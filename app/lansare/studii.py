"""Studiile de caz (F15.6, docs/25 §25.5 „două studii de caz sunt publicate”; șablonul în
`docs/sabloane/studiu-de-caz.md`).

`ciorna_din_pilot` pornește studiul din cifrele măsurate ale clientului (indicatorii pilotului, din urme):
situația și acțiunea le scrie omul, rezultatul are cifrele puse automat. Se publică doar cu acordul clientului
(constrângere și în bază); pagina publică `/site/studii-de-caz` arată doar studiile publicate.
"""

import datetime as dt
import re
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.lansare import pilot
from app.lansare.modele import PilotClient, StudiuCaz
from app.operare import audit


class StudiuInvalid(ValueError):
    pass


def _slug(titlu: str) -> str:
    import unicodedata

    s = unicodedata.normalize("NFKD", titlu.lower()).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:80] or "studiu"


def ciorna_din_pilot(
    db: Session, tenant_id: uuid.UUID, *, titlu: str, situatie: str, actiune: str, azi: dt.date | None = None
) -> StudiuCaz:
    p = db.get(PilotClient, tenant_id)
    azi = azi or dt.datetime.now(dt.UTC).date()
    de_la = p.inceput if p else azi - dt.timedelta(days=28)
    ind = pilot.indicatori(db, tenant_id, de_la, azi + dt.timedelta(days=1))
    rata = ind.rata_aprobare_din_prima
    rezultat = (
        f"În {(azi - de_la).days + 1} zile: {ind.decise} livrabile decise, "
        + (f"{rata:.0%} aprobate din prima" if rata is not None else "aprobarea din prima nemăsurată")
        + f", {ind.incidente_critice} incidente critice, {ind.minute_om} minute de lucru ale clientului."
    )
    if len(titlu.strip()) < 3:
        raise StudiuInvalid("titlul are cel puțin 3 caractere")
    s = StudiuCaz(
        tenant_id=tenant_id, slug=f"{_slug(titlu)}-{uuid.uuid4().hex[:4]}", titlu=titlu.strip()[:120],
        situatie=situatie.strip()[:3000], actiune=actiune.strip()[:3000], rezultat=rezultat,
        cifre={"de_la": de_la.isoformat(), "pana_la": azi.isoformat(), **ind.ca_dict()},
    )  # fmt: skip
    db.add(s)
    db.flush()
    return s


def publica(db: Session, studiu_id: uuid.UUID, *, acord_client: bool, utilizator_id: uuid.UUID) -> StudiuCaz:
    s = db.get(StudiuCaz, studiu_id)
    if s is None:
        raise StudiuInvalid("studiul nu există")
    if not acord_client:
        raise StudiuInvalid("studiul se publică doar cu acordul scris al clientului")
    if not (s.situatie and s.actiune):
        raise StudiuInvalid("completează situația și acțiunea")
    s.acord_client, s.stare, s.publicat_la = True, "publicat", dt.datetime.now(dt.UTC)
    audit.record(db, "lansare.studiu_publicat", obiect_tip="studiu_caz", obiect_id=s.id,
                 tenant_id=s.tenant_id,
                 utilizator_id=utilizator_id)  # fmt: skip
    db.flush()
    return s


def publicate(db: Session) -> list[StudiuCaz]:
    q = select(StudiuCaz).where(StudiuCaz.stare == "publicat").order_by(StudiuCaz.publicat_la.desc())
    return list(db.execute(q).scalars())


def toate(db: Session) -> list[StudiuCaz]:
    return list(db.execute(select(StudiuCaz).order_by(StudiuCaz.creat_la.desc())).scalars())
