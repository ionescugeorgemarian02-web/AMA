# ruff: noqa: F811
"""Demonstrația F-idee „Atelierul Spița” (docs/specs/F-idee.md, „Demonstrația”). Rulează doar cu `AMA_IDEE_DIR`
(jobul `idee` din CI), unde scrie artefactele, copiate exact din biblioteca aplicației.

Fundația (brief din interviu, ghid de ton, fapt de preț, oferta de 120 lei, strategie, calendar) vine din dosarul
`tests/pilot_clienti.py` („servicii”) cu modelul FALS determinist (# SIMULAT). Prompturile de creație (`SARCINI`) au
trei surse, în ordinea:

- `AMA_PUNTE_DIR` → puntea orchestratorului: critica (`continut.critica_idee`) în `<dir>/critic/`, restul în
  `<dir>/generator/`, ca să răspundă doi agenți diferiți; fiecare răspuns se ÎNREGISTREAZĂ în `INREGISTRARE`
  (cheie `sarcina#nr`, amprenta promptului, autorul din `AMA_PUNTE_AUTOR`, ex. „generator: X / critic: Y”);
- `AMA_CHEIE_PILOT` → model Anthropic real (`AMA_PILOT_MODEL`), înregistrat la fel;
- altfel → REDAREA înregistrării, în ordine pe sarcină (o amprentă diferită e un avertisment în raport, nu eșec).
  `AMA_IDEE_FALS=1` înregistrează răspunsurile modelului fals (doar pentru mecanică, într-un fișier temporar).

`AMA_IDEE_INREGISTRARE` mută fișierul înregistrării (implicit `tests/date/idei/spita.json`). Stock: `AMA_STOCK`
(`commons` în CI); fără rețea (ex. 403), `StockSimulat`, marcat „stock simulat” în raport; în CI (`CI` setat) stock-ul
trebuie să fie real. Cadrele de material propriu (fără interogări) primesc o imagine procedurală, marcată în raport;
ideea vede inventarul (clientul nu are filmări proprii), iar cadrele proprii de filmat apar ca cereri de filmare.

    AMA_IDEE_DIR=/tmp/idee AMA_PUNTE_DIR=/tmp/punte AMA_PUNTE_AUTOR="generator: … / critic: …" \\
      AMA_TEST_PLAFON_SEC=7200 uv run pytest tests/integration/test_idee_spita.py -o faulthandler_timeout=0
"""

import datetime as dt
import hashlib
import json
import os
import re
import shutil
import uuid
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine, text

from app import creier, productie, validare
from app.continut import brief, calendar, idei, pipeline, scriere
from app.creier.compartimente import Compartiment, SursaTip
from app.db import sesiune_tenant
from app.ids import new_id
from app.media import (
    biblioteca,
    cereri,
    compozitor,
    control,
    ffmpeg,
    fluxuri,
    furnizori,
    licente,
    montaj,
    regizor,
    sabloane,
)
from app.media.modele import Activ, Randare
from app.onboarding import completare, ghid, strategie
from tests.continut_utile import model_brief, model_calendar, model_postari, model_scripturi
from tests.furnizor_fals import CerereInregistrata
from tests.integration.test_onboarding_ghid import inregistreaza, varianta
from tests.integration.test_onboarding_interviu import interviu_complet
from tests.integration.utile_productie import om  # noqa: F401
from tests.media_utile import fotografie_procedurala, model_regizor
from tests.onboarding_utile import ModelFals, model_fals, modele, prompt_complet  # noqa: F401
from tests.pilot_clienti import CAZURI
from tests.punte_orchestrator import Punte
from tests.validare_utile import fapt_aprobat, oferta_aprobata

DIR = os.getenv("AMA_IDEE_DIR")
pytestmark = [
    pytest.mark.db,
    pytest.mark.skipif(not DIR, reason="demonstrația F-idee rulează doar cu AMA_IDEE_DIR (jobul idee)"),
    pytest.mark.skipif(not ffmpeg.disponibil(), reason="ffmpeg lipsește"),
]
DOSAR = CAZURI["servicii"]
INREGISTRARE = Path(
    os.getenv("AMA_IDEE_INREGISTRARE") or Path(__file__).resolve().parents[1] / "date" / "idei" / "spita.json"
)
INCEPUT = dt.date(2026, 12, 1)  # fix: promptul (termenul slotului) nu depinde de ziua rulării
# sarcina (componenta gateway-ului) -> fraza care apare doar în promptul ei
SARCINI = {
    "continut.idei": "Propune concepte creative pentru livrabilul",
    "continut.critica_idee": "Critică conceptele de mai jos",
    "continut.brief": "Scrie brieful livrabilului",
    "continut.hookuri": "Propune deschideri pentru materialul",
    "continut.script": "Scrie scriptul video scurt",
    "continut.postare": "Scrie postarea pentru",
    "continut.repara": "Corectează materialul de mai jos",
    "media.regizor": "Ești regizorul video",
}
CRITIC = "continut.critica_idee"


