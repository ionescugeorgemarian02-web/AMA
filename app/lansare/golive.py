"""Lista de go-live comercial (F15.6, docs/25 §25.5), bifabilă și calculată automat unde se poate.

Fiecare punct are un cod stabil și textul exact din §25.5. Punctele măsurabile au o regulă care se calculează
din bază, urme, fișiere sau configurare: `True` (îndeplinit), `False` (neîndeplinit, cu motiv) sau `None`
(nu se poate măsura aici). Un punct e bifat dacă regula dă `True`, sau dacă regula dă `None` și omul l-a
bifat; un
`False` calculat nu se poate acoperi cu o bifă manuală. Lansarea e permisă doar cu toate punctele bifate.

Pe lângă §25.5, punctul `C7` cere pâlnia de audit pornită (F15.6): motorul de audit nu e cel simulat.
"""

import datetime as dt
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.config import get_settings
from app.lansare import pilot
from app.lansare.modele import PilotClient, RezultatAvarie, StudiuCaz, VerificareLansare
from app.operare import audit
from app.operare.urme import Urma

ROOT = Path(__file__).resolve().parents[2]
Rezultat = tuple[bool | None, str]
Regula = Callable[[Session, dt.datetime], Rezultat]


@dataclass(frozen=True)
class Punct:
    cod: str
    sectiune: str
    text: str  # exact ca în docs/25 §25.5
    regula: Regula | None = None


def _acum() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def _avarie_staging(db: Session, acum: dt.datetime) -> Rezultat:
    r = db.execute(
        select(RezultatAvarie)
        .where(RezultatAvarie.mediu == "staging")
        .order_by(RezultatAvarie.rulat_la.desc())
    ).scalars().first()  # fmt: skip
    if r is None:
        return False, "testele de avarie nu au rulat încă pe staging (scripts/avarie.sh)"
    if acum - r.rulat_la > dt.timedelta(days=7):
        return False, f"ultima rulare pe staging e din {r.rulat_la:%Y-%m-%d} (mai veche de 7 zile)"
    if r.trecute < r.total:
        return False, f"pe staging: {r.trecute}/{r.total} scenarii trecute"
    return True, f"staging {r.rulat_la:%Y-%m-%d}: {r.trecute}/{r.total} scenarii; testele 25.2 = suita din CI"


def _zile_resurse(db: Session, acum: dt.datetime, zile: int) -> list[tuple[dt.date, bool, bool]]:
    """Pe fiecare zi din ultimele `zile`: (ziua, limitele respectate toată ziua, backup verde toată ziua)."""
    rows = db.execute(
        select(func.date(Urma.la), Urma.rezultat, Urma.iesiri)
        .where(Urma.componenta == "resurse", Urma.actiune == "verifica",
               Urma.la >= acum - dt.timedelta(days=zile), Urma.la <= acum)
    ).all()  # fmt: skip
    pe: dict[dt.date, list[bool]] = {}
    for zi, rez, ies in rows:
        z = pe.setdefault(zi, [True, True])
        z[0] = z[0] and rez == "ok"
        z[1] = z[1] and bool((ies or {}).get("backup_bun"))
    return [(z, v[0], v[1]) for z, v in sorted(pe.items())]


def _backup_4_saptamani(db: Session, acum: dt.datetime) -> Rezultat:
    zile = _zile_resurse(db, acum, 28)
    verzi = sum(1 for _, _, b in zile if b)
    if verzi >= 28:
        return True, "backup și restaurarea de test verzi în fiecare din ultimele 28 de zile"
    return False, f"verzi în {verzi} din ultimele 28 de zile (din urmele `resurse / verifica`)"


def _limite_14_zile(db: Session, acum: dt.datetime) -> Rezultat:
    zile = _zile_resurse(db, acum, 14)
    bune = sum(1 for _, ok, _ in zile if ok)
    if bune >= 14:
        return True, "disc sub 85% și memorie sub prag în fiecare din ultimele 14 zile"
    return False, f"respectate în {bune} din ultimele 14 zile măsurate"


