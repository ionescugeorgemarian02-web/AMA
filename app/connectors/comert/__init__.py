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
