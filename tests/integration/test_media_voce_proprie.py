"""F16.4 — vocea proprie antrenată. „Gata când”: fără acord scris nu se antrenează și nu se sintetizează; cu acord și
destule înregistrări, modelul se antrenează o dată și narațiunea are licența vocii proprii (verificată, cu acordul
drept dovadă, etichetată ca voce generată); scopul din afara acordului e refuzat; revocarea retrage modelul și
blochează narațiunile deja făcute. Antrenarea și adaptorul TTS sunt SIMULATE (D-026)."""

# ruff: noqa: F811
import uuid

import pytest
from sqlalchemy import Engine, text

from app.db import sesiune_tenant
from app.media import licente, provenienta, voce, voce_proprie
from app.media.modele import Activ
from tests.integration.utile_productie import fabrica_clienti, om, tenant  # noqa: F401

pytestmark = pytest.mark.db
ACORD = b"%PDF-1.4 acord semnat: Ana Pop permite vocea pentru continut organic"
INREG = [voce_proprie.Inregistrare(f"{i:064x}", 600.0) for i in range(10)]  # 100 de minute
FRAZE = ["Bună dimineața din Brașov, de la Cofetăria Zorilor."]


def test_acordul_antrenarea_sinteza_si_revocarea(
    tenant: uuid.UUID, om: uuid.UUID, admin_engine: Engine
) -> None:
    with sesiune_tenant(tenant) as db:
        with pytest.raises(voce_proprie.FaraConsimtamant):
            voce_proprie.inregistreaza_consimtamant(db, tenant, vorbitor="Ana Pop", document=b"  ",
                                                    scopuri=["continut_organic"], utilizator_id=om)  # fmt: skip
        with pytest.raises(voce_proprie.FaraConsimtamant):
            voce_proprie.antreneaza(db, tenant, uuid.uuid4(), INREG)
        c = voce_proprie.inregistreaza_consimtamant(
            db, tenant, vorbitor="Ana Pop", document=ACORD, scopuri=["continut_organic"], utilizator_id=om
        )
        with pytest.raises(voce_proprie.InregistrariInsuficiente):
            voce_proprie.antreneaza(db, tenant, c.id, INREG[:3])
        m = voce_proprie.antreneaza(db, tenant, c.id, INREG)
        assert m.stare == "gata" and float(m.minute_inregistrate) == 100.0
        assert voce_proprie.antreneaza(db, tenant, c.id, INREG).id == m.id, "antrenare o singură dată"
        n = voce_proprie.sintetizeaza(db, tenant, m.id, FRAZE)
        lic = n.activ.licenta or {}
        assert lic["tip"] == "voce_sintetizata" and lic["baza_drepturi"] == "voce_proprie"
        assert lic["statut"] == "verificata" and lic["consimtamant_id"] == str(c.id)
        assert c.document_sha256[:16] in lic["dovada"] and voce.permite_publicarea(lic)
        assert (n.activ.generare or {})["motor"] == "proprie" and not licente.probleme(lic)
        assert provenienta.ai_din([{"licenta": lic}])["voce_sintetica"], "vocea proprie e tot voce generată"
        with pytest.raises(voce_proprie.FaraConsimtamant):
            voce_proprie.sintetizeaza(db, tenant, m.id, FRAZE, scop="reclame")
        aid = n.activ.id
        assert voce_proprie.revoca(db, c.id, motiv="vorbitorul a plecat din firmă", utilizator_id=om) == 1
        with pytest.raises(voce_proprie.FaraConsimtamant):
            voce_proprie.sintetizeaza(db, tenant, m.id, FRAZE)
        a = db.get(Activ, aid)
        db.refresh(a)
        assert a is not None and a.licenta is not None and a.licenta["statut"] == "refuzata"
        assert licente.probleme(a.licenta) and not voce.permite_publicarea(a.licenta)
    with admin_engine.connect() as cx:
        actiuni = set(cx.execute(text("SELECT actiune FROM jurnal_audit WHERE tenant_id = :t AND actiune LIKE 'voce.%'"),
                                 {"t": tenant}).scalars())  # fmt: skip
        stare = cx.execute(text("SELECT stare FROM voce_modele WHERE id = :i"), {"i": m.id}).scalar_one()
    assert actiuni == {"voce.consimtamant", "voce.antrenare", "voce.revocare"} and stare == "retras"


def test_alt_client_nu_vede_acordul(tenant: uuid.UUID, fabrica_clienti, om: uuid.UUID) -> None:  # type: ignore[no-untyped-def]
    with sesiune_tenant(tenant) as db:
        c = voce_proprie.inregistreaza_consimtamant(
            db, tenant, vorbitor="Ana Pop", document=ACORD, scopuri=["reclame"], utilizator_id=om
        )
        cid = c.id
    alt = fabrica_clienti()
    with sesiune_tenant(alt) as db:
        assert db.get(voce_proprie.Consimtamant, cid) is None
        with pytest.raises(voce_proprie.FaraConsimtamant):
            voce_proprie.antreneaza(db, alt, cid, INREG)