def _doi_factori(db: Session, acum: dt.datetime) -> Rezultat:
    from app.conturi.roluri import ROLURI_AGENTIE

    fara = db.execute(
        text(
            "SELECT count(DISTINCT u.id) FROM utilizatori u JOIN apartenente a ON a.utilizator_id = u.id "
            "WHERE u.sters_la IS NULL AND a.sters_la IS NULL AND u.stare = 'activ' AND NOT u.totp_activ "
            "AND a.rol = ANY(:r)"
        ),
        {"r": [str(r) for r in ROLURI_AGENTIE]},
    ).scalar_one()
    return (
        (True, "toate conturile de administrare au 2FA") if not fara else (False, f"{fara} conturi fără 2FA")
    )


def _opriri_testate(db: Session, acum: dt.datetime) -> Rezultat:
    canale = set(
        db.execute(
            text(
                "SELECT DISTINCT detalii->>'canal' FROM jurnal_audit WHERE actiune = 'oprire.oprit' "
                "AND creat_la >= :de_la"
            ),
            {"de_la": acum - dt.timedelta(days=90)},
        ).scalars()
    )
    lipsa = {"panou", "telegram"} - canale
    if not lipsa:
        return True, "oprire folosită din panou și din Telegram în ultimele 90 de zile"
    return False, "netestat din: " + ", ".join(sorted(lipsa))


def _acord_judecatori(db: Session, acum: dt.datetime) -> Rezultat:
    from app.validare import calibrare
    from app.validare.calibrare_nucleu import MINIM_ETICHETE, PRAG_ACORD

    st = calibrare.statistici(db)
    if not st:
        return False, "nicio etichetă de calibrare încă"
    slabi = [
        j for j, s in st.items() if s["etichete"] < MINIM_ETICHETE or float(s["procent"] or 0) < PRAG_ACORD
    ]
    return (True, f"{len(st)} judecători la ≥ 85%") if not slabi else (False, "sub prag: " + ", ".join(slabi))


def _pilot(db: Session, acum: dt.datetime, *, ce: str) -> Rezultat:
    clienti = list(db.execute(select(PilotClient)).scalars())
    if not clienti:
        return False, "niciun client în pilot"
    porti = [pilot.stare_poarta(db, p, acum.date()) for p in clienti]
    if ce == "aprobare":
        rate = [x["rata_aprobare_din_prima"] for x in porti]
        if any(r is None or r <= pilot.PRAG_APROBARE for r in rate):
            return False, "aprobarea din prima: " + ", ".join("–" if r is None else f"{r:.0%}" for r in rate)
        return True, "aprobarea din prima peste 85% la toți clienții din pilot"
    incidente = sum(int(x["incidente_critice"]) for x in porti)
    gata = all(x["saptamani_gata"] >= p.saptamani for x, p in zip(porti, clienti, strict=True))
    if incidente:
        return False, f"{incidente} incidente critice în pilot"
    return (True, "zero incidente critice în pilot") if gata else (False, "pilotul nu s-a încheiat")


def _test_modele(db: Session, acum: dt.datetime) -> Rezultat:
    ultima = db.execute(
        text("SELECT max(pornita_la) FROM gateway_evaluari_rulari WHERE stare = 'terminata'")
    ).scalar()
    if ultima is None:
        return False, "testul comparativ al modelelor nu a rulat niciodată"
    if acum - ultima > dt.timedelta(days=31):
        return False, f"ultimul test comparativ: {ultima:%Y-%m-%d}"
    return True, f"ultimul test comparativ: {ultima:%Y-%m-%d}"


def _avocat(db: Session, acum: dt.datetime) -> Rezultat:
    from app.site import pagini

    ciorne = [f for f, c in pagini.DOCUMENTE_JURIDICE if pagini.TOATE[c].extra.get("ciorna")]
    return (
        (False, "ciorne nerevizuite: " + ", ".join(ciorne)) if ciorne else (True, "toate documentele semnate")
    )


