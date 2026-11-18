"""Răspunsuri și escaladare în inboxul social (F12.8, docs/17 §17.8): regulile tabelului, ferestrele de
mesagerie ale rețelelor și dezvăluirea AI.

- **Ce face platforma, pe clasă** (`decide`, pur): întrebarea cu răspuns în registrul de fapte și cererea de
  preț primesc răspuns sau propunere după nivelul canalului; lauda și mesajul neclar primesc răspuns automat
  de la L2; **critica și subiectul sensibil nu primesc niciodată răspuns automat**: ajung la om, cu context
  (și, la critică, o variantă de răspuns). Spamul, înșelătoria și abuzul se ascund și se înregistrează; unul
  din `ESANTION` ascunse e marcat pentru verificarea omului. Criticile nu se șterg și nu se ascund.
- **Ferestrele** (`in_fereastra`, pur): mesaj privat doar în 24 de ore de la ultimul mesaj al persoanei; un
  singur răspuns privat la un comentariu, în 7 zile. Eticheta „agent uman” prelungește fereastra la 7 zile
  **doar pentru textul scris de un om** (o propunere a sistemului aprobată de om nu e scrisă de om). Un mesaj
  în afara ferestrei nu se trimite: rămâne „blocat”, cu motiv. Executorul reverifică la trimitere
  (`fereastra_pana_la`, refuz definitiv al conectorului).
- **Dezvăluirea AI:** orice text scris de sistem începe cu `PREFIX_AI` și se încheie cu calea către un om.
  Persoana care cere un om ajunge la om. După un refuz („nu mă interesează”) nu mai trimitem oferte în fir.
- Totul pleacă prin efectul de sistem `mesaj_social`; fiecare decizie lasă urmă (`inbox / ...`).
"""

import datetime as dt
import re
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.crm import registru
from app.crm.inbox import ETICHETE_CLASA, _norma
from app.crm.modele import CanalInbox, MesajInbox, RaspunsInbox
from app.crm.registru import CrmRefuzat
from app.finante import planuri
from app.ids import new_id
from app.operare import audit, notificari, urme
from app.operare.efecte import sistem

NIVELURI = ("L0", "L1", "L2", "L3", "L4")
FEREASTRA_MESAJ = dt.timedelta(hours=24)
FEREASTRA_AGENT_UMAN = dt.timedelta(days=7)
FEREASTRA_COMENTARIU = dt.timedelta(days=7)
ESANTION = 10  # unul din zece mesaje ascunse e verificat de om [I]
PREFIX_AI = "[Asistentul AI al agenției] "
CALE_OM = " Dacă vrei să vorbești cu cineva din echipă, scrie „om”."
CERE_OM = re.compile(r"^\s*om\s*$|vreau sa vorbesc cu (?:un )?om|cu o persoana reala|operator uman")
REFUZ = re.compile(r"nu ma intereseaza|nu multumesc|nu, multumesc|nu mai scrieti|stop|dezabonare")
# Registrul de fapte al agenției [I]: întrebări la care răspunsul e un fapt, nu o părere.
FAPTE: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"program|orar|ce ore"), "Lucrăm de luni până vineri, 10:00–17:00."),
    (
        re.compile(r"audit"),
        "Auditul site-ului e gratuit: îl ceri din pagina „Audit gratuit” și îl primești pe email.",
    ),
    (
        re.compile(r"(?:din|in) (?:alt|ce) oras|cluj|iasi|timisoara|brasov|constanta|toata tara|la distanta"),
        "Lucrăm cu firme din toată țara, la distanță.",
    ),
    (re.compile(r"contract|perioada minima|cat timp"), "Abonamentul e lunar, fără perioadă minimă."),
)


@dataclass(frozen=True)
class Decizie:
    actiune: str  # raspunde | propune | la_om | ascunde
    text: str = ""
    motiv: str = ""


def _ai(text: str) -> str:
    return PREFIX_AI + text.strip() + CALE_OM


def fapt(text: str) -> str | None:
    t = _norma(text)
    for regula, raspuns in FAPTE:
        if regula.search(t):
            return raspuns
    return None


