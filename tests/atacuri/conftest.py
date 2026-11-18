# Fixturile colecției de atacuri (F15.2): clienți, conturi de reclame simulate, clientul HTTP.
from tests.integration.conftest import client  # noqa: F401
from tests.integration.test_facturare import procesator  # noqa: F401
from tests.integration.utile_productie import AnunturiFalse, anunturi, fabrica_clienti, om, tenant  # noqa: F401
from tests.integration.utile_reclame import cont_agentie, depozit, meta  # noqa: F401
from tests.integration.utile_site import cutie  # noqa: F401
