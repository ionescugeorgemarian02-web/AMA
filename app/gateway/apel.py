"""Rutarea și reacțiile la erori (8.2–8.3, 7.5): un apel parcurge lanțul profilului, model cu model.

Reacțiile (7.5), pe model, în ordinea în care apar:
- limită de rată (429): modelul se blochează până la resetare și se trece pe următorul; dacă nu mai
rămâne niciunul,
  apelul se amână până la cel mai apropiat moment de reluare;
- eroare de server sau de rețea: 3 reîncercări cu pauză crescătoare (1, 2, 4 s) pe același model, apoi
următorul;
  fiecare cerere eșuată numără la întrerupătorul furnizorului (3 la rând → scos pentru 2 minute);
- ieșire în afara schemei: o reparație pe același model, apoi următorul;
- autentificare (401 / 403): furnizorul trece pe pauză (până îl reactivează un om), cu alertă; se trece
pe următorul;
- altă eroare a cererii (400, conținut blocat): modelul se sare pentru acest apel.

Când lanțul principal s-a epuizat, profilul decide: `amana` → `Amanat` (strategia nu coboară niciodată la
un model mai
slab), `degradeaza` → lanțul de degradare (marcat), `amana_sau_provizoriu` → T3 „provizoriu” doar dacă
apelantul acceptă.
"""

import datetime as dt
import json
import time
import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.config import get_settings
from app.gateway import ceas, client, cote, interceptori, limitator, registru, sanatate
from app.gateway.candidat import Candidat
from app.gateway.cote import estimeaza_tokeni
from app.gateway.erori import (
    Amanat,
    ApelRefuzat,
    EroareFurnizor,
    FurnizoriIndisponibili,
    IesireInvalida,
)
from app.gateway.iesire import Iesire, schema_json
from app.gateway.intrerupator import StareSanatate
from app.gateway.limitator import Refuz
from app.gateway.profiluri import Profil
from app.gateway.rutare import INTERZIS, Cerinte, Motiv, Selectie, alege
from app.gateway.structurat import IesireNevalida, IesireStructurata, ruleaza_structurat
from app.gateway.tipuri import CerereModel, Mesaj, RaspunsModel
from app.operare import opriri
from app.operare.motor import Prioritate

PAUZA_FARA_FURNIZOR_SEC = (
    300.0  # nimic eligibil acum (furnizori opriți, fără cheie): se reîncearcă peste 5 minute
)
COD_INTERZIS = {
    Motiv.T4_CALE_CRITICA: "t4_in_afara_caii_critice",
    Motiv.APELURI_PLATITE: "apeluri_platite_oprite",
}


class CotaEpuizata(Exception):
    """Cota modelului nu permite apelul acum. Intern gateway-ului."""

    def __init__(self, refuz: Refuz) -> None:
        super().__init__(refuz.motiv)
        self.refuz = refuz


@dataclass
class ContextApel:
    """Ce știu interceptorii și rutarea despre un apel. Mutabil: un interceptor poate schimba `mesaje`
    sau poate
    cere reguli mai stricte (`date_confidentiale`); `extra` este loc liber pentru ei."""

    db: Session
    tenant_id: uuid.UUID
    profil: str
    mesaje: tuple[Mesaj, ...]
    schema: type[Iesire]
    componenta: str
    prioritate: Prioritate = Prioritate.P1
    livrabil_id: uuid.UUID | None = None
    max_tokeni: int = 1024
    temperatura: float = 0.2
    alt_model_decat: str | None = None
    accepta_provizoriu: bool = False
    date_confidentiale: bool = False
    prompt_nume: str = ""
    prompt_versiune: int | None = None
    corelare_id: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Incercare:
    """Un pas din traseul unui apel (pentru jurnal): ce model, cu ce rezultat, cât a costat."""

    model: str
    # ok | reparat | cota | limita | server | retea | autentificare | cerere | continut | iesire_invalida
    rezultat: str
    durata_ms: int = 0
    tokeni_intrare: int = 0
    tokeni_iesire: int = 0
    detaliu: str = ""


