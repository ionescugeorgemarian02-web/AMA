"""Descărcătorul politicos (F4.2, docs/12 §12.3, docs/21 §21.4): citește O adresă, cu toate apărările.

Ce face, la fiecare cerere:
1. verifică adresa (schemă, port, fără credențiale) și o rezolvă prin DNS; TOATE adresele trebuie să fie
publice
   (SSRF); conexiunea se face la adresa verificată (nu se mai rezolvă a doua oară: fără „DNS rebinding”), cu
   antetul `Host` și SNI ale gazdei adevărate;
2. citește `robots.txt` al gazdei (o dată pe gazdă, în memorie) și refuză ce interzice pentru User-Agent-ul
nostru;
3. respectă pauza dintre cereri pe aceeași gazdă (cel puțin pauza configurată, cel puțin `Crawl-delay`);
4. NU urmează redirecționările singur: le urmează el, cel mult `max_redirecturi`, și repetă verificările 1–2
pentru
   fiecare destinație, iar destinația trebuie să rămână în același domeniu înregistrat;
5. citește corpul în flux și se oprește la limita de octeți (și la limita de timp a cererii); tipul de
conținut
   se verifică înainte de a citi corpul;
6. nu trimite formulare, cookie-uri sau date de autentificare; la 401 / 403 sare pagina.

Nu folosește variabilele de proxy din mediu (`trust_env=False`): verificarea DNS trebuie să fie a lui.
Transportul HTTP, rezolvatorul DNS și ceasul se pot înlocui (teste fără rețea). O instanță = o colectare.
"""

import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlsplit

import httpx

from app.cercetare import robots as rb
from app.cercetare import ssrf
from app.cercetare.ssrf import Rezolvator, UrlRefuzat, UrlValid
from app.cercetare.url_utile import acelasi_domeniu, normalizeaza

TIPURI_PAGINA = ("text/html", "application/xhtml+xml")
TIPURI_TEXT = ("text/plain", "text/markdown")
TIPURI_SITEMAP = ("application/xml", "text/xml", "text/plain")
ANTETE_PASTRATE = (
    "content-type",
    "etag",
    "last-modified",
    "date",
    "content-language",
    "cache-control",
    "x-robots-tag",
)


@dataclass(frozen=True)
class Limite:
    """Limitele unei colectări (valori de pornire, nemăsurate)."""

    max_pagini: int = 60
    max_adancime: int = 3
    max_octeti_pagina: int = 2_000_000
    max_octeti_total: int = 40_000_000
    timp_total_sec: float = 300.0
    timeout_cerere_sec: float = 15.0
    pauza_sec: float = 1.0
    max_redirecturi: int = 5
    max_variante_interogare: int = (
        3  # câte interogări diferite pe aceeași cale (contra capcanelor cu parametri)
    )
    max_url_sitemap: int = 300


@dataclass
class Raspuns:
    url: str  # adresa finală, normalizată
    cod: int
    content_type: str
    corp: bytes
    antete: dict[str, str]
    redirecturi: int = 0


class Sarit(Exception):
    """Pagina nu s-a citit; `cod` e motivul (vezi `colectare.MOTIVE`)."""

    def __init__(self, cod: str, detaliu: str = "", cod_http: int | None = None) -> None:
        super().__init__(f"{cod}: {detaliu}" if detaliu else cod)
        self.cod = cod
        self.cod_http = cod_http


