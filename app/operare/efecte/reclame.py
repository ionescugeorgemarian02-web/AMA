"""Ușa executorului spre conturile de reclame (F13). Conectorii se cheamă DOAR din `app/operare/efecte`
(garda `check_efecte`), deci și citirea rezultatelor trece pe aici.

    from app.operare.efecte import reclame as usa_reclame
    randuri = usa_reclame.rezultate(tenant_id, "meta", "act_123", de_la, pana_la)

Citirea nu schimbă nimic la platformă: nu este un efect extern și nu trece prin cozile de efecte.
"""

import datetime as dt
import uuid

from app.connectors import reclame as registru_reclame
from app.connectors.contract import CititorReclame, RandReclame, StareCont


def are_cititor(platforma: str) -> bool:
    return registru_reclame.cititor_pentru(platforma) is not None


def _cititor(platforma: str) -> CititorReclame:
    c = registru_reclame.cititor_pentru(platforma)
    if c is None:
        raise LookupError(f"platforma „{platforma}” nu are conector de reclame")
    return c


def rezultate(
    tenant_id: uuid.UUID, platforma: str, cont_extern: str, de_la: dt.date, pana_la: dt.date
) -> list[RandReclame]:
    """Cifrele zilnice ale campaniilor și reclamelor contului. `LookupError` fără conector; altfel erorile
    clasificate ale platformei (`app.operare.motor`)."""
    return _cititor(platforma).rezultate(tenant_id, cont_extern, de_la, pana_la)


def stare_cont(tenant_id: uuid.UUID, platforma: str, cont_extern: str) -> StareCont:
    return _cititor(platforma).stare_cont(tenant_id, cont_extern)
