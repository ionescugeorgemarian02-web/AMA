"""Vocea proprie antrenată (F16.4, docs/14 §14.2 și §14.4, ADR-10): acordul vorbitorului, antrenarea o singură
dată, sinteza prin adaptorul TTS, revocarea.

Reguli (D-026):
1. Fără acord scris valabil (`voce_consimtaminte`: amprenta documentului semnat, scopurile) nu se
antrenează și nu
   se sintetizează nimic; scopul cererii (de ex. `reclame`) trebuie să fie în acord.
2. Antrenarea cere minimum `MINUTE_MINIME` de înregistrări [I] (14.2: ~2 ore); modelul rezultat e legat
de acord.
3. Narațiunea cu vocea proprie are licența `voce_sintetizata`, statut `verificata`, cu acordul drept
dovadă, deci
   intră în pașaport ca voce generată (etichetă AI), ca orice voce sintetică.
4. Revocarea acordului retrage modelul și trece narațiunile deja făcute pe `refuzata`: nu mai intră în niciun
   fișier final (`licente.probleme`, `voce.permite_publicarea`).

# SIMULAT: antrenarea (`AntrenorSimulat`) și adaptorul TTS (`MotorVoceProprieSimulat`): fără GPU și fără date
reale; la migrare, antrenarea pe GPU închiriat și modelul Piper/ONNX în spatele aceluiași adaptor.
"""

import datetime as dt
import hashlib
import uuid
from dataclasses import dataclass
from typing import Any, Protocol

from sqlalchemy import DateTime, Numeric, Text, select, text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.ids import new_id
from app.media import voce
from app.media.modele import BazaMedia
from app.operare import audit, urme

SCOPURI = ("continut_organic", "reclame", "raspunsuri")
MINUTE_MINIME = 90.0  # [I] minute de înregistrări curate (14.2: ~2 ore recomandate)
MOTOR = "proprie"


class Consimtamant(BazaMedia):
    __tablename__ = "voce_consimtaminte"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    vorbitor: Mapped[str] = mapped_column(Text)
    document_sha256: Mapped[str] = mapped_column(Text)
    scopuri: Mapped[list[str]] = mapped_column(ARRAY(Text))
    acordat_la: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    inregistrat_de: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    revocat_la: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    motiv_revocare: Mapped[str] = mapped_column(Text, default="")


class ModelVoce(BazaMedia):
    __tablename__ = "voce_modele"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    consimtamant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    stare: Mapped[str] = mapped_column(Text)
    minute_inregistrate: Mapped[float] = mapped_column(Numeric(8, 2))
    motor: Mapped[str] = mapped_column(Text)
    model_ref: Mapped[str] = mapped_column(Text)
    creat_la: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    retras_la: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class FaraConsimtamant(PermissionError):
    """Lipsește acordul valabil al vorbitorului pentru ce se cere."""


class InregistrariInsuficiente(ValueError):
    pass


@dataclass(frozen=True)
class Inregistrare:
    """O înregistrare a vorbitorului: amprenta fișierului și durata lui (fișierele stau în biblioteca de
    active)."""

    sha256: str
    durata_sec: float


class Antrenor(Protocol):
    def antreneaza(self, inregistrari: list[Inregistrare], *, eticheta: str) -> str:
        """Înregistrările -> referința modelului (calea fișierului ONNX, la migrare)."""
        ...


class AntrenorSimulat:
    """# SIMULAT: referința modelului e amprenta înregistrărilor (aceleași date -> același model)."""

    def antreneaza(self, inregistrari: list[Inregistrare], *, eticheta: str) -> str:
        h = hashlib.sha256("".join(sorted(i.sha256 for i in inregistrari)).encode()).hexdigest()[:16]
        return f"simulat://voce-proprie/{eticheta}/{h}"


class MotorVoceProprieSimulat(voce.MotorVoceSimulat):
    """# SIMULAT: adaptorul TTS al vocii proprii (aceeași interfață `MotorVoce`); la migrare, modelul antrenat
    (`ProfilVoce.model` = referința lui) rulează local pe CPU, ca Piper (ADR-10)."""


_antrenor: Antrenor = AntrenorSimulat()


def seteaza_antrenor(a: Antrenor | None) -> None:
    global _antrenor
    _antrenor = a or AntrenorSimulat()


def amprenta(document: bytes) -> str:
    return hashlib.sha256(document).hexdigest()


def inregistreaza_consimtamant(
    db: Session,
    tenant_id: uuid.UUID,
    *,
    vorbitor: str,
    document: bytes,
    scopuri: list[str],
    utilizator_id: uuid.UUID | None,
) -> Consimtamant:
    """Acordul scris (documentul semnat, ca octeți): se păstrează amprenta lui; scopurile din `SCOPURI`."""
    if not document.strip():
        raise FaraConsimtamant("acordul scris lipsește")
    necunoscute = [s for s in scopuri if s not in SCOPURI]
    if not scopuri or necunoscute:
        raise ValueError(f"scopuri invalide: {necunoscute or 'niciunul'}")
    c = Consimtamant(
        id=new_id(),
        tenant_id=tenant_id,
        vorbitor=vorbitor.strip(),
        document_sha256=amprenta(document),
        scopuri=sorted(set(scopuri)),
        acordat_la=dt.datetime.now(dt.UTC),
        inregistrat_de=utilizator_id,
        motiv_revocare="",
    )
    db.add(c)
    db.flush()
    audit.record(db, "voce.consimtamant", obiect_tip="voce_consimtamant", obiect_id=c.id, tenant_id=tenant_id,
                 utilizator_id=utilizator_id, detalii={"scopuri": c.scopuri})  # fmt: skip
    return c