@dataclass(frozen=True)
class Rezultat:
    iesire: Iesire
    model: str  # `furnizor/identificator`
    furnizor: str
    nivel: str
    tokeni_intrare: int  # totalul apelului, inclusiv încercările eșuate care au consumat tokeni
    tokeni_iesire: int
    durata_ms: int
    reparatii: int
    pret_umbra: Decimal
    degradat: bool = False
    provizoriu: bool = False
    verificare_suplimentara: bool = False
    incercari: tuple[Incercare, ...] = ()
    motiv_alegere: str = ""
    prompt_nume: str = ""
    prompt_versiune: int | None = None
    apel_id: uuid.UUID | None = None


def pret_umbra(c: Candidat, tokeni_intrare: int, tokeni_iesire: int) -> Decimal:
    """Cât ar fi costat apelul la un furnizor plătit (8.5): tokeni × preț-umbră la 1 milion."""
    total = Decimal(tokeni_intrare) * Decimal(str(c.pret_umbra_intrare)) + Decimal(tokeni_iesire) * Decimal(
        str(c.pret_umbra_iesire)
    )
    return (total / Decimal(1_000_000)).quantize(Decimal("0.000001"))


# --- o cerere HTTP, cu cota ei


def _caractere(cerere: CerereModel) -> int:
    n = sum(len(m.continut) for m in cerere.mesaje)
    return n + (len(json.dumps(cerere.schema_json)) if cerere.schema_json else 0)


def un_apel(
    candidat: Candidat, cheie: str | None, cerere: CerereModel, prioritate: Prioritate
) -> RaspunsModel:
    """O cerere HTTP cu cota ei: rezervă, trimite, regularizează cu tokenii reali, corectează din antete."""
    rezervare = limitator.rezerva(
        candidat, estimeaza_tokeni(_caractere(cerere), cerere.max_tokeni), prioritate
    )
    if isinstance(rezervare, Refuz):
        raise CotaEpuizata(rezervare)
    try:
        raspuns = client.trimite(candidat.destinatie, cheie, cerere)
    except EroareFurnizor as exc:
        if exc.fel == "limita":
            limitator.blocheaza_dupa_429(candidat, exc.retry_dupa)
        if exc.fel != "retea":  # la timeout nu știm ce a consumat furnizorul: rezervarea rămâne
            limitator.regularizeaza(rezervare, 0)
        raise
    limitator.regularizeaza(rezervare, raspuns.tokeni_intrare + raspuns.tokeni_iesire)
    limitator.corecteaza_din_antete(candidat, raspuns.antete)
    return raspuns


def un_apel_cu_reincercari(
    candidat: Candidat, cheie: str | None, cerere: CerereModel, prioritate: Prioritate
) -> RaspunsModel:
    """Eroare de server sau de rețea: reîncercări cu pauză crescătoare (7.5), fiecare eșec numărând la
    întrerupătorul furnizorului. Pauzele sunt scurte și în firul apelantului (nu sunt amânarea durabilă)."""
    s = get_settings()
    esecuri = 0
    for incercare in range(s.gateway_reincercari + 1):
        try:
            raspuns = un_apel(candidat, cheie, cerere, prioritate)
        except EroareFurnizor as exc:
            if exc.fel not in ("server", "retea"):
                raise
            esecuri += 1
            sanatate.inregistreaza_esec(candidat.furnizor_id)
            if incercare >= s.gateway_reincercari:
                raise
            ceas.dormi(s.gateway_pauza_sec * s.gateway_factor_pauza**incercare)
            continue
        if esecuri or candidat.erori_consecutive or candidat.intrerupt_pana_la is not None:
            sanatate.inregistreaza_succes(candidat.furnizor_id)
        return raspuns
    raise AssertionError("neajuns")  # pragma: no cover


