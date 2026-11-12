"""Testul comparativ pe română (F3.6, 8.10): hamul de evaluare.

Setul de sarcini este DATĂ în repo (`evaluare/sarcini/<profil>.json`, 72 de sarcini: 12 pe fiecare profil
din 8.2, scrise de mână, fără date personale). Fiecare sarcină are instrucțiune, intrare și criterii
automate (vezi `criterii`). Rularea trece prin gateway ca orice alt apel: prompturi versionate din
`evaluare/prompturi/`, prioritate P3, cote și bugete respectate, jurnal; un singur model pe rulare
(`gateway.apeleaza(…, model=…)`), indiferent de lanțul profilului. Dacă cota se epuizează, rularea se
oprește `amanata` și se continuă mai târziu, fără să refacă ce s-a făcut.

Scorul unui model pe un profil = media scorurilor automate, combinată cu nota umană (1–5, pe eșantion,
importată sau introdusă) cu ponderea `PONDERE_UMANA`. Se scrie în `gateway_modele.scor[profil]`, de unde
rutarea îl ia ca prim criteriu (8.3 pasul 4). Fiecare rulare rămâne în istoric. Apelurile de evaluare se
fac pentru un client intern („Evaluare modele (intern)”), cu buget propriu.
"""

import csv
import datetime as dt
import hashlib
import io
import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from sqlalchemy import text
from sqlalchemy.orm import Session

from app import gateway
from app.conturi import Actor
from app.conturi.servicii import creeaza_client
from app.db import sesiune_agentie, sesiune_tenant
from app.gateway import bugete, ceas, criterii, prompturi, registru
from app.gateway.erori import EroareGateway
from app.gateway.iesire import Iesire
from app.ids import new_id
from app.logging import get_logger
from app.operare import audit
from app.operare.motor import Prioritate

log = get_logger("app.gateway")

DIRECTOR = Path(__file__).resolve().parents[2] / "evaluare"
PONDERE_UMANA = 0.4  # cât din scorul final vine din nota umană, când există
NUME_CLIENT = "Evaluare modele (intern)"
MAX_TOKENI = 900


class RaspunsClasificare(Iesire):
    eticheta: str


class RaspunsText(Iesire):
    text: str


class RaspunsJudecata(Iesire):
    verdict: Literal["acceptat", "respins"]
    motiv: str


class RaspunsConsiliu(Iesire):
    decizie: str
    motiv: str


SCHEME: dict[str, type[Iesire]] = {
    "clasificare": RaspunsClasificare,
    "rescriere": RaspunsText,
    "creatie": RaspunsText,
    "judecata": RaspunsJudecata,
    "strategie": RaspunsText,
    "consiliu": RaspunsConsiliu,
}


@dataclass(frozen=True)
class Sarcina:
    id: str
    profil: str
    instructiune: str
    intrare: str
    criterii: dict[str, Any]


def incarca_sarcini(director: Path | None = None) -> list[Sarcina]:
    sarcini: list[Sarcina] = []
    for cale in sorted((director or DIRECTOR / "sarcini").glob("*.json")):
        date = json.loads(cale.read_text(encoding="utf-8"))
        for s in date["sarcini"]:
            sarcini.append(Sarcina(s["id"], s["profil"], s["instructiune"], s["intrare"], s["criterii"]))
    return sarcini


def valideaza_sarcini(sarcini: list[Sarcina]) -> list[str]:
    """Probleme ale setului (id-uri dublate, profil necunoscut, criterii necunoscute, lipsa unui criteriu
    verificabil)."""
    cunoscute = {
        "text_din", "lungime_min", "lungime_max", "cuvinte_obligatorii", "cuvinte_interzise",
        "raspuns_exact", "diacritice",
    }  # fmt: skip
    probleme: list[str] = []
    vazute: set[str] = set()
    for s in sarcini:
        if s.id in vazute:
            probleme.append(f"{s.id}: id dublat")
        vazute.add(s.id)
        if s.profil not in SCHEME:
            probleme.append(f"{s.id}: profil necunoscut {s.profil!r}")
        if set(s.criterii) - cunoscute:
            probleme.append(f"{s.id}: criterii necunoscute {sorted(set(s.criterii) - cunoscute)}")
        if not set(s.criterii) - {"text_din"}:
            probleme.append(f"{s.id}: niciun criteriu verificabil")
        if not s.instructiune.strip() or not s.intrare.strip():
            probleme.append(f"{s.id}: instrucțiune sau intrare goală")
    return probleme


