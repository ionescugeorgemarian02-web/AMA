"""API-ul public al gateway-ului: `apeleaza`. Restul aplicației nu vorbește cu furnizorii altfel.

    from app import gateway

    class Clasificare(gateway.Iesire):
        eticheta: Literal["pozitiv", "negativ", "neutru"]

    try:
        r = gateway.apeleaza(
            db, prompt="comentarii.clasifica", variabile={"text": comentariu}, schema=Clasificare,
            tenant_id=tenant_id, livrabil_id=livrabil_id, componenta="h4.moderator",
            prioritate=Prioritate.P2,
        )
    except gateway.Amanat as amanat:                   # cotă epuizată, furnizori căzuți: nu eșuează, se amână
        gateway.reprogrameaza(amanat, flux, tenant_id, comentariu_id, cheie=f"comentariu:{comentariu_id}")
    else:
        r.iesire.eticheta, r.model, r.pret_umbra, r.degradat

Ce face, în ordine: verifică clientul, rezolvă promptul (versiunea activă) și îl completează cu
variabilele, verifică
bugetul livrabilului, rulează interceptorii „înainte”, alege modelul și îl apelează (cote, reîncercări,
lanț de
rezervă, o reparație), rulează interceptorii „după”, scrie în jurnal (și când apelul eșuează, se amână
sau e refuzat) și
contorizează apelul în bugetul livrabilului (`productie.inregistreaza_consum`).
"""

import dataclasses
import os
import time
import uuid
from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app import productie
from app.config import get_settings
from app.gateway import jurnal, prompturi
from app.gateway.apel import ContextApel, Rezultat, ruleaza
from app.gateway.erori import Amanat, ApelRefuzat, FurnizoriIndisponibili, IesireInvalida
from app.gateway.iesire import Iesire, cheie_schema
from app.ids import new_id
from app.logging import correlation_id, get_logger
from app.operare import motor
from app.operare.motor import Prioritate

log = get_logger("app.gateway")
LUNGIME_MINIMA_SECRET = 16


def _secrete() -> list[str]:
    """Valorile secrete ale acestui proces: cheile furnizorilor și cheile aplicației (21.2: niciun secret
    într-un prompt)."""
    s = get_settings()
    valori = [v for k, v in os.environ.items() if k.startswith("AMA_CHEIE_")]
    valori += [s.master_key.get_secret_value(), s.secret_key.get_secret_value()]
    return [v for v in valori if len(v) >= LUNGIME_MINIMA_SECRET]


def _fara_secrete(texte: list[str]) -> None:
    secrete = _secrete()
    if any(sec in t for t in texte for sec in secrete):
        raise ApelRefuzat("secret_in_prompt", "un secret al aplicației ar fi ajuns într-un prompt")