def _transparenta(db: Session, acum: dt.datetime) -> Rezultat:
    from app.site import pagini

    contract = " ".join(" ".join(s.paragrafe + s.lista) for s in pagini.TOATE["legal/contract"].sectiuni)
    ok = "transparenta-ai" in pagini.TOATE and "jocuri de noroc" in contract
    return (
        (True, "/site/transparenta-ai și nișele refuzate (contract) publicate") if ok else (False, "lipsesc")
    )


def _studii(db: Session, acum: dt.datetime) -> Rezultat:
    n = db.execute(
        select(func.count()).select_from(StudiuCaz).where(StudiuCaz.stare == "publicat")
    ).scalar_one()
    return (True, f"{n} studii de caz publicate") if n >= 2 else (False, f"{n} din 2 studii de caz publicate")


def _proceduri(db: Session, acum: dt.datetime) -> Rezultat:
    lipsa = [
        f for f in ("restaurare.md", "instalare-vps.md") if not (ROOT / "docs" / "runbooks" / f).is_file()
    ]
    return (
        (False, "lipsesc: " + ", ".join(lipsa))
        if lipsa
        else (None, "scrise în docs/runbooks; „citite” se bifează")
    )


def _palnia_audit(db: Session, acum: dt.datetime) -> Rezultat:
    motor = get_settings().audit_motor
    return (
        (False, "motorul de audit e cel simulat")
        if motor == "simulat"
        else (True, f"motorul de audit: {motor}")
    )


PUNCTE: tuple[Punct, ...] = (
    Punct("T1", "Tehnic", "Toate testele din 25.2 și 25.3 trec pe staging", _avarie_staging),
    Punct(
        "T2",
        "Tehnic",
        "Backupul zilnic și restaurarea de test săptămânală sunt verzi de cel puțin 4 săptămâni",
        _backup_4_saptamani,
    ),
    Punct("T3", "Tehnic", "Al doilea factor este activ pe toate conturile de administrare", _doi_factori),
    Punct("T4", "Tehnic", "Butoanele de oprire sunt testate din panou și din Telegram", _opriri_testate),
    Punct("T5", "Tehnic", "Alertele critice ajung pe telefon în mai puțin de un minut"),
    Punct(
        "T6",
        "Tehnic",
        "Limitele de memorie și de disc au fost respectate în ultimele 14 zile",
        _limite_14_zile,
    ),
    Punct("T7", "Tehnic", "Niciun secret în repo; scanarea este curată"),
    Punct(
        "Q1",
        "Calitate",
        "Acordul dintre judecător și om este de cel puțin 85% pe fiecare validator",
        _acord_judecatori,
    ),
    Punct(
        "Q2",
        "Calitate",
        "Rata de aprobare din prima este peste 85% în pilot",
        lambda db, a: _pilot(db, a, ce="aprobare"),
    ),
    Punct(
        "Q3",
        "Calitate",
        "Zero incidente critice publicate în pilot",
        lambda db, a: _pilot(db, a, ce="incidente"),
    ),
    Punct("Q4", "Calitate", "Testul comparativ al modelelor a fost rulat în ultima lună", _test_modele),
    Punct(
        "C1",
        "Juridic și comercial",
        "Contractul, acordul de prelucrare, termenii și politicile sunt revizuite de avocat",
        _avocat,
    ),
    Punct(
        "C2",
        "Juridic și comercial",
        "Pagina „Transparență AI” și lista de nișe refuzate sunt publicate",
        _transparenta,
    ),
    Punct(
        "C3", "Juridic și comercial", "Matricea de conformitate pe țări este completată pentru piețele active"
    ),
    Punct("C4", "Juridic și comercial", "Facturarea și e-Factura sunt confirmate cu contabilul"),
    Punct("C5", "Juridic și comercial", "Prețurile sunt validate în discuții de vânzare"),
    Punct("C6", "Juridic și comercial", "Două studii de caz sunt publicate", _studii),
    Punct("C7", "Juridic și comercial", "Pâlnia de audit este pornită (F15.6)", _palnia_audit),
    Punct("O1", "Operare", "Procedurile pentru incidente sunt scrise și citite", _proceduri),
    Punct("O2", "Operare", "Rutina zilnică, săptămânală și lunară este în calendarul tău"),
    Punct("O3", "Operare", "Starea fiecărei aprobări API este cunoscută și comunicată cinstit clienților"),
)
EXTRA = {"C7"}  # nu e în §25.5: îl cere F15.6
DUPA_COD = {p.cod: p for p in PUNCTE}