def amprenta_set(sarcini: list[Sarcina]) -> str:
    continut = json.dumps(
        [[s.id, s.profil, s.instructiune, s.intrare, s.criterii] for s in sarcini], sort_keys=True
    )
    return hashlib.sha256(continut.encode()).hexdigest()


# --- pregătire


def asigura_prompturi(db: Session) -> list[str]:
    """Aduce în bază prompturile de evaluare din `evaluare/prompturi/` (idempotent)."""
    return prompturi.sincronizeaza(db, DIRECTOR / "prompturi")


def client_intern(db: Session) -> uuid.UUID:
    """Clientul pentru care se scriu apelurile de evaluare (creat la prima rulare, cu buget propriu, larg)."""
    r = db.execute(text("SELECT id FROM clienti WHERE nume = :n"), {"n": NUME_CLIENT}).first()
    if r is not None:
        return r[0]  # type: ignore[no-any-return]
    cid = creeaza_client(db, NUME_CLIENT, actor=Actor.cli()).id
    bugete.seteaza_client(
        db, cid,
        {"apeluri_zi": 5000, "tokeni_zi": 10_000_000, "pret_umbra_zi": 50, "apeluri_luna": 50_000,
         "tokeni_luna": 100_000_000, "pret_umbra_luna": 500},
        utilizator_id=None,
    )  # fmt: skip
    return cid


# --- rularea


@dataclass(frozen=True)
class Rulare:
    id: uuid.UUID
    model: str
    stare: str
    facute: int
    total: int
    amanata_pana_la: dt.datetime | None = None
    scor: dict[str, dict[str, Any]] | None = None


def _deschide(
    db: Session, model_cod: str, profiluri: list[str], sarcini: list[Sarcina], de: uuid.UUID | None
) -> uuid.UUID:
    cand = next((c for c in registru.candidati(db) if c.cod == model_cod), None)
    if cand is None:
        raise LookupError(f"modelul {model_cod!r} nu există în registru")
    rid = new_id()
    db.execute(
        text(
            "INSERT INTO gateway_evaluari_rulari (id, model_id, model_cod, set_amprenta, profiluri, "
            "sarcini_total, pornita_de) "
            "VALUES (:i, :m, :c, :a, :p, :t, :u)"
        ),
        {"i": rid, "m": cand.model_id, "c": model_cod, "a": amprenta_set(sarcini), "p": profiluri,
         "t": len(sarcini), "u": de},
    )  # fmt: skip
    return rid