def apeleaza(
    db: Session,
    *,
    prompt: str,
    variabile: Mapping[str, Any],
    schema: type[Iesire],
    tenant_id: uuid.UUID,
    componenta: str,
    prioritate: Prioritate,
    profil: str | None = None,
    livrabil_id: uuid.UUID | None = None,
    max_tokeni: int = 1024,
    temperatura: float = 0.2,
    alt_model_decat: str | None = None,
    accepta_provizoriu: bool = False,
    date_confidentiale: bool = False,
    mascheaza_cui: bool = False,
    demasca: bool = False,
    model: str | None = None,
) -> Rezultat:
    """Un apel la un model, prin profilul lui. Ridică `Amanat`, `ApelRefuzat`, `IesireInvalida` sau
    `FurnizoriIndisponibili`; orice apel (și orice eșec) se scrie în jurnal.

    - `prompt`: `nume` (versiunea activă) sau `nume@versiune`; `profil` implicit este cel al promptului;
    - `schema`: moștenește `Iesire` și trebuie să fie cea cu care a fost înregistrat promptul;
    - `livrabil_id`: apelul se contorizează în bugetul lui; cu bugetul epuizat apelul se refuză;
    - `alt_model_decat`: `furnizor/identificator` al autorului (profilul „judecată”);
    - `accepta_provizoriu`: profilul „consiliu” poate coborî la T3 marcat `provizoriu`;
    - `date_confidentiale`: furnizorii care antrenează pe date sau cu termeni necunoscuți nu primesc apelul
      (8.9);
    - `model`: doar acest model (`furnizor/identificator`), fără lanțul profilului (evaluare, diagnostic);
    - `mascheaza_cui`: maschează și CUI/CIF (implicit nu); `demasca`: răspunsul revine cu valorile originale.
      Datele personale se maschează ÎNTOTDEAUNA înainte de apel (F3.9); jurnalul păstrează varianta mascată.

    Jurnalul se scrie într-o tranzacție proprie, dar consumul din bugetul livrabilului se scrie în
    sesiunea `db` a
    apelantului: apelantul prinde `Amanat` / `EroareGateway` ÎN tranzacția lui; o excepție care iese din
    ea anulează
    tranzacția, cu tot cu consum."""
    apel_id = new_id()
    corelare = correlation_id.get() or apel_id.hex
    start = time.monotonic()
    ctx: ContextApel | None = None
    rezultat: Rezultat | None = None
    eroare: BaseException | None = None
    reperat: prompturi.Reperat | None = None
    try:
        ctx_db = db.info.get("ama_ctx")
        if ctx_db is not None and ctx_db.tenant_id is not None and ctx_db.tenant_id != tenant_id:
            raise ApelRefuzat("tenant_diferit", "sesiunea aparține altui client")
        reperat = prompturi.rezolva(db, prompt)
        if reperat is None:
            raise ApelRefuzat("prompt_necunoscut", f"{prompt}: nu există sau nu are o versiune activă")
        if reperat.schema_nume != cheie_schema(schema):
            raise ApelRefuzat("schema_diferita", f"{reperat.referinta} cere {reperat.schema_nume}")
        mesaje = prompturi.mesaje_pentru(reperat, variabile)
        _fara_secrete([m.continut for m in mesaje])
        if livrabil_id is not None:
            livrabil = db.get(productie.Livrabil, livrabil_id)
            if livrabil is None:  # inexistent sau al altui client (RLS)
                raise ApelRefuzat("livrabil_necunoscut", str(livrabil_id))
            if not productie.poate_consuma(livrabil):
                raise ApelRefuzat(
                    "buget_livrabil", "bugetul de apeluri sau de timp al livrabilului e epuizat"
                )
        ctx = ContextApel(
            db=db, tenant_id=tenant_id, profil=profil or reperat.profil, mesaje=mesaje,
            schema=schema, componenta=componenta, prioritate=prioritate, livrabil_id=livrabil_id,
            max_tokeni=max_tokeni, temperatura=temperatura, alt_model_decat=alt_model_decat,
            accepta_provizoriu=accepta_provizoriu, date_confidentiale=date_confidentiale,
            coada=motor.coada_curenta(), model_fixat=model,
            mascheaza_cui=mascheaza_cui, demasca=demasca, prompt_nume=reperat.nume,
            prompt_versiune=reperat.versiune,
            corelare_id=corelare,
        )  # fmt: skip
        rezultat = ruleaza(ctx)
        rezultat = dataclasses.replace(rezultat, apel_id=apel_id)
        return _demasca(ctx, rezultat) if demasca else rezultat
    except BaseException as exc:
        eroare = exc
        raise
    finally:
        _incheie(
            db, apel_id, corelare, time.monotonic() - start,
            tenant_id=tenant_id, componenta=componenta, prioritate=prioritate, livrabil_id=livrabil_id,
            profil=(ctx.profil if ctx else (profil or "")), prompt=prompt, reperat=reperat, ctx=ctx,
            rezultat=rezultat, eroare=eroare,
        )  # fmt: skip


def _demasca(ctx: ContextApel, rezultat: Rezultat) -> Rezultat:
    """Răspunsul pentru apelant, cu valorile originale în loc de marcaje (jurnalul rămâne mascat)."""
    masca = ctx.extra.get("masca")
    if masca is None:
        return rezultat
    try:
        iesire = type(rezultat.iesire).model_validate(
            masca.demasca_json(rezultat.iesire.model_dump(mode="json"))
        )
    except ValueError:  # valoarea originală nu respectă un tip al schemei: se întoarce varianta mascată
        return rezultat
    return dataclasses.replace(rezultat, iesire=iesire)


