"""F13.8 — verificarea reclamelor înainte de lansare. „Gata când”: reclamele de probă cu probleme de politică
sunt blocate (nu ajung la platformă, campania fără nicio reclamă bună nu se creează, activarea cere pagina vie).
Platforma e SIMULATĂ (# SIMULAT)."""

# ruff: noqa: F811
import uuid
from collections.abc import Callable

import pytest

from app.connectors.publicare.baza import DepozitInMemorie
from app.db import sesiune_agentie
from app.reclame import Campanie, constructor, propuneri
from app.reclame.constructor import Creativ
from tests.integration.utile_productie import fabrica_clienti, om  # noqa: F401
from tests.integration.utile_reclame import (  # noqa: F401
    PAGINI,
    autorizeaza,
    cont_agentie,
    creative,
    depozit,
    executa_efecte,
    meta,
    plan_aprobat,
)
from tests.platforme.meta_ads import MarketingSimulat

pytestmark = pytest.mark.db


def test_reclamele_cu_probleme_de_politica_sunt_blocate(
    meta: MarketingSimulat,
    depozit: DepozitInMemorie,
    cont_agentie: Callable[..., tuple[uuid.UUID, uuid.UUID]],
    om: uuid.UUID,
) -> None:
    tenant, cont_id = cont_agentie()
    autorizeaza(depozit, meta, tenant)
    pid = plan_aprobat(cont_id, om)
    cr = creative(pid) | {
        "scalare": Creativ("Audit gratuit", "Vânzări garantate în 30 de zile!"),  # promisiune de rezultat
        "Trei greșeli de pe site": Creativ("Trei greșeli de pe site", "Ești supraponderal? Și site-ul tău."),
        "Exemplu: o cafenea": Creativ("Cum a crescut o cafenea", "Exemplul unei cafenele.", generat_ai=True),
    }
    with sesiune_agentie() as db:
        scalare, test = (c.id for c in constructor.construieste(db, pid, cr))  # type: ignore[arg-type]
        blocate = {
            a.varianta: [p["cod"] for p in a.verificare]
            for a in constructor.anunturi(db, test)
            if a.stare == "blocata"
        }
    executa_efecte()
    assert blocate == {
        "Trei greșeli de pe site": ["reclame.reclame-atribute-personale"],
        "Exemplu: o cafenea": ["dezvaluire_ai"],
    }
    with sesiune_agentie() as db:
        assert db.get(Campanie, scalare).stare == "esuata"  # type: ignore[union-attr]
        assert db.get(Campanie, test).stare == "in_pauza"  # type: ignore[union-attr]
    assert [c["name"] for c in meta.campanii()] == ["Audit gratuit · test"], (
        "campania fără reclame bune nu pleacă"
    )
    [ad] = [a["name"] for a in meta.reclame()]
    assert ad.endswith("unde-pierzi-clienti"), "doar reclama curată ajunge la platformă"

    PAGINI["https://agentie.example/audit"] = False  # pagina de destinație cade înainte de activare
    try:
        with sesiune_agentie() as db:
            p = propuneri.propune(
                db, test, "stare", {"stare": "activa"}, motiv="Lansare", sursa="om", utilizator_id=om
            )
            assert p.stare == "refuzata" and p.verdict["motive"] == ["pagina de destinație nu răspunde"]
    finally:
        PAGINI.clear()
