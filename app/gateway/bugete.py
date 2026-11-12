"""Bugetele pe client (F3.8, 8.5): consum pe zi și pe lună, citit din contoare proprii, aplicat ca
interceptor.

Decizia despre consum: contoare proprii (`gateway_consum_client`), nu jurnalul de apeluri. Jurnalul se
scrie abia la sfârșitul apelului, într-o tranzacție separată, deci două apeluri simultane ar citi același
total și ar depăși bugetul; un contor se rezervă cu O SINGURĂ instrucțiune `INSERT … ON CONFLICT DO UPDATE
… WHERE` sub plafon (ca la limitatoarele de cotă din F3.3): corectă la concurență, între fire și între
workeri. Tokenii și prețul-umbră se adaugă după apel.

Ce face interceptorul `buget_client` (înregistrat la import, ordinea 20):
- `inainte`: rezervă un apel pe fereastra zilei și pe a lunii, în aceeași tranzacție (ori ambele, ori
  niciuna). La depășire: P2 și P3 primesc `Amanat(momentul resetării)`, P1 la fel dar abia peste
  `plafon_p1` × buget, P0 trece mereu (regulile, în `reguli_buget`). Apelul amânat nu consumă nimic.
- `dupa`: adaugă tokenii și prețul-umbră reale (și ale încercărilor eșuate, care s-au consumat); dacă
  apelul nu a ajuns la niciun furnizor (amânat pe cotă, refuzat), eliberează apelul rezervat.
- pragul de avertizare: la atingere (pe orice axă) pleacă o notificare „important”, o singură dată pe
  fereastră (rândul contorului are `avertizat`, setat atomic).
Tranzacțiile sunt ale interceptorului (sesiune de client, commit imediat): consumul rămâne chiar dacă
apelantul face rollback.
"""

import datetime as dt
import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import BigInteger, Integer, Numeric, bindparam, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import sesiune_tenant
from app.gateway import ceas, cote, interceptori
from app.gateway.erori import Amanat
from app.gateway.reguli_buget import (
    ETICHETE_AXA,
    ETICHETE_FEREASTRA,
    Axa,
    Buget,
    Consum,
    Fereastra,
    Valori,
    axe_la_prag,
    depasiri,
    inceput_fereastra,
    plafon,
    sfarsit_fereastra,
)
from app.logging import get_logger
from app.operare import audit

log = get_logger("app.gateway")

COLOANE = ("apeluri", "tokeni", "pret_umbra")
CAMPURI_BUGET = tuple(f"{c}_{f}" for f in ("zi", "luna") for c in COLOANE)

REZERVA = text(
    """
    INSERT INTO gateway_consum_client AS c (tenant_id, fereastra, inceput, apeluri, actualizat_la)
    SELECT :tenant, :fereastra, :inceput, 1, :acum
    WHERE (CAST(:pa AS integer) IS NULL OR 1 <= CAST(:pa AS integer))
      AND (CAST(:pt AS bigint) IS NULL OR 0 < CAST(:pt AS bigint))
      AND (CAST(:pp AS numeric) IS NULL OR 0 < CAST(:pp AS numeric))
    ON CONFLICT (tenant_id, fereastra, inceput) DO UPDATE
       SET apeluri = c.apeluri + 1, actualizat_la = :acum
     WHERE (CAST(:pa AS integer) IS NULL OR c.apeluri + 1 <= CAST(:pa AS integer))
       AND (CAST(:pt AS bigint) IS NULL OR c.tokeni < CAST(:pt AS bigint))
       AND (CAST(:pp AS numeric) IS NULL OR c.pret_umbra < CAST(:pp AS numeric))
    RETURNING apeluri, tokeni, pret_umbra
    """
).bindparams(
    bindparam("pa", type_=Integer), bindparam("pt", type_=BigInteger), bindparam("pp", type_=Numeric)
)