def ruleaza(
    model_cod: str,
    *,
    profiluri: list[str] | None = None,
    rulare_id: uuid.UUID | None = None,
    pe_profil: int | None = None,
    utilizator_id: uuid.UUID | None = None,
) -> Rulare:
    """Rulează sarcinile (ale `profiluri`, cel mult `pe_profil` din fiecare) pe `model_cod`. Cu
    `rulare_id` continuă o rulare amânată, fără să refacă sarcinile terminate. Nu ridică `Amanat`: oprește
    rularea (`stare = "amanata"`) și o întoarce."""
    toate = incarca_sarcini()
    alese = [s for s in toate if not profiluri or s.profil in profiluri]
    if pe_profil is not None:
        numarate: dict[str, int] = {}
        filtrate = []
        for s in alese:
            numarate[s.profil] = numarate.get(s.profil, 0) + 1
            if numarate[s.profil] <= pe_profil:
                filtrate.append(s)
        alese = filtrate
    with sesiune_agentie() as db:
        asigura_prompturi(db)
        tenant = client_intern(db)
        if rulare_id is None:
            rulare_id = _deschide(db, model_cod, sorted({s.profil for s in alese}), alese, utilizator_id)
        facute = {
            r[0]
            for r in db.execute(
                text("SELECT sarcina_id FROM gateway_evaluari_rezultate WHERE rulare_id = :r"),
                {"r": rulare_id},
            )
        }
        db.execute(
            text(
                "UPDATE gateway_evaluari_rulari SET stare = 'in_curs', amanata_pana_la = NULL WHERE id = :r"
            ),
            {"r": rulare_id},
        )
    amanata: dt.datetime | None = None
    for s in alese:
        if s.id in facute:
            continue
        rezultat = _o_sarcina(s, model_cod, tenant)
        if isinstance(rezultat, dt.datetime):
            amanata = rezultat
            break
        _scrie_rezultat(rulare_id, s, rezultat)
    return _incheie(rulare_id, model_cod, amanata)


def _o_sarcina(s: Sarcina, model_cod: str, tenant: uuid.UUID) -> dict[str, Any] | dt.datetime:
    """Rezultatul unei sarcini, sau momentul de la care merită reluat dacă cota a cerut amânare."""
    prompt = f"evaluare.{s.profil}"
    iesire: dict[str, Any] | None = None
    stare, cod, tokeni, durata = "ok", "", 0, 0
    try:
        with sesiune_tenant(tenant) as db:
            r = gateway.apeleaza(
                db, prompt=prompt, variabile={"instructiune": s.instructiune, "intrare": s.intrare},
                schema=SCHEME[s.profil], tenant_id=tenant, componenta="evaluare", prioritate=Prioritate.P3,
                profil=s.profil, model=model_cod, max_tokeni=MAX_TOKENI, temperatura=0.0,
            )  # fmt: skip
        iesire = r.iesire.model_dump(mode="json")
        tokeni, durata = r.tokeni_intrare + r.tokeni_iesire, r.durata_ms
    except gateway.Amanat as amanat:
        return amanat.pana_la
    except gateway.IesireInvalida:
        stare, cod = "invalid", "iesire_invalida"
    except gateway.ApelRefuzat as exc:
        stare, cod = "esec", exc.cod
    except EroareGateway as exc:
        stare, cod = "esec", type(exc).__name__
    ev = criterii.evalueaza(s.criterii, iesire)
    return {"stare": stare, "cod": cod, "scor": ev.scor, "detalii": ev.detalii, "raspuns": iesire,
            "tokeni": tokeni, "durata": durata}  # fmt: skip


def _scrie_rezultat(rulare_id: uuid.UUID, s: Sarcina, r: dict[str, Any]) -> None:
    with sesiune_agentie() as db:
        db.execute(
            text(
                "INSERT INTO gateway_evaluari_rezultate (rulare_id, sarcina_id, profil, stare, scor_auto, "
                "detalii, raspuns, cod_eroare, tokeni, durata_ms) VALUES (:r, :s, :p, :st, :sc, "
                "CAST(:d AS jsonb), CAST(:ra AS jsonb), :c, :t, :du) "
                "ON CONFLICT DO NOTHING"
            ),
            {"r": rulare_id, "s": s.id, "p": s.profil, "st": r["stare"], "sc": r["scor"],
             "d": json.dumps(r["detalii"]), "c": r["cod"],
             "ra": None if r["raspuns"] is None else json.dumps(r["raspuns"], ensure_ascii=False),
             "t": r["tokeni"], "du": r["durata"]},
        )  # fmt: skip
        db.execute(
            text(
                "UPDATE gateway_evaluari_rulari SET sarcini_facute = (SELECT count(*) FROM "
                "gateway_evaluari_rezultate WHERE rulare_id = :r) WHERE id = :r"
            ),
            {"r": rulare_id},
        )