def _pas(a: str, canal: str, r: str) -> dict[str, str]:
    return {"actiune": a, "canal": canal, "rezultat_asteptat": r}


STRATEGIE: dict[str, Any] = {
    "ipoteza": "Dacă arătăm ce verificăm la Revizia Urbană și spunem prețul de 120 lei dinainte, mai mulți navetiști din Sibiu programează revizia din formular.",
    "plan_30_zile": [
        _pas("Publicăm săptămânal o postare despre ce include revizia", "facebook", "primele 150 de interacțiuni"),
        _pas("Publicăm un clip scurt cu frâna și transmisia reglate", "instagram", "1000 de vizualizări"),
        _pas("Trimitem fișa reviziei celor care se programează", "email", "20 de fișe trimise"),
    ],
    "plan_90_zile": [
        _pas("Repetăm clipurile cu operațiunile reviziei, pe rând", "instagram", "15 programări din formular"),
        _pas("Răspundem la întrebările despre deviz în comentarii", "facebook", "30 de programări confirmate"),
        _pas("Cerem recenzii după fiecare revizie predată", "email", "10 recenzii noi"),
    ],
    "indicator_principal": {"nume": "Programări confirmate pentru Revizia Urbană", "unitate": "programări",
                            "tinta": 30, "mod_masurare": "Programările confirmate din formularul de pe site"},
    "prag_minim": {"valoare": 12, "unitate": "programări", "motiv": "Sub 12 programări nu acoperim timpul investit"},
    "fereastra_masurare_zile": 30,
    "criteriu_oprire": "Dacă după 45 de zile avem sub 5 programări din formular, schimbăm subiectele clipurilor.",
}  # fmt: skip
CALENDAR: dict[str, Any] = {
    "piloni": [
        {"nume": "Revizia pe înțeles", "descriere": "Ce verificăm la frâne și la transmisie, pe rând.", "pondere": 50},
        {"nume": "Naveta pe bicicletă", "descriere": "Bicicleta de oraș folosită zilnic în Sibiu.", "pondere": 30},
        {"nume": "Atelierul", "descriere": "Oamenii și bancul de lucru din atelierul din Sibiu.", "pondere": 20},
    ],
    "formate": [
        {"canal": "instagram", "tip": "script_video_scurt", "pe_saptamana": 1},
        {"canal": "facebook", "tip": "postare", "pe_saptamana": 2},
    ],
    "idei": [
        {"pilon": "Revizia pe înțeles", "subiect": "Frâna care scârțâie după ploaie", "unghi": "problemă"},
        {"pilon": "Revizia pe înțeles", "subiect": "Lanțul uns pe fiecare pinion", "unghi": "demonstrație"},
        {"pilon": "Revizia pe înțeles", "subiect": "Devizul explicat înainte de intervenție", "unghi": "încredere"},
        {"pilon": "Naveta pe bicicletă", "subiect": "Bicicleta pregătită pentru drumul de dimineață", "unghi": "beneficiu"},
        {"pilon": "Naveta pe bicicletă", "subiect": "Programarea din formular, fără telefon", "unghi": "pas simplu"},
        {"pilon": "Atelierul", "subiect": "Mecanicul care verifică uzura lanțului", "unghi": "poveste"},
    ],
}  # fmt: skip
VARIANTE_TON = [
    varianta(nume, ton, ["garantat", "reducere"], descriere=f"Atelierul sună {ton}, ca un mecanic care explică pe "
             "îndelete ce face la bicicletă.", reguli_da=[f"Numește operațiunea pe înțeles ({ton})",
             "Spune prețul dinainte"], vocabular_preferat=["revizie", "deviz", "reglaj"],
             exemple=[{"canal": "facebook", "text": f"Reglăm frâna ca etrierul să prindă discul egal ({ton})."},
                      {"canal": "email", "text": f"Bicicleta ta e gata; devizul l-ai văzut dinainte ({ton})."},
                      {"canal": "site", "text": f"Revizia Urbană: frâne și transmisie, 120 lei ({ton})."}])
    for nume, ton in (("Mecanicul calm", "calm"), ("Vecinul de atelier", "cald"), ("Ghidul practic", "practic"))
]  # fmt: skip


