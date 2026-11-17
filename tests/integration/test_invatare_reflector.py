"""F11.1 — Reflectorul. „Gata când”: după un lot închis apar propuneri de lecții cu dovezi. Lotul e construit
din postări etichetate cu recompensă (ca după colector), verdicte salvate și respingeri reale."""

# ruff: noqa: F811
import datetime as dt
import uuid
from collections.abc import Callable

import pytest
from sqlalchemy import Engine, text

from app.conturi import Rol
from app.db import sesiune_tenant
from app.ids import new_id
from app.invatare import Lectie, reflector
from app.productie import Hotarare, Stare, aprobari
from tests.integration.utile_productie import fabrica_clienti, livrabil, muta, om, tenant  # noqa: F401

pytestmark = pytest.mark.db
ETICHETA = (
    "INSERT INTO etichete_postari (id, tenant_id, livrabil_id, canal, publicat_la, tipar_hook, format, zi_saptamana, ora, "
    "recompensa, recompensa_tip, recompensa_interval) "
    "VALUES (:i, :t, :l, 'facebook', now() - interval '4 days', :h, 'postare', 2, 9, :r, 'interactiuni_pe_afisari', '72h')"
)


def postare_masurata(admin: Engine, t: uuid.UUID, tipar: str, recompensa: float) -> uuid.UUID:
    lid = livrabil(t)
    with admin.begin() as c:
        c.execute(text(ETICHETA), {"i": new_id(), "t": t, "l": lid, "h": tipar, "r": recompensa})
    return lid


def respinge(t: uuid.UUID, lid: uuid.UUID, om: uuid.UUID) -> None:
    curenta = Stare.PLANIFICAT
    for s in (Stare.BRIEFAT, Stare.IN_SCRIERE, Stare.IN_VALIDARE, Stare.VALIDAT):
        muta(t, lid, curenta, s)
        curenta = s
    with sesiune_tenant(t) as db:
        ap = aprobari.cere(db, lid)
        aprobari.decide(
            db,
            ap.id,
            Hotarare.RESPINS,
            utilizator_id=om,
            rol=Rol.PROPRIETAR,
            versiune=1,
            motiv_standard="hook_slab",
        )


def test_dupa_un_lot_inchis_apar_propuneri_de_lectii_cu_dovezi(
    fabrica_clienti: Callable[[], uuid.UUID], om: uuid.UUID, admin_engine: Engine
) -> None:
    t, alt = fabrica_clienti(), fabrica_clienti()
    for _ in range(12):
        postare_masurata(admin_engine, t, "cifra", 0.02)
    with sesiune_tenant(t) as db:
        assert reflector.reflecteaza(db, t) is None, "sub 20 de postări măsurate lotul nu se închide"
        assert reflector.propuneri(db, t) == []
    bune = [postare_masurata(admin_engine, t, "intrebare", 0.09) for _ in range(8)]
    for lid in bune[:3]:
        respinge(t, lid, om)
    with sesiune_tenant(t) as db:
        lot = reflector.reflecteaza(db, t)
        assert lot is not None and lot.postari == 20 and lot.propuneri >= 3
        p = {x.cheie: x for x in reflector.propuneri(db, t)}
    des = p["rezultate:tipar_hook:intrebare:mai_des"]
    assert des.stare == "propusa" and des.lot_id == lot.id and len(des.dovezi) == 8
    assert {d["livrabil_id"] for d in des.dovezi} == {str(i) for i in bune}, "dovezile sunt postările lotului"
    assert "9,0 interacțiuni la 100 de afișări" in des.text
    assert "rezultate:tipar_hook:cifra:mai_rar" in p
    resp = p["decizii:hook_slab"]
    assert "de 3 ori pentru „Hook slab”" in resp.text and len(resp.dovezi) == 3
    assert all(x.a_ajutat == 0 and x.a_daunat == 0 for x in p.values())
    with sesiune_tenant(t) as db:
        assert reflector.reflecteaza(db, t) is None, "același lot nu se reflectă de două ori"
    with sesiune_tenant(alt) as db:
        assert reflector.propuneri(db, alt) == [], "lecțiile unui client nu ajung la altul"
        assert db.query(Lectie).count() == 0

    # lotul următor: aceeași concluzie nu dublează lecția
    for _ in range(12):
        postare_masurata(admin_engine, t, "cifra", 0.02)
    for _ in range(8):
        postare_masurata(admin_engine, t, "intrebare", 0.09)
    with sesiune_tenant(t) as db:
        lot2 = reflector.reflecteaza(db, t, acum=dt.datetime.now(dt.UTC) + dt.timedelta(minutes=1))
        assert lot2 is not None and lot2.postari == 20 and lot2.propuneri == 0
        assert len(reflector.propuneri(db, t)) == len(p)