def raspuns_pret() -> str:
    preturi = ", ".join(f"{p.nume} {p.pret_lunar} lei/lună" for p in planuri.PLANURI.values())
    pagina = f"{get_settings().site_url.rstrip('/')}/preturi"
    return f"Pachetele noastre: {preturi} (fără TVA). Detalii: {pagina}"


def decide(clasa: str, text: str, nivel: str, *, refuz_in_fir: bool = False) -> Decizie:
    """Regula tabelului din 17.8 (pură). `nivel` e nivelul de autonomie al canalului (L0–L4)."""
    automat = NIVELURI.index(nivel) >= NIVELURI.index("L2")
    t = _norma(text)
    if CERE_OM.search(t):
        return Decizie("la_om", motiv="persoana a cerut un om")
    if clasa == "spam":
        return Decizie("ascunde", motiv="spam, înșelătorie sau abuz")
    if clasa in ("critica", "sensibil"):
        varianta = (
            "Îmi pare rău pentru ce s-a întâmplat. Scrieți-mi în privat ce s-a petrecut, ca să rezolvăm."
            if clasa == "critica"
            else ""
        )
        return Decizie("la_om", varianta, motiv=f"{ETICHETE_CLASA[clasa]}: decide omul")
    if clasa == "intrebare":
        f = fapt(text)
        if f is None:
            return Decizie("la_om", motiv="întrebare fără răspuns în registrul de fapte")
        return Decizie("raspunde" if automat else "propune", _ai(f), "răspuns din registrul de fapte")
    if clasa == "cerere_pret":
        if refuz_in_fir:
            return Decizie("la_om", motiv="persoana a refuzat deja: nu insistăm")
        return Decizie("raspunde" if automat else "propune", _ai(raspuns_pret()), "răspuns din catalog")
    if clasa == "lauda":
        return Decizie("raspunde" if automat else "propune", _ai("Mulțumim frumos!"), "mulțumire scurtă")
    return Decizie(
        "raspunde" if automat else "propune",
        _ai("Nu sunt sigur că am înțeles. Ne spui pe scurt cu ce te ajutăm?"),
        "întrebare de clarificare",
    )


def in_fereastra(
    tip: str,
    ultimul_al_persoanei: dt.datetime,
    acum: dt.datetime,
    *,
    scris_de_om: bool,
    private_trimise: int = 0,
) -> tuple[bool, bool, dt.datetime]:
    """(se poate trimite, cu eticheta „agent uman”, până când). Pur."""
    if tip == "comentariu":
        pana = ultimul_al_persoanei + FEREASTRA_COMENTARIU
        return private_trimise == 0 and acum <= pana, False, pana
    pana = ultimul_al_persoanei + FEREASTRA_MESAJ
    if acum <= pana:
        return True, False, pana
    pana_om = ultimul_al_persoanei + FEREASTRA_AGENT_UMAN
    if scris_de_om and acum <= pana_om:
        return True, True, pana_om
    return False, False, pana


def _ultimul_al_persoanei(db: Session, m: MesajInbox) -> dt.datetime:
    if m.tip == "comentariu":
        return m.primit_la
    ultim = db.execute(
        select(func.max(MesajInbox.primit_la)).where(
            MesajInbox.canal == m.canal, MesajInbox.fir == m.fir, MesajInbox.tip == "mesaj"
        )
    ).scalar_one()
    return ultim or m.primit_la


def _private_trimise(db: Session, m: MesajInbox) -> int:
    return db.execute(
        select(func.count()).where(RaspunsInbox.mesaj_id == m.id, RaspunsInbox.stare == "trimis")
    ).scalar_one()


def _refuz_in_fir(db: Session, m: MesajInbox) -> bool:
    texte = db.scalars(select(MesajInbox.text).where(MesajInbox.canal == m.canal, MesajInbox.fir == m.fir))
    return any(REFUZ.search(_norma(t)) for t in texte)


