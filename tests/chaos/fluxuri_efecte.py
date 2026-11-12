"""# SIMULAT: conectorul fals pe canalul `fals`, încărcat în procesul worker (`AMA_WORKER_MODULE_TEST`).
„Platforma” e directorul `AMA_PROBA_DIR/platforma`, comun cu testul."""

from app.connectors import registru
from tests.chaos.fluxuri_proba import director
from tests.conector_fals import ConectorFals

registru.inregistreaza("fals", ConectorFals(director()))