def incearca_model(
    candidat: Candidat,
    cheie: str | None,
    mesaje: tuple[Mesaj, ...],
    schema: type[Iesire],
    *,
    prioritate: Prioritate,
    max_tokeni: int = 1024,
    temperatura: float = 0.2,
) -> IesireStructurata:
    """Apel structurat (cu o reparație) pe `candidat`, fiecare cerere HTTP trecând prin cote și
    reîncercări."""
    sj = schema_json(schema)
    nativ = "iesire_structurata" in candidat.capabilitati

    def trimite(m: tuple[Mesaj, ...]) -> RaspunsModel:
        cerere = CerereModel(
            mesaje=m,
            max_tokeni=max_tokeni,
            temperatura=temperatura,
            schema_json=sj if nativ else None,
            schema_nume=schema.__name__,
        )
        return un_apel_cu_reincercari(candidat, cheie, cerere, prioritate)

    return ruleaza_structurat(trimite, mesaje, schema, nativ=nativ)


def apeleaza_pe_model(
    candidat: Candidat,
    cheie: str | None,
    mesaje: tuple[Mesaj, ...],
    schema: type[Iesire],
    *,
    prioritate: Prioritate = Prioritate.P1,
    max_tokeni: int = 1024,
    temperatura: float = 0.2,
) -> IesireStructurata:
    """Un model fixat, fără rutare: cota epuizată devine `Amanat(pana_la)`. Pentru probe și diagnostic;
    aplicațiile apelează prin profiluri (`gateway.apeleaza`)."""
    try:
        return incearca_model(
            candidat,
            cheie,
            mesaje,
            schema,
            prioritate=prioritate,
            max_tokeni=max_tokeni,
            temperatura=temperatura,
        )
    except CotaEpuizata as exc:
        if exc.refuz.imposibil:
            raise ApelRefuzat("cerere_prea_mare", exc.refuz.motiv) from None
        raise Amanat(exc.refuz.pana_la, exc.refuz.motiv) from None
    except EroareFurnizor as exc:
        if exc.fel == "limita":  # limitatorul l-a blocat deja; apelantul primește momentul reluării
            pana_la = cote.reluare_dupa(cote.pana_la_dupa_429(exc.retry_dupa, ceas.acum()))
            raise Amanat(pana_la, "limită de rată la furnizor") from None
        raise


# --- rutarea


@dataclass
class _Esecuri:
    """Ce s-a întâmplat cu modelele încercate: din asta se alege eroarea finală."""

    amanari: list[dt.datetime] = field(default_factory=list)  # momente de la care merită reluat
    iesiri_invalide: int = 0
    prea_mari: int = 0
    alte: int = 0
    incercari: list[Incercare] = field(default_factory=list)
    tokeni_intrare: int = 0
    tokeni_iesire: int = 0
    pret_umbra: Decimal = Decimal(0)