REGULARIZEAZA = text(
    """
    UPDATE gateway_consum_client
       SET apeluri = GREATEST(apeluri + :d_apeluri, 0), tokeni = tokeni + :tokeni,
           pret_umbra = pret_umbra + :pret, actualizat_la = :acum
     WHERE tenant_id = :tenant AND fereastra = :fereastra AND inceput = :inceput
    RETURNING apeluri, tokeni, pret_umbra
    """
)

MARCHEAZA_AVERTIZAT = text(
    """
    UPDATE gateway_consum_client SET avertizat = true
     WHERE tenant_id = :tenant AND fereastra = :fereastra AND inceput = :inceput AND NOT avertizat
    RETURNING 1
    """
)


# Interogări statice, câte una pe câmp (numele coloanei nu se compune niciodată din intrarea utilizatorului).
UPDATE_CLIENT = {
    k: text(
        f"UPDATE gateway_bugete_client SET {k} = :v, actualizat_la = now(), "  # noqa: S608
        "actualizat_de = :u WHERE tenant_id = :t"
    )
    for k in CAMPURI_BUGET
}
UPDATE_IMPLICIT = {
    k: text(
        f"UPDATE gateway_bugete_implicite SET {k} = :v, actualizat_la = now(), "  # noqa: S608
        "actualizat_de = :u WHERE id = 1"
    )
    for k in CAMPURI_BUGET
}


# --- bugetul efectiv


def _valori(rand: Any, fereastra: Fereastra) -> Valori:
    return Valori(
        rand[f"apeluri_{fereastra.value}"],
        rand[f"tokeni_{fereastra.value}"],
        rand[f"pret_umbra_{fereastra.value}"],
    )


def implicit(db: Session) -> Buget:
    r = db.execute(text("SELECT * FROM gateway_bugete_implicite WHERE id = 1")).mappings().first()
    if r is None:  # fără rând implicit nu există limită (un rând lipsă nu trebuie să oprească platforma)
        return Buget()
    return Buget(
        _valori(r, Fereastra.ZI),
        _valori(r, Fereastra.LUNA),
        float(r["prag_avertizare"]),
        float(r["plafon_p1"]),
    )


def efectiv(db: Session, tenant_id: uuid.UUID) -> Buget:
    """Bugetul clientului: valorile lui proprii, iar unde lipsesc, cele implicite."""
    baza = implicit(db)
    r = (
        db.execute(text("SELECT * FROM gateway_bugete_client WHERE tenant_id = :t"), {"t": tenant_id})
        .mappings()
        .first()
    )
    if r is None:
        return baza

    def pe(f: Fereastra) -> Valori:
        proprii = _valori(r, f)
        b = baza.pe(f)
        return Valori(
            b.apeluri if proprii.apeluri is None else proprii.apeluri,
            b.tokeni if proprii.tokeni is None else proprii.tokeni,
            b.pret_umbra if proprii.pret_umbra is None else proprii.pret_umbra,
        )

    return Buget(pe(Fereastra.ZI), pe(Fereastra.LUNA), baza.prag_avertizare, baza.plafon_p1)


def consum_curent(
    db: Session, tenant_id: uuid.UUID, acum: dt.datetime | None = None
) -> dict[Fereastra, Consum]:
    acum = acum or ceas.acum()
    ora = get_settings().gateway_buget_reset_ora
    rezultat: dict[Fereastra, Consum] = {}
    for f in Fereastra:
        r = db.execute(
            text(
                "SELECT apeluri, tokeni, pret_umbra FROM gateway_consum_client "
                "WHERE tenant_id = :t AND fereastra = :f AND inceput = :i"
            ),
            {"t": tenant_id, "f": f.value, "i": inceput_fereastra(acum, f, ora)},
        ).first()
        rezultat[f] = Consum(int(r[0]), int(r[1]), Decimal(r[2])) if r else Consum()
    return rezultat


