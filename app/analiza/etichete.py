"""Legarea rezultatelor de etichete (F10.3, K2, docs/11 §11.4, docs/13 §13.4).

Fiecare postare publicată primește un rând cu etichetele ei și cu recompensa, ca rezultatele să poată fi
sortate și comparate după tiparul de hook, format, slot, pilon și unghi. De aici citesc tablourile (F10.4),
raportul (F10.5) și alegerea adaptivă (F11.3).

- **Etichetele** vin din ce există deja, fără niciun model: tiparul hook-ului ales (`variante_hook`),
  formatul (tipul livrabilului; la video și formatul de montaj A/B/E al randării terminate), pilonul și
  unghiul din intrarea de calendar, ziua săptămânii și ora locală (Europe/București) a publicării. O etichetă
  necunoscută rămâne goală, nu se ghicește.
- **Recompensa** (11.4), nucleu pur:
  - video cu curbă de retenție: retenția medie (`retentie_medie`);
  - altfel: interacțiunile (aprecieri + comentarii + distribuiri + salvări) raportate la afișări; dacă
    platforma nu dă afișări, la acoperire, apoi la vizualizări (`interactiuni_pe_afisari`). Fără numitor
    sau cu numitor zero nu există recompensă (nu se inventează).
  Se ia din citirea de la 72 de ore; dacă aceea lipsește, din prima citire reușită de după (7 zile, 28 de
  zile), iar intervalul se ține pe rând. Tipurile diferite de recompensă nu se amestecă în medii.
- **Când.** Colectorul cheamă `leaga_postarea` după fiecare citire reușită (și după cifrele introduse de om).
"""

import datetime as dt
import uuid
import zoneinfo
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app import continut, productie
from app.analiza import retentie
from app.analiza.modele import EtichetePostare, MetriciPostare
from app.ids import new_id

FUS = zoneinfo.ZoneInfo("Europe/Bucharest")
ZILE = ("luni", "marți", "miercuri", "joi", "vineri", "sâmbătă", "duminică")
INTERVALE_RECOMPENSA = ("72h", "7z", "28z")
INTERACTIUNI = ("aprecieri", "comentarii", "distribuiri", "salvari")
NUMITORI = ("afisari", "acoperire", "vizualizari")
ETICHETE_RECOMPENSA = {
    "interactiuni_pe_afisari": "interacțiuni la 100 de afișări",
    "retentie_medie": "retenție medie",
}
# Câmpurile după care se poate grupa și numele lor pe ecran.
GRUPARI: dict[str, str] = {
    "tipar_hook": "Tiparul de hook",
    "format": "Formatul",
    "slot": "Slotul (ziua și ora)",
    "pilon": "Pilonul",
    "unghi": "Unghiul",
    "canal": "Canalul",
}
ETICHETE_HOOK = {
    "intrebare": "întrebare",
    "contraintuitiv": "afirmație contraintuitivă",
    "rezultat": "rezultat arătat",
    "greseala": "greșeală frecventă",
    "cifra": "cifră",
    "poveste": "poveste în trei cuvinte",
    "inainte_dupa": "înainte și după",
}
NECUNOSCUT = "(fără etichetă)"


def slot(publicat_la: dt.datetime) -> tuple[int, int]:
    """Ziua săptămânii (1 = luni … 7 = duminică) și ora, în fusul afacerii."""
    local = publicat_la.astimezone(FUS)
    return local.isoweekday(), local.hour


def eticheta_slot(zi: int, ora: int) -> str:
    return f"{ZILE[zi - 1]}, ora {ora:02d}"


def recompensa(valori: dict[str, Any], retentie_medie: float | None = None) -> tuple[float, str] | None:
    """Nucleu pur (11.4). Întoarce (valoarea, tipul) sau `None` dacă cifrele nu ajung pentru o recompensă."""
    if retentie_medie is not None:
        return round(retentie_medie, 4), "retentie_medie"
    numitor = next((int(valori[k]) for k in NUMITORI if isinstance(valori.get(k), int)), None)
    prezente = [int(valori[k]) for k in INTERACTIUNI if isinstance(valori.get(k), int)]
    if not numitor or not prezente:
        return None
    return round(sum(prezente) / numitor, 4), "interactiuni_pe_afisari"


def format_video(lista: dict[str, Any] | None) -> str:
    """Nucleu pur: formatul de montaj (A, B, E; docs/14) din lista de decizii a randării, ca etichetă."""
    cod = str((lista or {}).get("format", "")).lower()
    return f"video_{cod}" if cod in ("a", "b", "e") else "video"


def _format(db: Session, lv: productie.Livrabil) -> str:
    if lv.tip != "video":
        return lv.tip
    from app.media.modele import Randare

    lista = db.execute(
        select(Randare.lista)
        .where(Randare.livrabil_id == lv.id, Randare.stare == "gata")
        .order_by(Randare.creat_la.desc())
        .limit(1)
    ).scalar_one_or_none()
    return format_video(lista)


def _etichete(db: Session, lv: productie.Livrabil) -> dict[str, str]:
    aleasa = next((v for v in continut.scriere.variante(db, lv.id) if v.ales), None)
    intrare = continut.calendar.intrarea_livrabilului(db, lv.id)
    return {
        "tipar_hook": aleasa.tipar if aleasa is not None else "",
        "format": _format(db, lv),
        "pilon": intrare.pilon[:80] if intrare is not None else "",
        "unghi": intrare.unghi[:300] if intrare is not None else "",
    }


