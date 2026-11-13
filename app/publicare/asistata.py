"""Publicarea asistată (F6.6, H1 în mod asistat, docs/15 §15.2: „platforma pregătește pachetul complet …; îl
primești pe
telefon și postezi din două atingeri, prin meniul de partajare. Apoi lipești linkul postării, ca măsurarea să
pornească”).

În modul asistat platforma NU are niciun efect extern: publică omul, din aplicația platformei. De aceea nu
trece prin
executorul de efecte (F2.5); pachetul poartă totuși cheia de idempotență din 7.3
(client:livrabil:canal:versiune:tip),
ca o publicare automată ulterioară (F9) să recunoască ce s-a publicat deja.

1. `pregateste`: la aprobarea unei versiuni (punctul de extensie
`productie.aprobari.inregistreaza_dupa_decizie`, doar
   pentru livrabilele din calendar, adică cu brief), pachetul se construiește din conținutul VERSIUNII
   APROBATE: textul final
   (cu hashtag-urile), ora recomandată (slotul), dezvăluirea AI și pașii obligatorii (15.6: eticheta se pune
   manual când
   platforma nu are câmp în API; G11 vine în F8, până atunci orice text scris de model e marcat). Livrabilul
   trece
   `aprobat → programat` (H1).
2. `confirma`: omul lipește linkul postării; linkul trebuie să fie `https` pe domeniul canalului. Livrabilul
trece
   `programat → în publicare → publicat` (H1, cu omul ca autor al mutării, linkul în detaliile tranziției),
   evenimentul
   `publicare.asistata` pornește măsurarea (F10).
"""

import datetime as dt
import uuid
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import continut, productie, validare
from app.operare import audit, efecte, evenimente
from app.productie import Stare
from app.publicare.modele import PublicareAsistata

COMPONENTA = "H1"
TIP_EFECT = "publicare_asistata"
# Domeniile acceptate pentru linkul lipit, pe canal (gazda exactă sau un subdomeniu al ei).
DOMENII: dict[str, tuple[str, ...]] = {
    "facebook": ("facebook.com", "fb.com", "fb.watch"),
    "instagram": ("instagram.com",),
    "linkedin": ("linkedin.com", "lnkd.in"),
    "tiktok": ("tiktok.com",),
    "youtube": ("youtube.com", "youtu.be"),
}
ETICHETA_AI = "Conținut creat cu ajutorul AI"


class EroarePublicare(RuntimeError):
    """Pachetul nu se poate pregăti sau confirma (stare greșită, link greșit)."""


def link_valid(canal: str, link: str) -> str | None:
    """Nucleu pur: `None` dacă linkul e bun pentru canal, altfel motivul (în română)."""
    link = link.strip()
    if len(link) > 500:
        return "linkul e prea lung"
    try:
        p = urlsplit(link)
    except ValueError:
        return "linkul nu este o adresă validă"
    if p.scheme != "https" or not p.hostname:
        return "linkul trebuie să înceapă cu https://"
    gazda = p.hostname.lower()
    domenii = DOMENII.get(canal, ())
    if not any(gazda == d or gazda.endswith("." + d) for d in domenii):
        return f"linkul nu este pe {canal} ({', '.join(domenii) or 'canal fără publicare asistată'})"
    if p.path in ("", "/"):
        return "linkul trebuie să ducă la postare, nu la prima pagină"
    return None


def pachet_din(c: validare.Continut, lv: productie.Livrabil) -> dict[str, Any]:
    """Nucleu pur: pachetul unei versiuni de conținut."""
    hashtaguri = [str(h).lstrip("#") for h in c.campuri.get("hashtaguri", []) if str(h).strip("# ")]
    text = c.text + ("\n\n" + " ".join(f"#{h}" for h in hashtaguri) if hashtaguri else "")
    pasi = ["Deschide aplicația canalului din meniul de partajare.", "Lipește textul (e deja în clipboard)."]
    if c.model_autor:
        pasi.append(f"Bifează eticheta de conținut creat cu AI, dacă platforma o are („{ETICHETA_AI}”).")
    pasi.append("Publică, apoi copiază linkul postării și lipește-l aici.")
    pachet: dict[str, Any] = {
        "canal": lv.canal,
        "tip": lv.tip,
        "text": text,
        "hashtaguri": hashtaguri,
        "ora_recomandata": lv.termen_la.isoformat() if lv.termen_la else None,
        "dezvaluire_ai": bool(c.model_autor),
        "marcaj_comercial": False,  # [I] conținutul propriu al brandului; parteneriatele plătite vin cu F13
        "pasi_obligatorii": pasi,
    }
    if "batai" in c.campuri:
        pachet["batai"] = c.campuri[
            "batai"
        ]  # scriptul video: fișierul vine din F8; aici se publică doar textul
    return pachet


def al_versiunii(db: Session, livrabil_id: uuid.UUID, versiune: int) -> PublicareAsistata | None:
    return db.execute(
        select(PublicareAsistata).where(
            PublicareAsistata.livrabil_id == livrabil_id, PublicareAsistata.versiune == versiune
        )
    ).scalar_one_or_none()


def ale_livrabilului(db: Session, livrabil_id: uuid.UUID) -> list[PublicareAsistata]:
    return list(
        db.execute(
            select(PublicareAsistata)
            .where(PublicareAsistata.livrabil_id == livrabil_id)
            .order_by(PublicareAsistata.creat_la)
        ).scalars()
    )


