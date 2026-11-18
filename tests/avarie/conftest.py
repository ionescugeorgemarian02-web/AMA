# Fixturile testelor de avarie: workeri reali (din tests/chaos) și clienți (din utile_productie).
from tests.chaos.conftest import dir_proba, workeri  # noqa: F401
from tests.integration.conftest import client  # noqa: F401
from tests.integration.utile_productie import fabrica_clienti, om, tenant  # noqa: F401