def _incheie(rulare_id: uuid.UUID, model_cod: str, amanata: dt.datetime | None) -> Rulare:
    with sesiune_agentie() as db:
        rand = db.execute(
            text("SELECT sarcini_facute, sarcini_total FROM gateway_evaluari_rulari WHERE id = :r"),
            {"r": rulare_id},
        ).one()
        if amanata is not None:
            db.execute(
                text(
                    "UPDATE gateway_evaluari_rulari SET stare = 'amanata', amanata_pana_la = :a WHERE id = :r"
                ),
                {"a": amanata, "r": rulare_id},
            )
            return Rulare(rulare_id, model_cod, "amanata", int(rand[0]), int(rand[1]), amanata)
        scor = agrega(db, rulare_id)
        db.execute(
            text("UPDATE gateway_evaluari_rulari SET stare = 'terminata', terminata_la = :la WHERE id = :r"),
            {"la": ceas.acum(), "r": rulare_id},
        )
        audit.record(
            db, "gateway.evaluare_terminata", obiect_tip="model", obiect_id=model_cod, tenant_id=None,
            actor_tip="sistem",
            detalii={"model": model_cod, "rulare": str(rulare_id), "profiluri": sorted(scor)},
        )  # fmt: skip
    return Rulare(rulare_id, model_cod, "terminata", int(rand[0]), int(rand[1]), None, scor)


def agrega(db: Session, rulare_id: uuid.UUID) -> dict[str, dict[str, Any]]:
    """Recalculează scorul pe profil al rulării (automat + note umane) și îl scrie în rulare și în
    registrul de modele."""
    randuri = db.execute(
        text("SELECT profil, scor_auto, nota_umana FROM gateway_evaluari_rezultate WHERE rulare_id = :r"),
        {"r": rulare_id},
    ).all()
    pe_profil: dict[str, tuple[list[float], list[int]]] = {}
    for profil, auto, nota in randuri:
        a, n = pe_profil.setdefault(profil, ([], []))
        a.append(float(auto))
        if nota is not None:
            n.append(int(nota))
    scor: dict[str, dict[str, Any]] = {}
    for profil, (auto, note) in pe_profil.items():
        final = criterii.scor_profil(auto, note, PONDERE_UMANA)
        scor[profil] = {"final": final, "automat": round(sum(auto) / len(auto), 4), "sarcini": len(auto),
                        "note_umane": len(note)}  # fmt: skip
    model_id = db.execute(
        text("SELECT model_id FROM gateway_evaluari_rulari WHERE id = :r"), {"r": rulare_id}
    ).scalar_one()
    db.execute(
        text("UPDATE gateway_evaluari_rulari SET scor = CAST(:s AS jsonb), in_registru = true WHERE id = :r"),
        {"s": json.dumps(scor), "r": rulare_id},
    )
    for profil, v in scor.items():
        db.execute(
            text(
                "UPDATE gateway_modele SET scor = scor || jsonb_build_object(CAST(:p AS text), "
                "CAST(:v AS numeric)), actualizat_la = now() WHERE id = :m"
            ),
            {"p": profil, "v": v["final"], "m": model_id},
        )
    return scor


# --- nota umană


class NotaInvalida(ValueError):
    pass


def importa_note(db: Session, rulare_id: uuid.UUID, csv_text: str, *, utilizator_id: uuid.UUID | None) -> int:
    """Importă note umane dintr-un CSV cu coloanele `sarcina_id,nota` (1–5). Întoarce câte note s-au
    scris; tot sau nimic."""
    cititor = csv.DictReader(io.StringIO(csv_text.strip()))
    if not cititor.fieldnames or {"sarcina_id", "nota"} - set(cititor.fieldnames):
        raise NotaInvalida("CSV-ul trebuie să aibă coloanele sarcina_id și nota")
    note: list[tuple[str, int]] = []
    for rand in cititor:
        try:
            nota = int(rand["nota"])
        except (TypeError, ValueError):
            raise NotaInvalida(f"{rand.get('sarcina_id')}: nota nu e un număr") from None
        if not 1 <= nota <= 5:
            raise NotaInvalida(f"{rand['sarcina_id']}: nota trebuie să fie între 1 și 5")
        note.append((rand["sarcina_id"].strip(), nota))
    if not note:
        raise NotaInvalida("CSV-ul nu are nicio notă")
    return seteaza_note(db, rulare_id, note, utilizator_id=utilizator_id)


