"""# SIMULAT: contract HTTP local; nu admite transport de rețea real."""

import httpx


class ShopifySimulat:
    def __init__(self, transport: httpx.MockTransport) -> None:
        if not isinstance(transport, httpx.MockTransport):
            raise ValueError("Shopify rămâne simulat până la migrare")
        self.transport = transport

    def schimba_cod(self, cod: str, client_id: str, secret: str) -> str:
        with httpx.Client(transport=self.transport, base_url="https://shopify.invalid") as client:
            r = client.post(
                "/admin/oauth/access_token",
                json={
                    "client_id": client_id,
                    "client_secret": secret,
                    "code": cod,
                },
            )
            if r.status_code != 200:
                raise ValueError("Autorizarea Shopify a eșuat")
            token = r.json().get("access_token")
            if not isinstance(token, str) or not token:
                raise ValueError("Token Shopify absent")
            return token

    def catalog(self, token: str) -> list[dict[str, object]]:
        """# SIMULAT: contrat normalizat local, nu operație Admin API reală."""
        produse: list[dict[str, object]] = []
        cursor = ""
        vazute: set[str] = set()
        with httpx.Client(transport=self.transport, base_url="https://shopify.invalid") as client:
            for _ in range(100):
                r = client.get(
                    "/catalog", params={"cursor": cursor}, headers={"X-Shopify-Access-Token": token}
                )
                if r.status_code != 200:
                    raise ValueError("Sincronizarea catalogului a eșuat")
                corp = r.json()
                produse.extend(corp["produse"])
                cursor = corp.get("cursor", "")
                if not cursor:
                    return produse
                if cursor in vazute:
                    raise ValueError("Cursor Shopify repetat")
                vazute.add(cursor)
        raise ValueError("Catalog prea mare pentru un lot")

    def vanzari(self, tip: str, token: str) -> list[dict[str, object]]:
        """# SIMULAT: lot local de comenzi sau clienți, normalizat de adaptor."""
        if tip not in {"comanda", "client"}:
            raise ValueError("Tip nesuportat")
        with httpx.Client(transport=self.transport, base_url="https://shopify.invalid") as client:
            r = client.get(f"/date/{tip}", headers={"X-Shopify-Access-Token": token})
            if r.status_code != 200:
                raise ValueError("Import Shopify eșuat")
            corp = r.json()
            if not isinstance(corp, list):
                raise ValueError("Lot invalid")
            return corp
