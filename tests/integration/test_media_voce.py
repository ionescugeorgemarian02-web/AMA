"""F8.1 — vocea și licența ei. „Gata când”: o frază în română este sintetizată și statutul licenței este scris în
registrul de active. Motorul de voce este SIMULAT (D-007); Piper real: la migrare."""

# ruff: noqa: F811
import uuid
from pathlib import Path

import pytest
from sqlalchemy import Engine, text

from app import media
from app.config import get_settings
from app.db import sesiune_tenant
from tests.integration.utile_productie import fabrica_clienti, tenant  # noqa: F401

pytestmark = pytest.mark.db
FRAZA = "Cafeneaua Zorilor prăjește în fiecare marți cafea proaspătă, în loturi mici, la Brașov."


def test_fraza_romaneasca_sintetizata_cu_statutul_licentei_in_registru(
    tenant: uuid.UUID, admin_engine: Engine
) -> None:
    with sesiune_tenant(tenant) as db:
        n = media.voce.sintetizeaza(db, tenant, [FRAZA])
        a = n.activ
        assert (a.categorie, a.mime, a.sursa) == ("audio", "audio/wav", "voce_sintetizata")
        assert a.licenta is not None and a.licenta["statut"] == "verificata"
        assert a.licenta["profil"] == "ro-simulat" and a.licenta["tip"] == "voce_sintetizata"
        assert media.voce.permite_publicarea(a.licenta)
        wav = media.audio.citeste((Path(get_settings().media_dir) / a.cale).read_bytes())
        assert wav.durata == pytest.approx(n.durata) and n.durata > 3
        assert [c["w"] for c in wav.extra["cuvinte"]][:2] == ["Cafeneaua", "Zorilor"]
        aid = a.id
    with admin_engine.connect() as c:
        lic = c.execute(text("SELECT licenta->>'statut' FROM active WHERE id = :i"), {"i": aid}).scalar_one()
        det = c.execute(
            text("SELECT detalii->>'licenta' FROM jurnal_audit WHERE obiect_id = :i"), {"i": str(aid)}
        ).scalar_one()
    assert lic == "verificata" and det == "verificata"


def test_vocea_de_pornire_ramane_de_verificat_si_nu_se_publica(tenant: uuid.UUID) -> None:
    class MotorEcou:
        def sintetizeaza(self, text: str, profil: object, *, gresit: object = None) -> media.audio.Wav:
            return media.voce.MotorVoceSimulat().sintetizeaza(text, media.voce.profil())

    media.voce.seteaza_motor(MotorEcou())
    try:
        with sesiune_tenant(tenant) as db:
            n = media.voce.sintetizeaza(
                db, tenant, ["Bună dimineața din Brașov."], profil_cod="ro-piper-pornire"
            )
            assert n.activ.licenta is not None and n.activ.licenta["statut"] == "de_verificat"
            assert not media.voce.permite_publicarea(n.activ.licenta)
    finally:
        media.voce.seteaza_motor(None)