def pregatite(db: Session, *, limita: int = 50) -> list[PublicareAsistata]:
    """Pachetele care așteaptă să fie publicate (toți clienții vizibili sesiunii), cele mai apropiate de
    oră primele."""
    return list(
        db.execute(
            select(PublicareAsistata)
            .where(PublicareAsistata.stare == "pregatit")
            .order_by(PublicareAsistata.pachet["ora_recomandata"].astext, PublicareAsistata.creat_la)
            .limit(limita)
        ).scalars()
    )


def publicate(db: Session, *, limita: int = 20) -> list[PublicareAsistata]:
    return list(
        db.execute(
            select(PublicareAsistata)
            .where(PublicareAsistata.stare == "publicat")
            .order_by(PublicareAsistata.publicat_la.desc())
            .limit(limita)
        ).scalars()
    )


def pregateste(
    db: Session, livrabil_id: uuid.UUID, *, utilizator_id: uuid.UUID | None = None
) -> PublicareAsistata:
    """Pachetul versiunii aprobate; livrabilul trece în `programat`. Idempotent pe versiune."""
    lv = productie.blocheaza(db, livrabil_id)
    existent = al_versiunii(db, lv.id, lv.versiune)
    if existent is not None:
        return existent
    if Stare(lv.stare) is not Stare.APROBAT:
        raise EroarePublicare(
            f"se pregătește doar un livrabil aprobat, nu „{productie.ETICHETE[Stare(lv.stare)]}”"
        )
    if lv.canal not in DOMENII:
        raise EroarePublicare(f"canalul {lv.canal} nu are publicare asistată")
    aprobare = next(
        (a for a in reversed(productie.aprobari.ale_livrabilului(db, lv.id)) if a.stare == "aprobat"), None
    )
    if aprobare is None or aprobare.versiune != lv.versiune:
        raise EroarePublicare("versiunea curentă nu este cea aprobată")
    c = validare.continut.citeste(db, lv.id, lv.versiune)
    p = PublicareAsistata(
        tenant_id=lv.tenant_id,
        livrabil_id=lv.id,
        versiune=lv.versiune,
        canal=lv.canal,
        cheie=efecte.cheia(lv.tenant_id, lv.id, lv.canal, lv.versiune, TIP_EFECT),
        pachet=pachet_din(c, lv),
    )
    db.add(p)
    db.flush()
    productie.muta(
        db,
        lv.id,
        Stare.APROBAT,
        Stare.PROGRAMAT,
        componenta=COMPONENTA,
        motiv="pachet de publicare asistată pregătit",
        utilizator_id=utilizator_id,
        versiune=lv.versiune,
        detalii={"publicare": str(p.id)},
    )
    return p


def confirma(
    db: Session, publicare_id: uuid.UUID, *, link: str, utilizator_id: uuid.UUID
) -> PublicareAsistata:
    """Omul a publicat și a lipit linkul: livrabilul devine `publicat`, iar linkul intră în sistem."""
    p = db.execute(
        select(PublicareAsistata).where(PublicareAsistata.id == publicare_id).with_for_update()
    ).scalar_one_or_none()
    if p is None:
        raise EroarePublicare("pachetul nu există")
    if p.stare != "pregatit":
        raise EroarePublicare("pachetul a fost deja publicat sau anulat")
    motiv = link_valid(p.canal, link)
    if motiv:
        raise EroarePublicare(motiv)
    link = link.strip()
    lv = productie.blocheaza(db, p.livrabil_id)
    if lv.versiune != p.versiune or Stare(lv.stare) is not Stare.PROGRAMAT:
        raise EroarePublicare("livrabilul nu mai este programat pe versiunea acestui pachet")
    detalii = {"publicare": str(p.id), "link": link, "mod": "asistat"}
    productie.muta(
        db,
        lv.id,
        Stare.PROGRAMAT,
        Stare.IN_PUBLICARE,
        componenta=COMPONENTA,
        motiv="publicat de om, din telefon",
        utilizator_id=utilizator_id,
        detalii=detalii,
    )
    productie.muta(
        db,
        lv.id,
        Stare.IN_PUBLICARE,
        Stare.PUBLICAT,
        componenta=COMPONENTA,
        motiv="linkul postării a fost lipit",
        utilizator_id=utilizator_id,
        detalii=detalii,
    )
    p.stare, p.link, p.publicat_de, p.publicat_la = "publicat", link, utilizator_id, dt.datetime.now(dt.UTC)
    db.flush()
    audit.record(
        db,
        "publicare.asistata",
        obiect_tip="livrabil",
        obiect_id=lv.id,
        utilizator_id=utilizator_id,
        tenant_id=lv.tenant_id,
        detalii={"canal": p.canal, "versiune": p.versiune, "link": link},
    )
    evenimente.emite(
        db,
        "publicare.asistata",
        sursa="publicare",
        obiect_tip="livrabil",
        obiect_id=lv.id,
        tenant_id=lv.tenant_id,
        utilizator_id=utilizator_id,
        date={"canal": p.canal, "versiune": p.versiune, "link": link, "idem": p.cheie},
    )
    return p


def dupa_decizie(
    db: Session, ap: productie.Aprobare, lv: productie.Livrabil, hotarare: productie.Hotarare
) -> None:
    """La aprobarea unui livrabil din calendar, pachetul se pregătește singur."""
    if hotarare is not productie.Hotarare.APROBAT or lv.canal not in DOMENII:
        return
    if continut.brief.al_livrabilului(db, lv.id) is None:
        return
    pregateste(db, lv.id, utilizator_id=ap.decis_de)


productie.aprobari.inregistreaza_dupa_decizie(dupa_decizie)