def seteaza_note(
    db: Session, rulare_id: uuid.UUID, note: list[tuple[str, int]], *, utilizator_id: uuid.UUID | None
) -> int:
    scrise = 0
    for sarcina, nota in note:
        r = db.execute(
            text(
                "UPDATE gateway_evaluari_rezultate SET nota_umana = :n, nota_de = :u, nota_la = now() "
                "WHERE rulare_id = :r AND sarcina_id = :s"
            ),
            {"n": nota, "u": utilizator_id, "r": rulare_id, "s": sarcina},
        )
        if r.rowcount == 0:  # type: ignore[attr-defined]
            raise NotaInvalida(f"{sarcina}: nu există în rulare")
        scrise += 1
    agrega(db, rulare_id)  # scorul din registru include acum nota umană
    audit.record(
        db, "gateway.evaluare_note", obiect_tip="rulare", obiect_id=str(rulare_id),
        utilizator_id=utilizator_id,
        tenant_id=None, detalii={"note": scrise},
    )  # fmt: skip
    return scrise


# --- citire (panou)


def istoric(db: Session, limita: int = 20) -> list[dict[str, Any]]:
    return [
        dict(r._mapping)
        for r in db.execute(
            text("SELECT * FROM gateway_evaluari_rulari ORDER BY pornita_la DESC, id DESC LIMIT :l"),
            {"l": limita},
        )
    ]


def rezultate(db: Session, rulare_id: uuid.UUID) -> list[dict[str, Any]]:
    return [
        dict(r._mapping)
        for r in db.execute(
            text("SELECT * FROM gateway_evaluari_rezultate WHERE rulare_id = :r ORDER BY sarcina_id"),
            {"r": rulare_id},
        )
    ]


def porneste(model_cod: str) -> str:
    """Pune în coadă testul comparativ pe un model (din panou). Întoarce identificatorul jobului; același
    model în același minut nu pornește de două ori."""
    from app.gateway import fluxuri
    from app.operare import motor

    with sesiune_agentie() as db:
        if not any(c.cod == model_cod for c in registru.candidati(db)):
            raise LookupError(f"modelul {model_cod!r} nu există în registru")
    return motor.trimite(
        fluxuri.evalueaza, model_cod, "", coada=fluxuri.coada_pentru(model_cod), prioritate=Prioritate.P3,
        cheie=f"evaluare-panou:{model_cod}:{ceas.acum():%Y%m%d%H%M}",
    )  # fmt: skip


def main(argv: list[str] | None = None) -> int:
    import argparse
    import sys

    ap = argparse.ArgumentParser(
        prog="python -m app.gateway.evaluare", description="Testul comparativ pe română"
    )
    ap.add_argument(
        "--model", action="append", default=[], help="furnizor/identificator; implicit: toate modelele active"
    )
    ap.add_argument("--profil", action="append", default=[])
    ap.add_argument("--pe-profil", type=int, default=None, help="doar primele N sarcini din fiecare profil")
    args = ap.parse_args(argv)
    with sesiune_agentie() as db:
        modele = args.model or [
            c.cod for c in registru.candidati(db)
            if c.stare_furnizor == "activ" and c.model_activ
            and "embeddings" not in c.capabilitati and not c.fara_cheie
        ]  # fmt: skip
    if not modele:
        print("niciun model activ de evaluat", file=sys.stderr)
        return 2
    for cod in modele:
        r = ruleaza(cod, profiluri=args.profil or None, pe_profil=args.pe_profil)
        print(f"{cod}: {r.stare} ({r.facute}/{r.total})", {p: v["final"] for p, v in (r.scor or {}).items()})
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