def _valabil(db: Session, consimtamant_id: uuid.UUID, scop: str) -> Consimtamant:
    c = db.get(Consimtamant, consimtamant_id)
    if c is None or c.revocat_la is not None:
        raise FaraConsimtamant("acordul vorbitorului lipsește sau a fost revocat")
    if scop not in c.scopuri:
        raise FaraConsimtamant(f"acordul nu acoperă scopul „{scop}”")
    return c


def antreneaza(
    db: Session, tenant_id: uuid.UUID, consimtamant_id: uuid.UUID, inregistrari: list[Inregistrare]
) -> ModelVoce:
    """Antrenarea o singură dată (al doilea apel pe același acord întoarce modelul existent)."""
    c = db.get(Consimtamant, consimtamant_id)
    if c is None or c.revocat_la is not None:
        raise FaraConsimtamant("fără acord valabil nu se antrenează vocea")
    existent = db.execute(
        select(ModelVoce).where(ModelVoce.consimtamant_id == c.id, ModelVoce.stare == "gata")
    ).scalar_one_or_none()
    if existent is not None:
        return existent
    minute = round(sum(i.durata_sec for i in inregistrari) / 60, 2)
    if minute < MINUTE_MINIME:
        raise InregistrariInsuficiente(f"{minute} minute înregistrate; trebuie cel puțin {MINUTE_MINIME}")
    with urme.span(
        "media", "voce_proprie.antrenare", db=db, obiect_tip="voce_model", intrari={"minute": minute}
    ):
        ref = _antrenor.antreneaza(inregistrari, eticheta=c.id.hex[:12])
    m = ModelVoce(id=new_id(), tenant_id=tenant_id, consimtamant_id=c.id, stare="gata",
                  minute_inregistrate=minute, motor=MOTOR, model_ref=ref,
                  creat_la=dt.datetime.now(dt.UTC))  # fmt: skip
    db.add(m)
    db.flush()
    audit.record(db, "voce.antrenare", obiect_tip="voce_model", obiect_id=m.id, tenant_id=tenant_id,
                 detalii={"minute": minute, "consimtamant_id": str(c.id)})  # fmt: skip
    return m


def profil(db: Session, model_id: uuid.UUID, scop: str) -> voce.ProfilVoce:
    """Profilul de voce al modelului, doar cu acord valabil pentru scop."""
    m = db.get(ModelVoce, model_id)
    if m is None or m.stare != "gata":
        raise FaraConsimtamant("modelul de voce nu există sau a fost retras")
    c = _valabil(db, m.consimtamant_id, scop)
    lic = voce.LicentaVoce(
        "verificata",
        "voce_proprie",
        c.vorbitor,
        f"acord scris {c.document_sha256[:16]}…, {c.acordat_la:%Y-%m-%d}",
        f"scop: {scop}",
    )
    return voce.ProfilVoce(f"proprie-{m.id.hex[:12]}", MOTOR, m.model_ref, lic)


def sintetizeaza(
    db: Session,
    tenant_id: uuid.UUID,
    model_id: uuid.UUID,
    fraze: list[str],
    *,
    scop: str = "continut_organic",
) -> voce.Naratiune:
    """Narațiunea cu vocea proprie; licența poartă acordul (pentru revocare)."""
    p = profil(db, model_id, scop)
    m = db.get(ModelVoce, model_id)
    assert m is not None  # noqa: S101 (verificat în `profil`)
    extra: dict[str, Any] = {
        "consimtamant_id": str(m.consimtamant_id),
        "model_voce_id": str(m.id),
        "scop": scop,
    }
    return voce.sintetizeaza(
        db, tenant_id, fraze, profil_dat=p, licenta_extra=extra, descriere="narațiune, voce proprie"
    )


def revoca(db: Session, consimtamant_id: uuid.UUID, *, motiv: str, utilizator_id: uuid.UUID | None) -> int:
    """Revocă acordul: modelul se retrage, narațiunile făcute cu el devin `refuzata`. Întoarce câte s-au
    blocat."""
    c = db.get(Consimtamant, consimtamant_id)
    if c is None:
        raise FaraConsimtamant("acordul nu există")
    acum = dt.datetime.now(dt.UTC)
    c.revocat_la, c.motiv_revocare = c.revocat_la or acum, motiv[:500]
    for m in db.execute(select(ModelVoce).where(ModelVoce.consimtamant_id == c.id)).scalars():
        m.stare, m.retras_la = "retras", m.retras_la or acum
    blocate = db.execute(
        text(
            "UPDATE active SET licenta = jsonb_set(licenta, '{statut}', '\"refuzata\"') "
            "WHERE tenant_id = :t AND licenta->>'consimtamant_id' = :c RETURNING id"
        ),
        {"t": c.tenant_id, "c": str(c.id)},
    )
    n = len(blocate.all())
    db.flush()
    audit.record(db, "voce.revocare", obiect_tip="voce_consimtamant", obiect_id=c.id, tenant_id=c.tenant_id,
                 utilizator_id=utilizator_id, detalii={"active_blocate": n})  # fmt: skip
    return int(n)