def evalueaza(db: Session, acum: dt.datetime | None = None) -> list[dict[str, Any]]:
    acum = acum or _acum()
    manuale = {v.cod: v for v in db.execute(select(VerificareLansare)).scalars()}
    out = []
    for p in PUNCTE:
        try:
            auto, detaliu = p.regula(db, acum) if p.regula else (None, "se bifează de mână")
        except Exception as exc:  # o regulă stricată nu ascunde lista; punctul rămâne nebifat
            auto, detaliu = False, f"nu s-a putut calcula: {type(exc).__name__}"
        m = manuale.get(p.cod)
        bifat = auto is True or (auto is None and m is not None and m.bifat)
        out.append({"cod": p.cod, "sectiune": p.sectiune, "text": p.text, "auto": auto, "detaliu": detaliu,
                    "manual": bool(m and m.bifat), "nota": m.nota if m else "", "bifat": bifat,
                    "se_bifeaza_manual": auto is None})  # fmt: skip
    return out


def rezumat(puncte: list[dict[str, Any]]) -> dict[str, Any]:
    bifate = sum(1 for p in puncte if p["bifat"])
    return {"bifate": bifate, "total": len(puncte), "gata": bifate == len(puncte),
            "automate": sum(1 for p in puncte if not p["se_bifeaza_manual"])}  # fmt: skip


class BifaRefuzata(ValueError):
    pass


def bifeaza(db: Session, cod: str, bifat: bool, *, nota: str, utilizator_id: uuid.UUID) -> None:
    """Bifa manuală, cu audit; doar pe punctele care nu se pot măsura (cele calculate nu se bifează)."""
    p = DUPA_COD.get(cod)
    if p is None:
        raise BifaRefuzata("punct necunoscut")
    if p.regula is not None:
        auto, _ = p.regula(db, _acum())
        if auto is not None:
            raise BifaRefuzata("punctul se calculează automat; nu se bifează de mână")
    nota = nota.strip()[:500]
    if bifat and len(nota) < 3:
        raise BifaRefuzata("bifa cere o notă (dovada: ce ai verificat, unde)")
    db.execute(
        pg_insert(VerificareLansare)
        .values(cod=cod, bifat=bifat, nota=nota, bifat_de=utilizator_id)
        .on_conflict_do_update(index_elements=["cod"], set_={"bifat": bifat, "nota": nota,
                               "bifat_de": utilizator_id, "bifat_la": func.now()})
    )  # fmt: skip
    audit.record(db, "lansare.bifa", obiect_tip="verificare_lansare", obiect_id=cod,
                 utilizator_id=utilizator_id,
                 detalii={"bifat": bifat, "nota": nota})  # fmt: skip


def inregistreaza_avarie(db: Session, raport: dict[str, Any], *, mediu: str) -> RezultatAvarie:
    """Rezultatul `scripts/avarie.sh` (raport.json) pentru punctul T1."""
    if raport.get("schema") != "ama.avarie/1":
        raise ValueError("raportul nu e unul de avarie (ama.avarie/1)")
    r = RezultatAvarie(mediu=mediu, trecute=int(raport["trecute"]), total=int(raport["total"]), raport=raport)
    db.add(r)
    db.flush()
    return r