# --- sursa răspunsurilor de creație ----------------------------------------------------------------------------


def _amprenta(prompt: str) -> str:
    """Amprenta promptului fără identificatori (UUID-urile diferă de la o rulare la alta)."""
    p = re.sub(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", "<id>", prompt)
    return hashlib.sha256(re.sub(r"\b[0-9a-f]{32}\b", "<id>", p).encode()).hexdigest()


def _autori(sir: str) -> dict[str, str]:
    """„generator: X / critic: Y” -> {"generator": "X", "critic": "Y"}."""
    out = {}
    for parte in sir.split("/"):
        rol, _, nume = parte.partition(":")
        if nume.strip():
            out[rol.strip()] = nume.strip()
    return out


def _json_din(t: str) -> str:
    """JSON-ul dintr-un răspuns de model (fără blocul de cod din jur)."""
    m = re.search(r"\{.*\}", t, re.S)
    return m.group(0) if m else t


def _anthropic(c: CerereInregistrata, model: str) -> str:
    """# NEVERIFICAT: modelul Anthropic real răspunde cererii ajunse la furnizorul de probă (ca agentul din punte);
    gateway-ul rămâne apelantul. Rulează doar cu `AMA_CHEIE_PILOT` (secretul nu apare în cod)."""
    import httpx

    mesaje = c.corp.get("messages", [])
    sistem = "\n".join(m["content"] for m in mesaje if m.get("role") == "system")
    schema = ((c.corp.get("response_format") or {}).get("json_schema") or {}).get("schema")
    if schema:
        sistem += "\n\nRăspunde DOAR cu un obiect JSON valid după schema: " + json.dumps(
            schema, ensure_ascii=False
        )
    r = httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": os.environ["AMA_CHEIE_PILOT"], "anthropic-version": "2023-06-01"},
        json={"model": model, "max_tokens": max(4000, int(c.corp.get("max_tokens") or 0)), "system": sistem,
              "messages": [{"role": m["role"], "content": m["content"]} for m in mesaje if m.get("role") != "system"]},
        timeout=600,
    )  # fmt: skip
    r.raise_for_status()
    return _json_din("".join(b.get("text", "") for b in r.json()["content"] if b.get("type") == "text"))