@dataclass(frozen=True)
class RandClient:
    tenant_id: uuid.UUID
    nume: str
    buget: Buget
    propriu: bool  # are suprascrieri proprii
    zi: Consum
    luna: Consum


def situatie(db: Session, acum: dt.datetime | None = None) -> list[RandClient]:
    """Consumul de azi și din luna curentă al fiecărui client vizibil sesiunii (proprietarul îi vede pe
    toți)."""
    acum = acum or ceas.acum()
    clienti = db.execute(text("SELECT id, nume FROM clienti ORDER BY nume")).all()
    cu_buget = {r[0] for r in db.execute(text("SELECT tenant_id FROM gateway_bugete_client"))}
    randuri = []
    for cid, nume in clienti:
        c = consum_curent(db, cid, acum)
        randuri.append(
            RandClient(cid, nume, efectiv(db, cid), cid in cu_buget, c[Fereastra.ZI], c[Fereastra.LUNA])
        )
    return randuri


# --- interceptorul


def _eticheta(fereastra: Fereastra, axe: list[Axa]) -> str:
    return f"{', '.join(ETICHETE_AXA[a] for a in axe)} {ETICHETE_FEREASTRA[fereastra]}"


class BugetClient:
    nume = "buget_client"

    def inainte(self, ctx: Any) -> None:
        acum = ceas.acum()
        ora = get_settings().gateway_buget_reset_ora
        anunturi: list[tuple[Fereastra, list[Axa], Buget]] = []
        refuzate: list[tuple[Fereastra, list[Axa]]] = []
        ferestre: dict[Fereastra, dt.datetime] = {}
        with sesiune_tenant(ctx.tenant_id) as db:
            buget = efectiv(db, ctx.tenant_id)
            for f in Fereastra:
                limita = plafon(buget.pe(f), ctx.prioritate, buget.plafon_p1)
                inceput = inceput_fereastra(acum, f, ora)
                r = db.execute(
                    REZERVA,
                    {
                        "tenant": ctx.tenant_id, "fereastra": f.value, "inceput": inceput, "acum": acum,
                        "pa": limita.apeluri, "pt": limita.tokeni, "pp": limita.pret_umbra,
                    },
                ).first()  # fmt: skip
                if r is None:
                    refuzate.append((f, self._axe_depasite(db, ctx, f, inceput, limita)))
                    continue
                ferestre[f] = inceput
                consum = Consum(int(r[0]), int(r[1]), Decimal(r[2]))
                axe = axe_la_prag(consum, buget.pe(f), buget.prag_avertizare)
                if axe and self._marcheaza_avertizat(db, ctx.tenant_id, f, inceput):
                    anunturi.append((f, axe, buget))
            if refuzate:
                db.rollback()  # nicio rezervare parțială nu rămâne
                anunturi.clear()
                ferestre.clear()
        if refuzate:
            pana_la = max(cote.reluare_dupa(sfarsit_fereastra(acum, f, ora)) for f, _ in refuzate)
            motiv = "bugetul clientului este atins (" + "; ".join(_eticheta(f, a) for f, a in refuzate) + ")"
            raise Amanat(pana_la, motiv)
        ctx.extra["buget"] = {"ferestre": ferestre, "buget": buget}
        self._anunta(ctx.tenant_id, anunturi)

    def dupa(self, ctx: Any, rezultat: Any, eroare: BaseException | None) -> None:
        stare = ctx.extra.get("buget")
        if stare is None:  # apelul nu a rezervat nimic (a fost amânat de buget sau oprit înainte)
            return
        esecuri = ctx.extra.get("esecuri")
        if rezultat is not None:
            ajuns, tokeni, pret = True, rezultat.tokeni_intrare + rezultat.tokeni_iesire, rezultat.pret_umbra
        elif esecuri is not None:
            ajuns = any(i.rezultat != "cota" for i in esecuri.incercari)
            tokeni = esecuri.tokeni_intrare + esecuri.tokeni_iesire
            pret = esecuri.pret_umbra
        else:
            ajuns, tokeni, pret = False, 0, Decimal(0)
        buget: Buget = stare["buget"]
        anunturi: list[tuple[Fereastra, list[Axa], Buget]] = []
        acum = ceas.acum()
        with sesiune_tenant(ctx.tenant_id) as db:
            for f, inceput in stare["ferestre"].items():
                r = db.execute(
                    REGULARIZEAZA,
                    {
                        "tenant": ctx.tenant_id, "fereastra": f.value, "inceput": inceput, "acum": acum,
                        "d_apeluri": 0 if ajuns else -1, "tokeni": tokeni if ajuns else 0,
                        "pret": pret if ajuns else Decimal(0),
                    },
                ).first()  # fmt: skip
                if r is None:
                    continue
                consum = Consum(int(r[0]), int(r[1]), Decimal(r[2]))
                axe = axe_la_prag(consum, buget.pe(f), buget.prag_avertizare)
                if axe and self._marcheaza_avertizat(db, ctx.tenant_id, f, inceput):
                    anunturi.append((f, axe, buget))
        self._anunta(ctx.tenant_id, anunturi)

    # --- interne

    @staticmethod
    def _axe_depasite(db: Session, ctx: Any, f: Fereastra, inceput: dt.datetime, limita: Valori) -> list[Axa]:
        r = db.execute(
            text(
                "SELECT apeluri, tokeni, pret_umbra FROM gateway_consum_client "
                "WHERE tenant_id = :t AND fereastra = :f AND inceput = :i"
            ),
            {"t": ctx.tenant_id, "f": f.value, "i": inceput},
        ).first()
        consum = Consum(int(r[0]), int(r[1]), Decimal(r[2])) if r else Consum()
        return depasiri(consum, limita) or [Axa.APELURI]

    @staticmethod
    def _marcheaza_avertizat(db: Session, tenant_id: uuid.UUID, f: Fereastra, inceput: dt.datetime) -> bool:
        return (
            db.execute(
                MARCHEAZA_AVERTIZAT, {"tenant": tenant_id, "fereastra": f.value, "inceput": inceput}
            ).first()
            is not None
        )

    @staticmethod
    def _anunta(tenant_id: uuid.UUID, anunturi: list[tuple[Fereastra, list[Axa], Buget]]) -> None:
        if not anunturi:
            return
        from app.operare import notificari

        try:
            with sesiune_tenant(tenant_id) as db:
                r = db.execute(text("SELECT nume FROM clienti WHERE id = :t"), {"t": tenant_id}).first()
            nume = str(r[0]) if r else str(tenant_id)[:8]
            for f, axe, buget in anunturi:
                notificari.notifica(
                    notificari.Nivel.IMPORTANT,
                    "Buget de modele aproape epuizat",
                    f"{nume}: {_eticheta(f, axe)} au atins {round(buget.prag_avertizare * 100)}% din buget. "
                    "P2 și P3 se amână când bugetul e atins; P0 nu e atins.",
                    url="/gateway/registru",
                )
        except Exception as exc:  # o alertă care nu pleacă nu are voie să strice apelul
            log.warning("alerta de buget nu a plecat", extra={"tip_eroare": type(exc).__name__})


