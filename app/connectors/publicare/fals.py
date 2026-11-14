"""# SIMULAT: platforma falsă, în memorie, și conectorul ei (F9.1). Referința contractului comun: orice
conector real
trebuie să treacă aceleași teste (`tests/contract/contract_publicare.py`), pe platforma lui simulată prin
HTTP.

Defectele se injectează pe rând (`injecteaza`) și se consumă la următoarea publicare:
`temporar` (5xx), `definitiv` (refuz), `autentificare` (token respins), `timeout`, `pierde_raspunsul`
(postarea se face,
răspunsul se pierde: `verifica` trebuie să o găsească)."""

import datetime as dt
import secrets
import uuid
from dataclasses import dataclass, field
from urllib.parse import quote

from app.connectors.contract import EfectDeTrimis, Limite, RezultatPlatforma, StarePostare, Token
from app.connectors.publicare.baza import DepozitTokenuri, text_postare, token_sau_autentificare
from app.operare.motor import EroareAutentificare, EroareDefinitiva, EroareTemporara


@dataclass
class PlatformaFalsa:
    defecte: list[str] = field(default_factory=list)
    postari: list[dict[str, str]] = field(default_factory=list)
    tokenuri_valide: set[str] = field(default_factory=set)
    coduri: set[str] = field(default_factory=set)
    limita_zi: int = 100

    def injecteaza(self, *defecte: str) -> None:
        self.defecte.extend(defecte)

    def postari_publicate(self) -> list[dict[str, str]]:
        return list(self.postari)

    def expira_tokenul(self) -> None:
        self.tokenuri_valide.clear()

    def cod_valid(self) -> str:
        c = secrets.token_hex(8)
        self.coduri.add(c)
        return c

    def emite_token(self, cont: str = "cont-fals") -> Token:
        acces = "fals-" + secrets.token_hex(12)
        self.tokenuri_valide.add(acces)
        return Token(
            acces, dt.datetime.now(dt.UTC) + dt.timedelta(days=60), "re-" + acces, cont, ("publicare",)
        )


class ConectorFalsPublicare:
    def __init__(self, platforma: PlatformaFalsa, depozit: DepozitTokenuri, canal: str = "fals_api") -> None:
        self.p, self.depozit, self.canal = platforma, depozit, canal

    def _token(self, tenant_id: uuid.UUID) -> Token:
        t = token_sau_autentificare(self.depozit, tenant_id, self.canal)
        if t.acces not in self.p.tokenuri_valide:
            raise EroareAutentificare("401: token respins de platformă")
        return t

    def url_autorizare(self, stare: str, redirect: str) -> str:
        return f"https://platforma.exemplu.test/oauth?client_id=ama&state={quote(stare)}&redirect_uri={quote(redirect)}"

    def schimba_cod(self, cod: str, redirect: str) -> Token:
        if cod not in self.p.coduri:
            raise EroareDefinitiva("400: cod de autorizare invalid")
        self.p.coduri.discard(cod)
        return self.p.emite_token()

    def reimprospateaza(self, token: Token) -> Token:
        if not token.reimprospatare.startswith("re-"):
            raise EroareAutentificare("401: reîmprospătare refuzată")
        return self.p.emite_token(token.cont_extern)

    def trimite(self, efect: EfectDeTrimis) -> RezultatPlatforma:
        self._token(efect.tenant_id)
        defect = self.p.defecte.pop(0) if self.p.defecte else "ok"
        if defect == "temporar":
            raise EroareTemporara("503: platforma indisponibilă")
        if defect == "timeout":
            raise EroareTemporara("timeout")
        if defect == "autentificare":
            raise EroareAutentificare("401: token respins de platformă")
        text = text_postare(efect.payload)
        if defect == "definitiv" or not text:
            raise EroareDefinitiva("400: conținut refuzat")
        if len(self.p.postari) >= self.p.limita_zi:
            raise EroareTemporara("429: limita zilnică")
        n = len(self.p.postari) + 1
        rez = RezultatPlatforma(f"fals-{n}", f"https://platforma.exemplu.test/p/{n}")
        self.p.postari.append({"id": rez.id_extern, "idem": efect.idem, "text": text, "link": rez.link})
        if defect == "pierde_raspunsul":
            raise EroareTemporara("răspunsul s-a pierdut")
        return rez

    def verifica(self, efect: EfectDeTrimis) -> RezultatPlatforma | None:
        self._token(efect.tenant_id)
        for p in self.p.postari:
            if p["idem"] == efect.idem:
                return RezultatPlatforma(p["id"], p["link"])
        return None

    def stare(self, tenant_id: uuid.UUID, id_extern: str) -> StarePostare:
        self._token(tenant_id)
        gasit = any(p["id"] == id_extern for p in self.p.postari)
        return StarePostare.PUBLICATA if gasit else StarePostare.INEXISTENTA

    def limite(self, tenant_id: uuid.UUID) -> Limite:
        self._token(tenant_id)
        return Limite(
            "platforma falsă: contorul zilnic", self.p.limita_zi - len(self.p.postari), self.p.limita_zi
        )
