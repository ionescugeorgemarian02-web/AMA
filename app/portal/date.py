"""Exportul și ștergerea datelor clientului (F7.7, docs/19 §19.2 „Date”, docs/21).

- `exporta`: o arhivă ZIP cu fiecare tabel care are `tenant_id` (rândurile clientului, ca JSON; RLS pe
clientul
  sesiunii și filtrul explicit pe client), plus fișierele din biblioteca de active și un `manifest.json`.
- `cere_stergerea`: titularul confirmă; cererea se înregistrează și ștergerea rulează ca job durabil
  (`date.sterge`), prin `app.db.stergere` (singura operație ca proprietar al schemei). Se păstrează
  jurnalul de
  audit și cererea însăși; utilizatorii clientului se anonimizează; fișierele de pe disc se șterg."""

import datetime as dt
import io
import json
import shutil
import uuid
import zipfile
from pathlib import Path
from typing import Any

from sqlalchemy import DateTime, Text, event, func, select, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from app.config import get_settings
from app.db import sesiune_agentie
from app.db.stergere import sterge_client
from app.ids import new_id
from app.logging import get_logger
from app.media import biblioteca
from app.operare import audit, motor

log = get_logger("app.portal.date")
CONFIRMARE = "ȘTERGE"
TABELE = """SELECT c.relname FROM pg_class c
JOIN pg_attribute a ON a.attrelid = c.oid AND a.attname = 'tenant_id' AND a.attnum > 0 AND NOT a.attisdropped
WHERE c.relnamespace = 'public'::regnamespace AND c.relkind = 'r' AND has_table_privilege(c.oid, 'SELECT')
ORDER BY 1"""


class Baza(DeclarativeBase):
    pass


class CerereStergere(Baza):
    __tablename__ = "cereri_stergere"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    cerut_de: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    stare: Mapped[str] = mapped_column(Text, default="cerut")
    rezultat: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    creat_la: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    executat_la: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class CerereInvalida(ValueError):
    pass


def exporta(db: Session, tenant_id: uuid.UUID, *, utilizator_id: uuid.UUID | None) -> bytes:
    buf = io.BytesIO()
    manifest: dict[str, Any] = {
        "client": str(tenant_id),
        "generat_la": dt.datetime.now(dt.UTC).isoformat(),
        "tabele": {},
        "fisiere": [],
    }
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for (tabel,) in db.execute(text(TABELE)).all():
            rows = (
                db.execute(
                    text(f'SELECT row_to_json(x) FROM public."{tabel}" x WHERE x.tenant_id = :t'),  # noqa: S608
                    {"t": tenant_id},
                )
                .scalars()
                .all()
            )
            manifest["tabele"][tabel] = len(rows)
            z.writestr(f"date/{tabel}.json", json.dumps(rows, ensure_ascii=False, indent=1, default=str))
        for a in biblioteca.ale_clientului(db, tenant_id, limita=100_000):
            try:
                z.writestr(f"fisiere/{Path(a.cale).name}", biblioteca.citeste_fisier(a))
                manifest["fisiere"].append({"fisier": Path(a.cale).name, "nume_original": a.nume_original})
            except OSError:
                manifest["fisiere"].append({"fisier": Path(a.cale).name, "lipsa": True})
        z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=1))
    audit.record(
        db,
        "date.exportate",
        obiect_tip="client",
        obiect_id=tenant_id,
        tenant_id=tenant_id,
        utilizator_id=utilizator_id,
        detalii={"tabele": len(manifest["tabele"])},
    )
    return buf.getvalue()


def cerere_deschisa(db: Session, tenant_id: uuid.UUID) -> CerereStergere | None:
    return db.execute(
        select(CerereStergere).where(CerereStergere.tenant_id == tenant_id, CerereStergere.stare == "cerut")
    ).scalar_one_or_none()


def cere_stergerea(
    db: Session, tenant_id: uuid.UUID, *, utilizator_id: uuid.UUID, confirmare: str
) -> CerereStergere:
    if confirmare.strip() != CONFIRMARE:
        raise CerereInvalida(f"scrie „{CONFIRMARE}” ca să confirmi")
    existenta = cerere_deschisa(db, tenant_id)
    if existenta is not None:
        return existenta
    c = CerereStergere(tenant_id=tenant_id, cerut_de=utilizator_id)
    db.add(c)
    db.flush()
    audit.record(
        db,
        "date.stergere_ceruta",
        obiect_tip="client",
        obiect_id=tenant_id,
        tenant_id=tenant_id,
        utilizator_id=utilizator_id,
    )
    cid = c.id

    def dupa(_s: Session) -> None:
        try:
            motor.trimite(sterge, str(tenant_id), str(cid), cheie=f"stergere:{cid}")
        except Exception:  # cererea rămâne deschisă; se reia din panou
            log.warning("ștergerea nu a pornit", extra={"cerere": str(cid)})

    event.listen(db, "after_commit", dupa, once=True)
    return c


def executa(tenant_id: uuid.UUID, cerere_id: uuid.UUID) -> dict[str, int]:
    with sesiune_agentie() as db:
        c = db.get(CerereStergere, cerere_id)
        if c is None or c.stare != "cerut" or c.tenant_id != tenant_id:
            return {}
    sterse = sterge_client(tenant_id)
    shutil.rmtree(Path(get_settings().media_dir) / str(tenant_id), ignore_errors=True)
    with sesiune_agentie() as db:
        c = db.execute(
            select(CerereStergere).where(CerereStergere.id == cerere_id).with_for_update()
        ).scalar_one()
        c.stare, c.rezultat, c.executat_la = "executat", sterse, dt.datetime.now(dt.UTC)
        audit.record(
            db,
            "date.sterse",
            obiect_tip="client",
            obiect_id=tenant_id,
            tenant_id=tenant_id,
            actor_tip="sistem",
            detalii={"randuri": sum(sterse.values()), "tabele": len(sterse)},
        )
    return sterse


@motor.pas(reincercari=2, pauza_sec=5.0)
def _pas_sterge(tenant_id: str, cerere_id: str) -> int:
    return sum(executa(uuid.UUID(tenant_id), uuid.UUID(cerere_id)).values())


@motor.flux("date.sterge")
def sterge(tenant_id: str, cerere_id: str) -> int:
    return _pas_sterge(tenant_id, cerere_id)