def _parcurge(
    ctx: ContextApel, lant: tuple[Candidat, ...], esecuri: _Esecuri
) -> tuple[Candidat, IesireStructurata, int] | None:
    """Încearcă pe rând modelele; întoarce primul succes (modelul, ieșirea, durata) sau `None`."""
    for c in lant:
        start = time.monotonic()
        try:
            iesire = incearca_model(
                c,
                registru.citeste_cheie_env(c.cheie_env),
                ctx.mesaje,
                ctx.schema,
                prioritate=ctx.prioritate,
                max_tokeni=ctx.max_tokeni,
                temperatura=ctx.temperatura,
            )
        except CotaEpuizata as exc:
            if exc.refuz.imposibil:
                esecuri.prea_mari += 1
            else:
                esecuri.amanari.append(exc.refuz.pana_la)
            esecuri.incercari.append(Incercare(c.cod, "cota", detaliu=exc.refuz.motiv))
            continue
        except IesireNevalida as exc:
            esecuri.iesiri_invalide += 1
            esecuri.tokeni_intrare += sum(r.tokeni_intrare for r in exc.raspunsuri)
            esecuri.tokeni_iesire += sum(r.tokeni_iesire for r in exc.raspunsuri)
            esecuri.pret_umbra += pret_umbra(
                c, sum(r.tokeni_intrare for r in exc.raspunsuri), sum(r.tokeni_iesire for r in exc.raspunsuri)
            )
            esecuri.incercari.append(
                Incercare(
                    c.cod,
                    "iesire_invalida",
                    int((time.monotonic() - start) * 1000),
                    sum(r.tokeni_intrare for r in exc.raspunsuri),
                    sum(r.tokeni_iesire for r in exc.raspunsuri),
                    exc.eroare,
                )
            )
            continue
        except EroareFurnizor as exc:
            _reactie_la_eroare(c, exc, esecuri, int((time.monotonic() - start) * 1000))
            continue
        durata = int((time.monotonic() - start) * 1000)
        esecuri.tokeni_intrare += iesire.tokeni_intrare
        esecuri.tokeni_iesire += iesire.tokeni_iesire
        esecuri.pret_umbra += pret_umbra(c, iesire.tokeni_intrare, iesire.tokeni_iesire)
        esecuri.incercari.append(
            Incercare(
                c.cod,
                "reparat" if iesire.reparat else "ok",
                durata,
                iesire.tokeni_intrare,
                iesire.tokeni_iesire,
                iesire.eroare_initiala,
            )
        )
        return c, iesire, durata
    return None


def _reactie_la_eroare(c: Candidat, exc: EroareFurnizor, esecuri: _Esecuri, durata_ms: int) -> None:
    acum = ceas.acum()
    esecuri.incercari.append(Incercare(c.cod, exc.fel, durata_ms, detaliu=str(exc)[:200]))
    if exc.fel == "limita":
        esecuri.amanari.append(cote.reluare_dupa(cote.pana_la_dupa_429(exc.retry_dupa, acum)))
    elif exc.fel == "autentificare":
        sanatate.pune_pe_pauza(c.furnizor_id, c.furnizor, motiv="eroare de autentificare")
    elif exc.fel in ("server", "retea"):
        s = get_settings()
        stare = sanatate.citeste_starea(c.furnizor_id, acum)
        esecuri.amanari.append(
            stare.intrerupt_pana_la or acum + dt.timedelta(seconds=s.gateway_intrerupator_pauza_sec)
        )
    else:
        esecuri.alte += 1


def _eroare_finala(
    ctx: ContextApel, sel: Selectie, esecuri: _Esecuri
) -> Amanat | ApelRefuzat | IesireInvalida | FurnizoriIndisponibili:
    incercat = bool(esecuri.incercari)
    if not incercat:
        interzise = sel.motive() & INTERZIS
        if interzise:  # nu e o problemă de moment: nu are voie. Prima în ordinea de la 8.x / ADR-06.
            return ApelRefuzat(COD_INTERZIS[sorted(interzise)[0]], "profilul nu are niciun model permis")
    if esecuri.amanari:
        return Amanat(min(esecuri.amanari), "cota sau sănătatea furnizorilor")
    if esecuri.prea_mari and not esecuri.iesiri_invalide and not esecuri.alte:
        return ApelRefuzat("cerere_prea_mare", "cererea nu încape în limitele niciunui model din lanț")
    if esecuri.iesiri_invalide:
        return IesireInvalida(f"ieșire în afara schemei pe {esecuri.iesiri_invalide} model(e) din lanț")
    if esecuri.alte:
        return FurnizoriIndisponibili("niciun model din lanț nu a acceptat cererea")
    return Amanat(
        ceas.acum() + dt.timedelta(seconds=PAUZA_FARA_FURNIZOR_SEC), "niciun furnizor activ pentru profil"
    )