class Creatie:
    """Sursa răspunsurilor la prompturile de creație: punte, model real, model fals (înregistrate) sau redare."""

    def __init__(self, modele: ModelFals) -> None:
        self.avertismente: list[str] = []
        self.ordine: dict[str, int] = defaultdict(int)
        self.punti: dict[str, Punte] = {}
        self.model = os.getenv("AMA_PILOT_MODEL", "").strip()
        if os.getenv("AMA_PUNTE_DIR"):
            d = Path(os.environ["AMA_PUNTE_DIR"])
            self.mod = "punte"
            self.punti = {"generator": Punte(d / "generator"), "critic": Punte(d / "critic")}
            self.autor = os.getenv("AMA_PUNTE_AUTOR", "").strip() or "agent extern prin punte (nedeclarat)"
        elif os.getenv("AMA_CHEIE_PILOT"):
            assert self.model, "AMA_PILOT_MODEL lipsește (identificatorul modelului Anthropic)"
            self.mod, self.autor = "anthropic", f"Anthropic {self.model}"
        elif os.getenv("AMA_IDEE_FALS") == "1":
            self.mod, self.autor = "fals", "modelul fals din teste (# SIMULAT, doar pentru mecanică)"
        else:
            assert INREGISTRARE.is_file(), (
                f"lipsește înregistrarea {INREGISTRARE}: rulează o dată cu AMA_PUNTE_DIR sau AMA_CHEIE_PILOT"
            )
            self.mod = "redare"
        if self.mod == "redare":
            self.date = json.loads(INREGISTRARE.read_text(encoding="utf-8"))
            self.autor = self.date.get("autor", "nedeclarat")
        else:
            self.date = {"descriere": "Răspunsurile prompturilor de creație ale demonstrației F-idee (Atelierul "
                         "Spița), cu prompturile platformei.", "mod": self.mod, "autor": self.autor,
                         "inregistrat_la": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
                         "raspunsuri": {}}  # fmt: skip
        fals = {f: modele.handlere[f] for f in SARCINI.values()}
        for s, f in SARCINI.items():
            modele.handlere[f] = self._handler(s, fals[f])

    def _handler(
        self, sarcina: str, fals: Callable[[CerereInregistrata], str]
    ) -> Callable[[CerereInregistrata], str]:
        return lambda c: self.raspunde(sarcina, fals, c)

    def raspunde(self, sarcina: str, fals: Callable[[CerereInregistrata], str], c: CerereInregistrata) -> str:
        self.ordine[sarcina] += 1
        cheie, amprenta = f"{sarcina}#{self.ordine[sarcina]}", _amprenta(prompt_complet(c))
        if self.mod == "redare":
            x = self.date["raspunsuri"].get(cheie)
            assert x is not None, f"înregistrarea nu are răspunsul {cheie}"
            if x.get("prompt_sha256") != amprenta:
                self.avertismente.append(
                    f"{cheie}: promptul diferă de cel înregistrat (amprentă nouă {amprenta[:12]})"
                )
            r = x["raspuns"]
            return r if isinstance(r, str) else json.dumps(r, ensure_ascii=False)
        rol = "critic" if sarcina == CRITIC else "generator"
        if self.mod == "punte":
            t = self.punti[rol].intreaba(sarcina, c)
        elif self.mod == "anthropic":
            t = _anthropic(c, self.model)
        else:
            t = fals(c)
        try:
            raspuns: Any = json.loads(t)
        except ValueError:
            raspuns = t
        self.date["raspunsuri"][cheie] = {
            "sarcina": sarcina, "nr": self.ordine[sarcina], "rol": rol, "prompt_sha256": amprenta,
            "autor": _autori(self.autor).get(rol, self.autor), "raspuns": raspuns,
        }  # fmt: skip
        INREGISTRARE.parent.mkdir(parents=True, exist_ok=True)
        INREGISTRARE.write_text(json.dumps(self.date, ensure_ascii=False, indent=1), encoding="utf-8")
        return t

    def inchide(self) -> None:
        for p in self.punti.values():
            p.inchide()


# --- fundația și materialul ----------------------------------------------------------------------------------