def _trimite(
    db: Session, m: MesajInbox, text: str, *, autor: str, utilizator_id: uuid.UUID | None, acum: dt.datetime
) -> RaspunsInbox:
    ok, eticheta, pana = in_fereastra(
        m.tip,
        _ultimul_al_persoanei(db, m),
        acum,
        scris_de_om=autor == "om",
        private_trimise=_private_trimise(db, m),
    )
    r = RaspunsInbox(
        id=new_id(),
        mesaj_id=m.id,
        text=text[:2000],
        autor=autor,
        utilizator_id=utilizator_id,
        stare="trimis" if ok else "blocat",
        motiv="" if ok else "în afara ferestrei de mesagerie",
        eticheta_agent_uman=eticheta,
        creat_la=acum,
        trimis_la=acum if ok else None,
    )
    db.add(r)
    db.flush()
    if not ok:
        urme.inregistreaza(
            db,
            "inbox",
            "raspuns_blocat",
            rezultat="blocat",
            motiv="în afara ferestrei",
            obiect_tip="mesaj_inbox",
            obiect_id=str(m.id),
            intrari={"autor": autor, "canal": m.canal, "tip": m.tip},
        )
        return r
    payload: dict[str, Any] = {
        "actiune": "raspunde",
        "canal": m.canal,
        "fir": m.fir,
        "catre": m.autor,
        "text": r.text,
        "privat": True,
        "fereastra_pana_la": pana.isoformat(),
    }
    if eticheta:
        payload["eticheta"] = "HUMAN_AGENT"
    sistem.cere(db, "mesaj_social", cheie=f"inbox:{r.id}", payload=payload)
    m.stare = "raspuns"
    urme.inregistreaza(
        db,
        "inbox",
        "raspuns_trimis",
        obiect_tip="mesaj_inbox",
        obiect_id=str(m.id),
        actor=str(utilizator_id) if utilizator_id else None,
        iesiri={"autor": autor, "eticheta_agent_uman": eticheta, "dezvaluire_ai": autor == "sistem"},
    )
    return r


def _la_om(db: Session, m: MesajInbox, d: Decizie, acum: dt.datetime) -> None:
    m.stare = "la_om"
    if d.text:
        db.add(
            RaspunsInbox(
                mesaj_id=m.id, text=d.text, autor="sistem", stare="propus", motiv="variantă", creat_la=acum
            )
        )
    titlu = "Critică în inbox" if m.clasa == "critica" else "Mesaj pentru tine în inbox"
    registru.dupa_commit(
        db,
        lambda: notificari.notifica(
            notificari.Nivel.IMPORTANT, titlu, d.motiv[:200], url="/crm/inbox?clasa=" + m.clasa
        ),
    )
    urme.inregistreaza(
        db,
        "inbox",
        "escaladare",
        obiect_tip="mesaj_inbox",
        obiect_id=str(m.id),
        motiv=d.motiv[:200],
        iesiri={"clasa": m.clasa, "varianta": bool(d.text)},
    )


def _ascunde(db: Session, m: MesajInbox, numar: int) -> None:
    if m.clasa != "spam":
        raise CrmRefuzat("se ascund doar spamul, înșelătoriile și abuzul; criticile rămân")
    m.stare, m.de_verificat = "ascuns", numar % ESANTION == 0
    sistem.cere(
        db,
        "mesaj_social",
        cheie=f"inbox:ascunde:{m.id}",
        payload={"actiune": "ascunde", "canal": m.canal, "id_extern": m.id_extern},
    )
    urme.inregistreaza(
        db,
        "inbox",
        "ascuns",
        obiect_tip="mesaj_inbox",
        obiect_id=str(m.id),
        iesiri={"de_verificat": m.de_verificat},
    )


ADRESA = re.compile(r"[^@\s<>()]{1,64}@[^@\s<>()]{1,189}\.[a-z]{2,}", re.IGNORECASE)


def _lead_din_cerere(db: Session, m: MesajInbox) -> None:
    """Cererea de preț creează lead (17.8) dacă persoana lasă o adresă: temeiul e „a scris prima”."""
    gasit = ADRESA.search(m.text)
    if gasit is None:
        return
    try:
        registru.primeste(
            db,
            email=gasit.group(0),
            firma=f"{m.autor} ({m.canal})",
            sursa="inbox",
            dovada=f"cerere de preț pe {m.canal}",
        )
    except CrmRefuzat:
        return
    urme.inregistreaza(db, "inbox", "lead_din_cerere", obiect_tip="mesaj_inbox", obiect_id=str(m.id))