def _rezultat(
    ctx: ContextApel,
    c: Candidat,
    iesire: IesireStructurata,
    esecuri: _Esecuri,
    *,
    durata_ms: int,
    profil: Profil,
    degradat: bool,
    provizoriu: bool,
    motiv: str,
) -> Rezultat:
    return Rezultat(
        iesire=iesire.obiect,
        model=c.cod,
        furnizor=c.furnizor,
        nivel=c.nivel,
        tokeni_intrare=esecuri.tokeni_intrare,
        tokeni_iesire=esecuri.tokeni_iesire,
        durata_ms=durata_ms,
        reparatii=1 if iesire.reparat else 0,
        pret_umbra=esecuri.pret_umbra,
        degradat=degradat,
        provizoriu=provizoriu,
        verificare_suplimentara=degradat and profil.verificare_in_plus,
        incercari=tuple(esecuri.incercari),
        motiv_alegere=motiv,
        prompt_nume=ctx.prompt_nume,
        prompt_versiune=ctx.prompt_versiune,
    )


def alege_si_ruleaza(ctx: ContextApel) -> Rezultat:
    """Rutarea propriu-zisă (fără interceptori și fără jurnal): vezi `ruleaza`."""
    db = ctx.db
    profil = registru.profil(db, ctx.profil)
    if profil is None:
        raise ApelRefuzat("profil_necunoscut", ctx.profil)
    if opriri.este_oprit(db, opriri.Oprire.CLIENT, tenant_id=ctx.tenant_id):
        raise ApelRefuzat("client_oprit", "clientul este oprit")
    acum = ceas.acum()
    candidati = registru.candidati(db)
    cer = Cerinte(
        prioritate=ctx.prioritate,
        acum=acum,
        date_confidentiale=ctx.date_confidentiale,
        alt_model_decat=ctx.alt_model_decat,
        apeluri_platite_oprite=opriri.este_oprit(db, opriri.Oprire.APELURI_PLATITE, tenant_id=ctx.tenant_id),
        chei_configurate=frozenset(
            {c.furnizor for c in candidati if registru.citeste_cheie_env(c.cheie_env) is not None}
        ),
        sanatate={c.furnizor: StareSanatate(c.erori_consecutive, c.intrerupt_pana_la) for c in candidati},
    )
    sel = alege(profil, candidati, cer)
    esecuri = _Esecuri()
    ctx.extra["esecuri"] = esecuri  # pentru jurnal, și când apelul se termină cu eroare
    succes = _parcurge(ctx, sel.principal, esecuri)
    if succes is not None:
        c, iesire, durata = succes
        pozitie = sel.principal.index(c)
        motiv = (
            "primul model eligibil din lanț"
            if pozitie == 0
            else f"modelele dinaintea lui au eșuat ({pozitie})"
        )
        return _rezultat(
            ctx,
            c,
            iesire,
            esecuri,
            durata_ms=durata,
            profil=profil,
            degradat=False,
            provizoriu=False,
            motiv=motiv,
        )
    degradare_permisa = profil.la_epuizare == "degradeaza" or (
        profil.la_epuizare == "amana_sau_provizoriu" and ctx.accepta_provizoriu
    )
    if degradare_permisa and sel.degradare:
        succes = _parcurge(ctx, sel.degradare, esecuri)
        if succes is not None:
            c, iesire, durata = succes
            return _rezultat(
                ctx, c, iesire, esecuri, durata_ms=durata, profil=profil, degradat=True,
                provizoriu=profil.la_epuizare == "amana_sau_provizoriu",
                motiv="lanțul principal s-a epuizat: degradare conform profilului",
            )  # fmt: skip
    raise _eroare_finala(ctx, sel, esecuri)


def ruleaza(ctx: ContextApel) -> Rezultat:
    """Un apel prin gateway: interceptorii „înainte”, rutarea, interceptorii „după” (mereu, cu rezultatul
    sau eroarea)."""
    rezultat: Rezultat | None = None
    try:
        interceptori.ruleaza_inainte(ctx)
        rezultat = alege_si_ruleaza(ctx)
    except BaseException as exc:
        interceptori.ruleaza_dupa(ctx, None, exc)
        raise
    interceptori.ruleaza_dupa(ctx, rezultat, None)
    return rezultat