def _recompensa_din_citiri(db: Session, lv: productie.Livrabil, canal: str) -> tuple[float, str, str] | None:
    citiri = {
        r.interval: r
        for r in db.execute(
            select(MetriciPostare).where(
                MetriciPostare.livrabil_id == lv.id,
                MetriciPostare.canal == canal,
                MetriciPostare.stare == "citit",
                MetriciPostare.interval.in_(INTERVALE_RECOMPENSA),
            )
        ).scalars()
    }
    interval = next((i for i in INTERVALE_RECOMPENSA if i in citiri), None)
    if interval is None:
        return None
    medie: float | None = None
    if lv.tip == "video":
        curba = retentie.a_livrabilului(db, lv.id, canal)
        if curba is not None:
            medie = retentie.rezumat(retentie.puncte(curba)).medie
    rez = recompensa(dict(citiri[interval].valori), medie)
    return None if rez is None else (rez[0], rez[1], interval)


def leaga(
    db: Session, livrabil_id: uuid.UUID, canal: str, publicat_la: dt.datetime
) -> EtichetePostare | None:
    """Scrie sau împrospătează rândul postării: etichetele și, dacă există citirea, recompensa."""
    lv = productie.citeste(db, livrabil_id)
    if lv is None:
        return None
    zi, ora = slot(publicat_la)
    rec = _recompensa_din_citiri(db, lv, canal)
    date: dict[str, Any] = {
        **_etichete(db, lv),
        "publicat_la": publicat_la,
        "zi_saptamana": zi,
        "ora": ora,
        "recompensa": rec[0] if rec else None,
        "recompensa_tip": rec[1] if rec else None,
        "recompensa_interval": rec[2] if rec else None,
        "actualizat_la": dt.datetime.now(dt.UTC),
    }
    db.execute(
        pg_insert(EtichetePostare)
        .values(id=new_id(), tenant_id=lv.tenant_id, livrabil_id=livrabil_id, canal=canal, **date)
        .on_conflict_do_update(constraint="etichete_postari_unic", set_=date)
    )
    return db.execute(
        select(EtichetePostare)
        .where(EtichetePostare.livrabil_id == livrabil_id, EtichetePostare.canal == canal)
        .execution_options(populate_existing=True)
    ).scalar_one()


def a_postarii(db: Session, livrabil_id: uuid.UUID, canal: str) -> EtichetePostare | None:
    return db.execute(
        select(EtichetePostare).where(
            EtichetePostare.livrabil_id == livrabil_id, EtichetePostare.canal == canal
        )
    ).scalar_one_or_none()


def valoare(e: EtichetePostare, dupa: str) -> str:
    """Valoarea afișată a etichetei după care se grupează."""
    if dupa == "slot":
        return eticheta_slot(e.zi_saptamana, e.ora)
    if dupa == "tipar_hook":
        return ETICHETE_HOOK.get(e.tipar_hook, e.tipar_hook) or NECUNOSCUT
    return str(getattr(e, dupa) or "") or NECUNOSCUT


@dataclass
class Grup:
    """Postările cu aceeași valoare a unei etichete."""

    valoare: str
    postari: list[EtichetePostare] = field(default_factory=list)

    def medii(self) -> dict[str, tuple[int, float]]:
        """Pe tip de recompensă: câte postări au recompensă și media lor. Tipurile nu se amestecă."""
        pe_tip: dict[str, list[float]] = {}
        for p in self.postari:
            if p.recompensa is not None and p.recompensa_tip:
                pe_tip.setdefault(p.recompensa_tip, []).append(p.recompensa)
        return {t: (len(v), round(sum(v) / len(v), 4)) for t, v in pe_tip.items()}

    def scor(self, tip: str) -> float:
        return self.medii().get(tip, (0, -1.0))[1]


def grupeaza(
    db: Session,
    dupa: str,
    *,
    tenant_id: uuid.UUID | None = None,
    de_la: dt.datetime | None = None,
    limita: int = 2000,
) -> list[Grup]:
    """Postările etichetate, grupate după `dupa` (una dintre `GRUPARI`). Grupurile sunt ordonate după media
    recompensei celei mai răspândite, descrescător; în grup, postările cu recompensa cea mai mare primele."""
    if dupa not in GRUPARI:
        raise ValueError(f"grupare necunoscută: {dupa}")
    q = select(EtichetePostare).order_by(EtichetePostare.publicat_la.desc()).limit(limita)
    if tenant_id is not None:
        q = q.where(EtichetePostare.tenant_id == tenant_id)
    if de_la is not None:
        q = q.where(EtichetePostare.publicat_la >= de_la)
    grupuri: dict[str, Grup] = {}
    numar_pe_tip: dict[str, int] = {}
    for e in db.execute(q).scalars():
        grupuri.setdefault(valoare(e, dupa), Grup(valoare(e, dupa))).postari.append(e)
        if e.recompensa_tip:
            numar_pe_tip[e.recompensa_tip] = numar_pe_tip.get(e.recompensa_tip, 0) + 1
    principal = max(numar_pe_tip, key=lambda t: numar_pe_tip[t]) if numar_pe_tip else ""
    for g in grupuri.values():
        g.postari.sort(key=lambda p: (p.recompensa is None, -(p.recompensa or 0.0)))
    return sorted(grupuri.values(), key=lambda g: (-g.scor(principal), g.valoare))