# --- editare (ecranul „Modele și cote”, F3.10)


def _nume_audit(camp: str) -> str:
    """Jurnalul de audit refuză cheile cu „token” (le ia drept secrete): tokenii apar ca „jetoane”."""
    return camp.replace("tokeni", "jetoane")


class BugetInvalid(ValueError):
    """Valoare de buget nepermisă (negativă, prag în afara intervalului, câmp necunoscut)."""


def _curata(valori: dict[str, Any]) -> dict[str, Any]:
    ies: dict[str, Any] = {}
    for k, v in valori.items():
        if k not in CAMPURI_BUGET:
            raise BugetInvalid(f"câmp de buget necunoscut: {k}")
        if v is None or v == "":
            ies[k] = None
            continue
        try:
            n = Decimal(str(v))
        except ArithmeticError:
            raise BugetInvalid(f"{k}: nu e un număr") from None
        if n < 0 or not n.is_finite():
            raise BugetInvalid(f"{k}: nu poate fi negativ")
        ies[k] = n if k.startswith("pret_umbra") else int(n)
    return ies


def seteaza_client(
    db: Session, tenant_id: uuid.UUID, valori: dict[str, Any], *, utilizator_id: uuid.UUID | None
) -> None:
    """Suprascrie bugetul unui client (câmpurile date; `None` = revine la valoarea implicită). Cu audit."""
    curate = _curata(valori)
    db.execute(
        text("INSERT INTO gateway_bugete_client (tenant_id) VALUES (:t) ON CONFLICT (tenant_id) DO NOTHING"),
        {"t": tenant_id},
    )
    for k, v in curate.items():
        db.execute(UPDATE_CLIENT[k], {"v": v, "u": utilizator_id, "t": tenant_id})
    audit.record(
        db, "gateway.buget_client_setat", obiect_tip="client", obiect_id=str(tenant_id),
        utilizator_id=utilizator_id, tenant_id=tenant_id,
        detalii={_nume_audit(k): (None if v is None else str(v)) for k, v in curate.items()},
    )  # fmt: skip