def _json(nume: str, date: object) -> None:
    assert DIR
    (Path(DIR) / nume).write_text(
        json.dumps(date, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )


def _fundatie(admin_engine: Engine, om: uuid.UUID, modele: ModelFals) -> tuple[uuid.UUID, list[uuid.UUID]]:
    """Clientul Spița până la calendarul aprobat (model FALS): brief, ghid, fapt, ofertă, strategie, calendar."""
    t = new_id()
    with admin_engine.begin() as c:
        c.execute(text("INSERT INTO clienti (id, nume) VALUES (:i, :n)"), {"i": t, "n": DOSAR.marca})
    sid = interviu_complet(t, om, suprascrie=DOSAR.raspunsuri)
    inregistreaza(modele, VARIANTE_TON)
    with sesiune_tenant(t, om) as db:
        completare.compune(db, sid, utilizator_id=om)
        iid, nr = completare.trimite_spre_aprobare(db, sid, utilizator_id=om)
        creier.aproba(db, iid, nr, utilizator_id=om)
        ghid.propune_variante(db, tenant_id=t, utilizator_id=om)
        iid, nr = ghid.alege(db, t, utilizator_id=om, varianta=1)
        creier.aproba(db, iid, nr, utilizator_id=om)
    fid = fapt_aprobat(
        t, om, "pret", DOSAR.produs, DOSAR.raspunsuri["preturi"],
        valoare={"numar": DOSAR.pret, "moneda": "RON", "unitate": DOSAR.unitate},
    )  # fmt: skip
    oferta_aprobata(t, om, DOSAR.produs, DOSAR.pret, destinatie="/programare", fapte=[str(fid)])
    model_calendar(modele, CALENDAR)
    with sesiune_tenant(t, om) as db:
        i, v = creier.creeaza_intrare(
            db, tenant_id=t, compartiment=Compartiment.STRATEGIE, cheie=strategie.CHEIE_STRATEGIE,
            continut=STRATEGIE, sursa=creier.Sursa(SursaTip.DECLARATIE_CLIENT), utilizator_id=om,
        )  # fmt: skip
        creier.aproba(db, i.id, v.nr, utilizator_id=om)
        sabloane.asigura_sabloane(db, t, DOSAR.marca)
        cal = calendar.propune(db, tenant_id=t, utilizator_id=om, inceput=INCEPUT)
        livrabile = calendar.aproba(db, cal.id, utilizator_id=om)
    return t, livrabile


def _primul(t: uuid.UUID, livrabile: list[uuid.UUID], tip: str) -> uuid.UUID:
    with sesiune_tenant(t) as db:
        return next(lid for lid in livrabile if (lv := productie.citeste(db, lid)) and lv.tip == tip)


class Stock:
    """Furnizorul de stock: cel din mediu (`AMA_STOCK`) sau, fără rețea, `StockSimulat` (marcat)."""

    def __init__(self) -> None:
        self.furnizor = furnizori.stock_din_mediu()
        self.real = not isinstance(self.furnizor, furnizori.StockSimulat)
        self.motiv = "" if self.real else "AMA_STOCK nu cere un furnizor real"
        furnizori.seteaza(self.furnizor)

    def cauta(self, q: str, tip: str) -> list[furnizori.RezultatStock]:
        try:
            return furnizori.cauta_stock(q, tip=tip, n=1)
        except Exception as e:  # rețea blocată (ex. 403): stock simulat, marcat; în CI e o eroare
            if not self.real:
                raise
            assert not os.getenv("CI"), f"în CI stock-ul trebuie să fie real: {e}"
            # SIMULAT: fără rețea, catalogul determinist
            self.real, self.motiv, self.furnizor = (
                False,
                f"{type(e).__name__}: {e}"[:200],
                furnizori.StockSimulat(),
            )
            furnizori.seteaza(self.furnizor)
            return furnizori.cauta_stock(q, tip=tip, n=1)


def _material(
    db: Any, t: uuid.UUID, livrabil: str, concept: dict[str, Any], stock: Stock
) -> list[dict[str, Any]]:
    """Materialul fiecărui cadru vizual: stock după interogările cadrului; materialul propriu (fără interogări),
    o imagine procedurală marcată. Subiectul activului e descrierea cadrului (storyboardul îl potrivește)."""
    assert DIR
    dest = Path(DIR) / "stock"
    dest.mkdir(exist_ok=True)
    out = []
    for i, c in enumerate(concept["cadre"], 1):
        if c.get("tip") == "text":
            continue
        subiect = " ".join(str(c.get(k, "")) for k in ("subiect", "actiune", "context") if c.get(k)).strip()
        gasit: tuple[str, furnizori.RezultatStock] | None = None
        for q in c.get("interogari", []):
            for tip in dict.fromkeys(["video" if c["tip"] == "video" else "foto", "foto"]):
                if gasite := stock.cauta(q, tip):
                    gasit = (q, gasite[0])
                    break
            if gasit:
                break
        if gasit is None:
            corp = fotografie_procedurala(samanta=100 + i, subiect=(0.5, 0.6))
            a = biblioteca.incarca(
                db, t, corp, nume_original=f"{livrabil}-cadru-{i}.jpg", sursa="stock", utilizator_id=None,
                rol_vizual="fotografie", subiect=subiect, licenta={
                    "statut": licente.STATUT_OK, "tip": "generat", "furnizor": "test", "model": "procedural",
                    "prompt": subiect, "samanta": 100 + i,
                    "conditii": "imagine procedurală de test (material propriu lipsă), nu o fotografie reală"},
            )  # fmt: skip
            sursa: dict[str, Any] = {"tip": "procedural (material propriu lipsă)", "interogare": None}
        else:
            q, r = gasit
            a = furnizori.aduce_stock(db, t, r)
            a = biblioteca.clasifica(db, a.id, "filmare" if a.categorie == "video" else "fotografie", subiect)
            sursa = {"tip": "stock", "interogare": q, "furnizor": r.furnizor, "titlu": r.identificator,
                     "autor": r.autor, "licenta": r.licenta or r.licenta_text[:120], "url_licenta": r.url_licenta,
                     "pagina": r.url, "real": stock.real}  # fmt: skip
        fisier = f"{livrabil}-cadru-{i}{Path(regizor.cale(a)).suffix}"
        shutil.copyfile(regizor.cale(a), dest / fisier)
        out.append({"livrabil": livrabil, "cadru": i, "subiect": subiect, "tip_cerut": c["tip"],
                    "activ_id": str(a.id), "categorie": a.categorie, "fisier": f"stock/{fisier}", **sursa})  # fmt: skip
    return out


def _atribuiri(material: list[dict[str, Any]], stock: Stock) -> str:
    rows = [f"# Atribuiri — {DOSAR.marca}\n", f"Stock: {'real' if stock.real else 'stock simulat'}"
            f" ({getattr(stock.furnizor, 'nume', '?')}).\n"]  # fmt: skip
    for m in material:
        if m["tip"] != "stock":
            rows.append(
                f"- {m['livrabil']}, cadrul {m['cadru']}: {m['tip']} — fără atribuire (nu e o lucrare reală)"
            )
        else:
            lic = f"[{m['licenta']}]({m['url_licenta']})" if m["url_licenta"] else m["licenta"]
            rows.append(f"- {m['livrabil']}, cadrul {m['cadru']}: „{m['titlu']}”, {m['autor']}, {lic}, "
                        f"{m['pagina']} (interogarea „{m['interogare']}”)")  # fmt: skip
    return "\n".join(rows) + "\n"


def _concepte(db: Any, lid: uuid.UUID) -> list[dict[str, Any]]:
    return [{"id": str(r.id), "runda": r.runda, "nr": r.nr, "sursa": r.sursa, "concept": r.concept,
             "note": r.note, "scor": r.scor, "obiectii": r.obiectii, "probleme": r.probleme, "ales": r.ales,
             "motiv": r.motiv, "model_autor": r.model_autor, "model_critic": r.model_critic,
             "autoevaluare": r.autoevaluare} for r in idei.concepte(db, lid)]  # fmt: skip


def test_idee_concept_stock_video_si_feed_pentru_spita(
    admin_engine: Engine, om: uuid.UUID, modele: ModelFals
) -> None:
    assert DIR
    Path(DIR).mkdir(parents=True, exist_ok=True)
    # modelul fals pentru tot ce nu e sursa de creație (și răspunsul de mecanică în modul `fals`)
    model_brief(modele)
    model_scripturi(modele)
    model_postari(modele)
    model_regizor(modele)
    sursa = Creatie(modele)
    stock = Stock()
    raport: dict[str, Any] = {"client": DOSAR.marca, "oferta": f"{DOSAR.pret} lei", "mod_creatie": sursa.mod,
                              "autor_creatie": sursa.autor, "inregistrare": str(INREGISTRARE)}  # fmt: skip
    try:
        t, livrabile = _fundatie(admin_engine, om, modele)
        lids = {tip: _primul(t, livrabile, tip) for tip in ("script_video_scurt", "postare")}
        ideile, critica, alese = {}, {}, {}
        for tip, lid in lids.items():
            assert pipeline.idee_si_brief(t, lid) is None, f"ideea pentru {tip} a ajuns la om"
            with sesiune_tenant(t) as db:
                assert scriere.scrie(db, lid) is not None, f"autorul {tip} a eșuat"
                rows = _concepte(db, lid)
            ideile[tip] = [r["concept"] for r in rows if r["sursa"] == "propus" and r["runda"] == 1]
            critica[tip] = [{k: r[k] for k in ("runda", "nr", "sursa", "note", "scor", "obiectii", "probleme",
                             "model_critic", "autoevaluare")} for r in rows]  # fmt: skip
            ales = next(r for r in rows if r["ales"])
            with sesiune_tenant(t) as db:
                filmari = [
                    c.cerere for c in cereri.deschise(db, t, lid) if c.versiune == cereri.VERSIUNE_IDEE
                ]
            alese[tip] = {"concept": ales["concept"], "motiv": ales["motiv"], "sursa": ales["sursa"],
                          "scor": ales["scor"], "model_autor": ales["model_autor"],
                          "cereri_filmare": filmari}  # fmt: skip
            # clientul nu are filmări proprii: fiecare cadru propriu al conceptului ales se cere filmat
            assert len(filmari) == len(ales["concept"]["de_filmat"]), (filmari, ales["motiv"])
        _json("idei.json", ideile)
        _json("critica.json", critica)
        _json("concept_ales.json", alese)

        with sesiune_tenant(t) as db:
            continut = {tip: validare.continut.citeste(db, lid) for tip, lid in lids.items()}
            sc, post = continut["script_video_scurt"], continut["postare"]
            _json("script.json", sc.campuri)
            _json("postare.json", post.campuri)
            (Path(DIR) / "postare.txt").write_text(post.text, encoding="utf-8")
            material = [m for tip in lids for m in _material(db, t, tip, alese[tip]["concept"], stock)]
        (Path(DIR) / "atribuiri.md").write_text(_atribuiri(material, stock), encoding="utf-8")

        lid = lids["script_video_scurt"]
        rid = fluxuri.pregateste_script(str(t), str(lid), str(sc.versiune))
        assert rid and rid != fluxuri.BLOCAT_MATERIAL, rid
        with sesiune_tenant(t) as db:
            r = db.get(Randare, uuid.UUID(rid))
            assert r is not None
            r = montaj.executa(db, r)
            video = db.get(Activ, r.activ_id)
            assert video is not None
            b = brief.al_livrabilului(db, lids["postare"])
            assert b is not None
            titlu = brief.titlu_imagine(alese["postare"]["concept"], DOSAR.produs)
            feed = compozitor.exporta(db, t, DOSAR.marca, dict(b.continut), {"titlu": titlu})
            v = control.verdict_editorial(db, t, lid, randare=r, imagini=feed.active)
            shutil.copyfile(regizor.cale(video), Path(DIR) / "video.mp4")
            shutil.copyfile(regizor.cale(feed.active[0]), Path(DIR) / "feed.png")
            plansa = biblioteca.citeste_activ(db, uuid.UUID(v["plansa_activ_id"]))
            assert plansa is not None
            shutil.copyfile(regizor.cale(plansa), Path(DIR) / "plansa.png")
            (Path(DIR) / "subtitrari.srt").write_text(
                r.masuratori.get("subtitrari_srt", ""), encoding="utf-8"
            )
            sb = r.masuratori["storyboard"]
            pe_activ = {m["activ_id"]: m for m in material}
            _json("storyboard.json", {**sb, "scene": [{**s, "material": pe_activ.get(s.get("activ_id") or "")}
                                                      for s in sb["scene"]], "cadre": material})  # fmt: skip
            info = ffmpeg.probe(regizor.cale(video))
            vs = next(s for s in info["streams"] if s["codec_type"] == "video")
            raport.update({
                "stock": "real" if stock.real else f"stock simulat ({stock.motiv})",
                "furnizor_stock": getattr(stock.furnizor, "nume", "?"),
                "simulate": ["fundația (brief, ghid, strategie, calendar): modelul fals determinist"]
                + ([] if stock.real else ["stock simulat: imagini și clipuri deterministe, nu reale"])
                + (["prompturile de creație: modelul fals"] if sursa.mod == "fals" or "SIMULAT" in sursa.autor else [])
                + [f"cadrul {m['cadru']} ({m['livrabil']}): imagine procedurală" for m in material
                   if m["tip"] != "stock"],
                "concept_ales": {tip: {"titlu": a["concept"]["titlu"], "motiv": a["motiv"]} for tip, a in alese.items()},
                "G6": r.control["G6"]["rezultat"],
                "editorial": v["rezultat"],
                "motiv_editorial": v["mesaj"],
                "video": {"latime": vs["width"], "inaltime": vs["height"], "durata": float(info["format"]["duration"]),
                          "pista_audio": any(s["codec_type"] == "audio" for s in info["streams"]),
                          "subtitrari": bool(r.masuratori.get("subtitrari_srt"))},
                "imagine_feed": {"macheta": feed.macheta, "nota": feed.nota},
                "scene": [{"scena": s["scena"], "sursa": s["sursa"], "activ": s.get("activ_id"), "motiv": s["motiv"]}
                          for s in sb["scene"]],
            })  # fmt: skip
            if v["rezultat"] != "trece":
                raport["respins_editorial"] = v["motive"]
        assert len(ideile["script_video_scurt"]) == idei.NUMAR_CONCEPTE == len(ideile["postare"])
        assert r.control["G6"]["rezultat"] == "trece", r.control["G6"]
        assert (vs["width"], vs["height"]) == (1080, 1920) and raport["video"]["pista_audio"]
        assert raport["video"]["subtitrari"]
        assert all(s["sursa"] == "activ" for s in sb["scene"]), sb["scene"]
        assert len(v["cadre"]) >= 1 and v["plansa_activ_id"]
    finally:
        raport["avertismente"] = sursa.avertismente
        _json("raport.json", raport)
        sursa.inchide()
        furnizori.seteaza(None)