@dataclass
class Descarcator:
    user_agent: str
    radacina: str  # adresa de pornire: domeniul ei înregistrat este singurul permis
    limite: Limite = field(default_factory=Limite)
    transport: httpx.BaseTransport | None = None
    rezolva: Rezolvator = ssrf.rezolva_sistem
    exceptii_ssrf: frozenset[str] = frozenset()
    porturi: frozenset[int] = ssrf.PORTURI_IMPLICITE
    ceas: Callable[[], float] = time.monotonic
    dormi: Callable[[float], None] = time.sleep
    _robots: dict[str, rb.Robots] = field(default_factory=dict)
    _ultima: dict[str, float] = field(default_factory=dict)
    _client: httpx.Client | None = None
    cereri: int = 0

    # --- configurare

    def __post_init__(self) -> None:
        self._gazda_radacina = (urlsplit(self.radacina).hostname or "").lower()

    def _http(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                transport=self.transport,
                timeout=httpx.Timeout(self.limite.timeout_cerere_sec),
                follow_redirects=False,
                trust_env=False,
                headers={"User-Agent": self.user_agent, "Accept-Language": "ro,en;q=0.5"},
            )
        return self._client

    def inchide(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    # --- pașii

    def _valideaza(self, url: str) -> tuple[UrlValid, list[str]]:
        v = ssrf.valideaza_url(url, porturi=self.porturi)
        if not acelasi_domeniu(v.gazda, self._gazda_radacina):
            raise UrlRefuzat("alt_domeniu", v.gazda)
        return v, ssrf.adrese_sigure(v, self.rezolva, self.exceptii_ssrf)

    def _asteapta(self, gazda: str, pauza: float) -> None:
        ultima = self._ultima.get(gazda)
        if ultima is not None:
            ramas = pauza - (self.ceas() - ultima)
            if ramas > 0:
                self.dormi(ramas)
        self._ultima[gazda] = self.ceas()

    def _o_cerere(
        self,
        v: UrlValid,
        adrese: list[str],
        antete: dict[str, str],
        *,
        max_octeti: int,
        tipuri: Iterable[str],
        pauza: float,
    ) -> tuple[httpx.Response, bytes]:
        """O cerere, fără redirecționări, către prima dintre `adrese` (verificate, rezolvate o singură dată).
        Corpul se citește doar pentru 200 cu tip permis."""
        self._asteapta(v.gazda, pauza)
        adresa = adrese[0]
        gazda_ip = f"[{adresa}]" if ":" in adresa else adresa
        port_implicit = 443 if v.schema == "https" else 80
        tinta = f"{v.schema}://{gazda_ip}:{v.port}{v.cale}"
        antet_gazda = v.gazda if v.port == port_implicit else f"{v.gazda}:{v.port}"
        cerere = self._http().build_request(
            "GET", tinta, headers={**antete, "Host": antet_gazda}, extensions={"sni_hostname": v.gazda}
        )
        self.cereri += 1
        try:
            raspuns = self._http().send(cerere, stream=True)
            self._http().cookies.clear()  # nicio sesiune: nu se trimit cookie-uri înapoi
        except httpx.TimeoutException:
            raise Sarit("timeout") from None
        except httpx.HTTPError as exc:
            raise Sarit("eroare_retea", type(exc).__name__) from None
        try:
            if raspuns.status_code != 200:
                return raspuns, b""
            tip = raspuns.headers.get("content-type", "").split(";")[0].strip().lower()
            if tip not in tuple(tipuri):
                raise Sarit("tip_continut", tip or "lipsă", 200)
            declarat = raspuns.headers.get("content-length", "")
            if declarat.isdigit() and int(declarat) > max_octeti:
                raise Sarit("prea_mare", f"{declarat} octeți", 200)
            bucati: list[bytes] = []
            total = 0
            inceput = self.ceas()
            for bucata in raspuns.iter_bytes():
                total += len(bucata)
                if total > max_octeti:
                    raise Sarit("prea_mare", f"peste {max_octeti} octeți", 200)
                if self.ceas() - inceput > self.limite.timeout_cerere_sec * 2:
                    raise Sarit("timeout", "citirea corpului a durat prea mult", 200)
                bucati.append(bucata)
            return raspuns, b"".join(bucati)
        except httpx.TimeoutException:
            raise Sarit("timeout") from None
        except httpx.HTTPError as exc:
            raise Sarit("eroare_retea", type(exc).__name__) from None
        finally:
            raspuns.close()

    def _cu_redirecturi(
        self,
        url: str,
        antete: dict[str, str],
        *,
        max_octeti: int,
        tipuri: Iterable[str],
        robots_nu: bool = False,
    ) -> Raspuns:
        curent = self._curata(url, 0)
        for salt in range(self.limite.max_redirecturi + 1):
            try:
                v, adrese = self._valideaza(curent)
            except UrlRefuzat as exc:
                raise Sarit(
                    "redirect_alt_domeniu" if salt and exc.cod == "alt_domeniu" else exc.cod, str(exc)
                ) from None
            robots = self._robots_pentru(v)
            if not robots_nu and not robots.permite(self.user_agent, v.cale):
                raise Sarit("robots_interzis", v.cale)
            pauza = max(self.limite.pauza_sec, robots.crawl_delay(self.user_agent) or 0.0)
            r, corp = self._o_cerere(v, adrese, antete, max_octeti=max_octeti, tipuri=tipuri, pauza=pauza)
            if r.status_code in (301, 302, 303, 307, 308):
                locatie = r.headers.get("location", "")
                if not locatie:
                    raise Sarit("eroare_server", "redirecționare fără destinație", r.status_code)
                curent = self._curata(urljoin(curent, locatie), salt + 1)
                continue
            return self._raspuns(curent, r, corp, salt)
        raise Sarit("redirect_prea_multe", f"mai mult de {self.limite.max_redirecturi}")

    def _curata(self, url: str, salt: int) -> str:
        """Verifică adresa BRUTĂ (normalizarea ar scoate numele și parola) și o normalizează."""
        try:
            ssrf.valideaza_url(url, porturi=self.porturi)
        except UrlRefuzat as exc:
            raise Sarit(exc.cod, str(exc)) from None
        return normalizeaza(url)

    @staticmethod
    def _raspuns(url: str, r: httpx.Response, corp: bytes, salt: int) -> Raspuns:
        cod = r.status_code
        antete = {k: r.headers[k][:300] for k in ANTETE_PASTRATE if k in r.headers}
        if cod in (200, 304):
            return Raspuns(url, cod, antete.get("content-type", ""), corp, antete, salt)
        if cod in (401, 403, 407):
            raise Sarit("autentificare", "pagina cere autentificare sau interzice accesul", cod)
        if cod in (404, 410):
            raise Sarit("lipsa", "", cod)
        if cod in (429, 503):
            raise Sarit("limitat_de_server", r.headers.get("retry-after", ""), cod)
        raise Sarit("eroare_server" if cod >= 500 else "cod_neasteptat", str(cod), cod)

    # --- robots.txt

    def _robots_pentru(self, v: UrlValid) -> rb.Robots:
        origine = f"{v.schema}://{v.gazda}:{v.port}"
        if origine in self._robots:
            return self._robots[origine]
        # `robots.txt` se cere de pe aceeași origine, prin aceleași apărări (dar nu cere robots pentru
        # robots).
        url = f"{v.schema}://{v.gazda}:{v.port}/robots.txt"
        try:
            r = self._cu_redirecturi_robots(url)
            robots = rb.din_status(r.cod, r.corp.decode("utf-8", errors="replace"))
        except (Sarit, UrlRefuzat) as exc:
            robots = rb.din_status(getattr(exc, "cod_http", None), "")
        self._robots[origine] = robots
        return robots

    def _cu_redirecturi_robots(self, url: str) -> Raspuns:
        curent = url
        for _ in range(self.limite.max_redirecturi + 1):
            v, adrese = self._valideaza(curent)
            r, corp = self._o_cerere(
                v, adrese, {}, max_octeti=rb.MAXIM_OCTETI, tipuri=("text/plain", "text/html"),
                pauza=self.limite.pauza_sec,
            )  # fmt: skip
            if r.status_code in (301, 302, 303, 307, 308):
                curent = urljoin(curent, r.headers.get("location", ""))
                v2 = ssrf.valideaza_url(curent, porturi=self.porturi)
                if v2.gazda != v.gazda:  # robots.txt se urmărește doar pe aceeași gazdă
                    raise Sarit("redirect_alt_domeniu", cod_http=None)
                continue
            if r.status_code != 200:
                raise Sarit("robots", str(r.status_code), r.status_code)
            return Raspuns(curent, 200, "text/plain", corp, {}, 0)
        raise Sarit("redirect_prea_multe")

    def robots(self, url: str) -> rb.Robots:
        """`robots.txt` pentru gazda unei adrese (cerut o singură dată)."""
        v, _ = self._valideaza(url)
        return self._robots_pentru(v)

    # --- API

    def ia_pagina(self, url: str, *, etag: str | None = None, modificat: str | None = None) -> Raspuns:
        """O pagină HTML sau text. `etag` / `modificat` fac cererea condiționată (re-colectare incrementală):
        răspunsul 304 vine ca `Raspuns(cod=304)`. Ridică `Sarit`."""
        antete = {"Accept": "text/html,application/xhtml+xml;q=0.9,text/plain;q=0.5"}
        if etag:
            antete["If-None-Match"] = etag
        if modificat:
            antete["If-Modified-Since"] = modificat
        return self._cu_redirecturi(
            url, antete, max_octeti=self.limite.max_octeti_pagina, tipuri=TIPURI_PAGINA + TIPURI_TEXT
        )

    def ia_sitemap(self, url: str) -> Raspuns:
        return self._cu_redirecturi(
            url, {"Accept": "application/xml,text/xml"}, max_octeti=self.limite.max_octeti_pagina,
            tipuri=TIPURI_SITEMAP,
        )  # fmt: skip