def seteaza_implicite(
    db: Session,
    valori: dict[str, Any],
    *,
    prag_avertizare: float | None = None,
    plafon_p1: float | None = None,
    utilizator_id: uuid.UUID | None,
) -> None:
    """Schimbă bugetele implicite (valabile clienților fără suprascriere). Cu audit."""
    curate = _curata(valori)
    if prag_avertizare is not None and not 0.5 <= prag_avertizare <= 1.0:
        raise BugetInvalid("pragul de avertizare trebuie să fie între 50% și 100%")
    if plafon_p1 is not None and not 1.0 <= plafon_p1 <= 10.0:
        raise BugetInvalid("plafonul lui P1 trebuie să fie între 1 și 10 ori bugetul")
    for k, v in curate.items():
        db.execute(UPDATE_IMPLICIT[k], {"v": v, "u": utilizator_id})
    if prag_avertizare is not None:
        db.execute(
            text("UPDATE gateway_bugete_implicite SET prag_avertizare = :v WHERE id = 1"),
            {"v": prag_avertizare},
        )
    if plafon_p1 is not None:
        db.execute(text("UPDATE gateway_bugete_implicite SET plafon_p1 = :v WHERE id = 1"), {"v": plafon_p1})
    audit.record(
        db, "gateway.buget_implicit_setat", obiect_tip="buget", obiect_id="implicit",
        utilizator_id=utilizator_id, tenant_id=None,
        detalii={**{_nume_audit(k): (None if v is None else str(v)) for k, v in curate.items()},
                 "prag_avertizare": prag_avertizare, "plafon_p1": plafon_p1},
    )  # fmt: skip


def curata_vechi(*, acum: dt.datetime | None = None) -> int:
    """Contoarele ferestrelor încheiate de peste 400 de zile se șterg (rulează în curățarea zilnică)."""
    from app.db import sesiune_agentie

    acum = acum or ceas.acum()
    with sesiune_agentie() as db:
        r = db.execute(
            text("DELETE FROM gateway_consum_client WHERE inceput < :l"), {"l": acum - dt.timedelta(days=400)}
        )
        return int(getattr(r, "rowcount", 0) or 0)


def inregistreaza() -> None:
    """Interceptorul bugetelor, ordinea 20 (după mascare și marcare, înainte de rutare)."""
    interceptori.adauga(BugetClient(), ordine=20)