def _raspuns_mascat(ctx: ContextApel | None, rezultat: Rezultat | None) -> dict[str, Any] | None:
    """Răspunsul se salvează mascat (8.8: datele personale se maschează înainte de salvare)."""
    if rezultat is None:
        return None
    brut = rezultat.iesire.model_dump(mode="json")
    masca = ctx.extra.get("masca") if ctx else None
    return masca.json(brut, raspuns=True) if masca is not None else brut


def _incheie(
    db: Session,
    apel_id: uuid.UUID,
    corelare: str,
    secunde: float,
    *,
    tenant_id: uuid.UUID,
    componenta: str,
    prioritate: Prioritate,
    livrabil_id: uuid.UUID | None,
    profil: str,
    prompt: str,
    reperat: prompturi.Reperat | None,
    ctx: ContextApel | None,
    rezultat: Rezultat | None,
    eroare: BaseException | None,
) -> None:
    esecuri = ctx.extra.get("esecuri") if ctx else None
    incercari = list(esecuri.incercari) if esecuri else []
    if rezultat is not None:
        stare, cod = "ok", ""
    elif isinstance(eroare, Amanat):
        stare, cod = "amanat", "amanat"
    elif isinstance(eroare, ApelRefuzat):
        stare, cod = "refuzat", eroare.cod
    elif isinstance(eroare, IesireInvalida):
        stare, cod = "esec", "iesire_invalida"
    elif isinstance(eroare, FurnizoriIndisponibili):
        stare, cod = "esec", "furnizori_indisponibili"
    else:
        stare, cod = "esec", type(eroare).__name__ if eroare else "necunoscut"
    ultimul = incercari[-1] if incercari else None
    intrare = jurnal.IntrareJurnal(
        id=apel_id, tenant_id=tenant_id, livrabil_id=livrabil_id, componenta=componenta,
        prioritate=prioritate.name, profil=profil, rezultat=stare, cod_eroare=cod,
        prompt_nume=reperat.nume if reperat else prompt.split("@")[0],
        prompt_versiune=reperat.versiune if reperat else None, corelare_id=corelare,
        furnizor=rezultat.furnizor if rezultat else (ultimul.model.split("/")[0] if ultimul else ""),
        model=rezultat.model if rezultat else (ultimul.model if ultimul else ""),
        nivel=rezultat.nivel if rezultat else "",
        motiv_alegere=rezultat.motiv_alegere if rezultat else (str(eroare)[:300] if eroare else ""),
        tokeni_intrare=(rezultat.tokeni_intrare if rezultat else (esecuri.tokeni_intrare if esecuri else 0)),
        tokeni_iesire=(rezultat.tokeni_iesire if rezultat else (esecuri.tokeni_iesire if esecuri else 0)),
        durata_ms=int(secunde * 1000), reparatii=rezultat.reparatii if rezultat else 0,
        pret_umbra=rezultat.pret_umbra if rezultat else (esecuri.pret_umbra if esecuri else Decimal(0)),
        degradat=bool(rezultat and rezultat.degradat), provizoriu=bool(rezultat and rezultat.provizoriu),
        verificare_suplimentara=bool(rezultat and rezultat.verificare_suplimentara),
        incercari=[dataclasses.asdict(i) for i in incercari],
        mesaje=[{"rol": m.rol, "continut": m.continut} for m in (ctx.mesaje if ctx else ())],
        raspuns=_raspuns_mascat(ctx, rezultat), semnale=list(ctx.extra.get("semnale", [])) if ctx else [],
    )  # fmt: skip
    jurnal.scrie(intrare)
    if livrabil_id is not None and any(i.rezultat != "cota" for i in incercari):
        # Apelul a ajuns la cel puțin un furnizor: se numără în bugetul livrabilului (inclusiv eșecurile).
        try:
            productie.inregistreaza_consum(
                db, livrabil_id, apeluri_llm=1, secunde=secunde, componenta=componenta,
                diagnostic={"profil": profil, "model": intrare.model, "rezultat": stare},
            )  # fmt: skip
        except Exception as exc:  # contorizarea nu are voie să acopere eroarea (sau rezultatul) apelului
            log.error(
                "consumul nu s-a putut înregistra",
                extra={"livrabil": str(livrabil_id), "tip_eroare": type(exc).__name__},
            )
