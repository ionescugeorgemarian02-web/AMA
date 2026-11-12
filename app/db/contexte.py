"""Contextul de client al unei tranzacții (21.1). Setat cu `set_config(..., true)`: local tranzacției."""

import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class ContextDb:
    """Ce știe baza despre cel care întreabă. Implicit nimic: politicile RLS refuză tot (refuz implicit).

    - `tenant_id`: clientul curent; vede doar rândurile lui.
    - `user_id`: utilizatorul curent (pentru rândurile proprii și pentru jurnal).
    - `agency`: scop de agenție; vede toți clienții. Doar rolurile din `roluri.ROLURI_SCOP_AGENTIE`.
    - `auth`: context de sistem pentru fluxul de autentificare, înainte să existe o sesiune.
    """

    tenant_id: uuid.UUID | None = None
    user_id: uuid.UUID | None = None
    agency: bool = False
    auth: bool = False

    def settings(self) -> dict[str, str]:
        return {
            "app.tenant_id": str(self.tenant_id) if self.tenant_id else "",
            "app.user_id": str(self.user_id) if self.user_id else "",
            "app.agency": "1" if self.agency else "",
            "app.auth": "1" if self.auth else "",
        }
