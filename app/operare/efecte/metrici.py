"""Ușa executorului spre cititorii de metrici ai platformelor (F10.1, K1). Conectorii se cheamă DOAR din
`app/operare/efecte` (garda `check_efecte`), deci și citirea metricilor trece pe aici.

    from app.operare.efecte import metrici as usa_metrici
    if usa_metrici.are_cititor("facebook"):
        cifre = usa_metrici.citeste(tenant_id, "facebook", id_extern)

Citirea nu schimbă nimic la platformă: nu este un efect extern și nu trece prin cozile de efecte.
"""

import datetime as dt
import uuid

from app.connectors import metrici as registru_metrici
from app.connectors.contract import Metrici


def are_cititor(canal: str) -> bool:
    return registru_metrici.cititor_pentru(canal) is not None


def citeste(tenant_id: uuid.UUID, canal: str, id_extern: str) -> Metrici:
    """Cifrele postării, acum. Aruncă `LookupError` dacă nu există cititor pentru canal și erorile
    clasificate ale platformei (`app.operare.motor`) altfel."""
    c = registru_metrici.cititor_pentru(canal)
    if c is None:
        raise LookupError(f"canalul „{canal}” nu are cititor de metrici")
    return c.metrici(tenant_id, id_extern)


def are_retentie(canal: str) -> bool:
    return registru_metrici.cititor_retentie(canal) is not None


def citeste_retentie(
    tenant_id: uuid.UUID, canal: str, id_extern: str, de_la: dt.date, pana_la: dt.date
) -> list[tuple[float, float]]:
    """Curba de retenție a clipului (F10.2). `LookupError` dacă canalul nu are cititor de retenție."""
    c = registru_metrici.cititor_retentie(canal)
    if c is None:
        raise LookupError(f"canalul „{canal}” nu are curbă de retenție")
    return c.retentie(tenant_id, id_extern, de_la, pana_la)
