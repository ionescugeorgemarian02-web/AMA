"""Atac F15.2 (CRITIC în revizie): mai multe propuneri de activare, fiecare sub plafon singură, aprobate una
după alta, nu trec împreună de plafonul zilnic al contului (gardianul se reaplică la aprobare)."""

import uuid
from collections.abc import Callable

import pytest

from app.connectors.publicare.baza import DepozitInMemorie
from app.db import sesiune_agentie
from app.reclame import Campanie, propuneri
from tests.integration.utile_reclame import autorizeaza, construieste
from tests.platforme.meta_ads import MarketingSimulat

pytestmark = pytest.mark.db


def test_activarile_aprobate_impreuna_nu_trec_de_plafonul_zilnic(
    meta: MarketingSimulat,
    depozit: DepozitInMemorie,
    cont_agentie: Callable[..., tuple[uuid.UUID, uuid.UUID]],
    om: uuid.UUID,
) -> None:
    tenant, cont_id = cont_agentie()  # plafonul zilnic: 10 000 de bani
    autorizeaza(depozit, meta, tenant)
    ids = construieste(cont_id, om)
    assert len(ids) >= 2, "planul construiește cel puțin două campanii"
    ids = ids[:2]
    with sesiune_agentie() as db:
        for cid in ids:
            c = db.get(Campanie, cid)
            assert c is not None and c.stare != "activa"
            c.buget_zilnic_bani = 6_000  # fiecare încape singură (sub plafonul pe campanie, 8 000)
    with sesiune_agentie() as db:
        p = [
            propuneri.propune(
                db, cid, "stare", {"stare": "activa"}, motiv="Pornire", sursa="om", utilizator_id=om
            )
            for cid in ids
        ]
        assert all(x.verdict["permis"] for x in p), [x.verdict for x in p]
        prima, a_doua = p[0].id, p[1].id
    with sesiune_agentie() as db:
        propuneri.aproba(db, prima, utilizator_id=om)
    with pytest.raises(propuneri.PropunereRefuzata, match="plafonul zilnic"), sesiune_agentie() as db:
        propuneri.aproba(db, a_doua, utilizator_id=om)
    with sesiune_agentie() as db:
        assert propuneri.ale_campaniei(db, ids[1])[0].stare == "propusa", (
            "a doua rămâne nedecisă, nu aplicată"
        )