def trateaza(db: Session, acum: dt.datetime | None = None) -> dict[str, int]:
    """Aplică regulile pe mesajele noi. Întoarce câte pe acțiune (și câte blocate de fereastră)."""
    acum = acum or dt.datetime.now(dt.UTC)
    rez: dict[str, int] = {}
    ascunse = db.execute(select(func.count()).where(MesajInbox.stare == "ascuns")).scalar_one()
    noi = db.execute(
        select(MesajInbox, CanalInbox.nivel)
        .join(CanalInbox, CanalInbox.canal == MesajInbox.canal)
        .where(MesajInbox.stare == "nou")
        .order_by(MesajInbox.primit_la)
        .with_for_update(of=MesajInbox, skip_locked=True)
    ).tuples()
    for m, nivel in list(noi):
        d = decide(m.clasa, m.text, nivel, refuz_in_fir=m.clasa == "cerere_pret" and _refuz_in_fir(db, m))
        if m.clasa == "cerere_pret":
            _lead_din_cerere(db, m)
        actiune = d.actiune
        if d.actiune == "ascunde":
            ascunse += 1
            _ascunde(db, m, ascunse)
        elif d.actiune == "la_om":
            _la_om(db, m, d, acum)
        elif d.actiune == "propune":
            m.stare = "propus"
            db.add(
                RaspunsInbox(
                    mesaj_id=m.id, text=d.text, autor="sistem", stare="propus", motiv=d.motiv, creat_la=acum
                )
            )
            urme.inregistreaza(db, "inbox", "raspuns_propus", obiect_tip="mesaj_inbox", obiect_id=str(m.id))
        else:
            r = _trimite(db, m, d.text, autor="sistem", utilizator_id=None, acum=acum)
            actiune = "trimis" if r.stare == "trimis" else "blocat"
        rez[actiune] = rez.get(actiune, 0) + 1
    return rez


def raspunde_om(
    db: Session, mesaj_id: uuid.UUID, text: str, *, utilizator_id: uuid.UUID, acum: dt.datetime | None = None
) -> RaspunsInbox:
    """Răspunsul scris de om (fără prefixul AI). Poate folosi eticheta „agent uman” până la 7 zile."""
    acum = acum or dt.datetime.now(dt.UTC)
    text = text.strip()
    if not 1 <= len(text) <= 2000:
        raise CrmRefuzat("răspunsul trebuie să aibă între 1 și 2000 de caractere")
    m = db.get(MesajInbox, mesaj_id, with_for_update=True)
    if m is None or m.stare == "ascuns":
        raise CrmRefuzat("mesaj inexistent")
    for p in db.scalars(
        select(RaspunsInbox).where(RaspunsInbox.mesaj_id == m.id, RaspunsInbox.stare == "propus")
    ):
        p.stare = "inlocuit"
    r = _trimite(db, m, text, autor="om", utilizator_id=utilizator_id, acum=acum)
    audit.record(
        db,
        "crm.inbox_raspuns_om",
        obiect_tip="mesaj_inbox",
        obiect_id=m.id,
        utilizator_id=utilizator_id,
        rezultat="ok" if r.stare == "trimis" else "refuzat",
    )
    return r


def aproba_propunerea(
    db: Session, raspuns_id: uuid.UUID, *, utilizator_id: uuid.UUID, acum: dt.datetime | None = None
) -> RaspunsInbox:
    """Trimite propunerea sistemului, aprobată de om. Rămâne textul sistemului: fără „agent uman”."""
    acum = acum or dt.datetime.now(dt.UTC)
    p = db.get(RaspunsInbox, raspuns_id, with_for_update=True)
    if p is None or p.stare != "propus" or p.autor != "sistem":
        raise CrmRefuzat("propunerea nu există sau nu mai așteaptă")
    m = db.get(MesajInbox, p.mesaj_id, with_for_update=True)
    if m is None:
        raise CrmRefuzat("mesaj inexistent")
    p.stare = "inlocuit"
    text = p.text if p.text.startswith(PREFIX_AI) else _ai(p.text)
    return _trimite(db, m, text, autor="sistem", utilizator_id=utilizator_id, acum=acum)


def propuneri(db: Session, mesaj_id: uuid.UUID) -> list[RaspunsInbox]:
    return list(
        db.scalars(
            select(RaspunsInbox).where(RaspunsInbox.mesaj_id == mesaj_id).order_by(RaspunsInbox.creat_la)
        )
    )
