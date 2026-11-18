"""Fluxuri de probă pentru FT.2: un job care lasă o urmă și pune în coadă un al doilea job (același fir)."""

from app.operare import motor, urme


@motor.pas("proba_urme.pas")
def _pas(tenant_id: str, eticheta: str) -> str:
    urme.emite("agent", f"lucreaza:{eticheta}", rezultat="ok")
    return eticheta


@motor.flux("proba_urme.copil")
def copil(tenant_id: str) -> str:
    _pas(tenant_id, "copil")
    raise motor.EroareDefinitiva("platforma a refuzat")


@motor.pas("proba_urme.trimite_copil")
def _trimite_copil(tenant_id: str) -> str:
    return motor.trimite(copil, tenant_id, cheie=f"urme-copil-{tenant_id}")


@motor.flux("proba_urme.parinte")
def parinte(tenant_id: str) -> str:
    _pas(tenant_id, "parinte")
    return _trimite_copil(tenant_id)
