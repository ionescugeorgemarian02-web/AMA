"""`robots.txt` (RFC 9309), nucleu pur: reguli Allow / Disallow cu `*` și `$`, grupuri pe agent, Crawl-delay,
Sitemap. Biblioteca standard (`urllib.robotparser`) nu cunoaște metacaracterele și alege altfel regula
castigatoare, deci parserul e scris aici.

Alegerea regulii: grupul agentului cel mai specific (cea mai lungă potrivire a jetonului din `User-agent`
în numele nostru, apoi `*`); în grup, regula cu modelul cel mai lung câștigă, iar la egalitate `Allow`.
Starea cererii de `robots.txt` hotărăște comportamentul fără fișier (`din_status`): 404 / 410 → totul permis;
401 / 403, 5xx, 429 sau eroare de rețea → NIMIC permis (prudență).
"""

import re
from dataclasses import dataclass, field
from urllib.parse import unquote, urlsplit

MAXIM_OCTETI = 500 * 1024
CRAWL_DELAY_MAXIM_SEC = 60.0


@dataclass(frozen=True)
class Regula:
    permite: bool
    model: str

    def potriveste(self, cale: str) -> bool:
        return _regex(self.model).match(cale) is not None


@dataclass
class Grup:
    agenti: list[str] = field(default_factory=list)
    reguli: list[Regula] = field(default_factory=list)
    crawl_delay: float | None = None


@dataclass(frozen=True)
class Robots:
    grupuri: tuple[Grup, ...] = ()
    sitemapuri: tuple[str, ...] = ()
    interzis_tot: bool = False

    def _grup(self, agent: str) -> Grup | None:
        agent = agent.lower()
        cel_mai_bun: tuple[int, list[Grup]] = (-1, [])
        for g in self.grupuri:
            for a in g.agenti:
                if a == "*":
                    scor = 0
                elif a and a in agent:
                    scor = len(a)
                else:
                    continue
                if scor > cel_mai_bun[0]:
                    cel_mai_bun = (scor, [g])
                elif scor == cel_mai_bun[0] and g not in cel_mai_bun[1]:
                    cel_mai_bun[1].append(g)
        if not cel_mai_bun[1]:
            return None
        if len(cel_mai_bun[1]) == 1:
            return cel_mai_bun[1][0]
        imbinat = Grup(agenti=cel_mai_bun[1][0].agenti)  # grupuri cu același agent: se unesc
        for g in cel_mai_bun[1]:
            imbinat.reguli.extend(g.reguli)
            imbinat.crawl_delay = imbinat.crawl_delay if imbinat.crawl_delay is not None else g.crawl_delay
        return imbinat

    def permite(self, agent: str, url_sau_cale: str) -> bool:
        if self.interzis_tot:
            return False
        grup = self._grup(agent)
        if grup is None:
            return True
        cale = _cale(url_sau_cale)
        castigatoare: Regula | None = None
        for r in grup.reguli:
            if not r.model:
                continue  # `Disallow:` gol = nimic interzis
            if r.potriveste(cale) and (
                castigatoare is None
                or len(r.model) > len(castigatoare.model)
                or (len(r.model) == len(castigatoare.model) and r.permite and not castigatoare.permite)
            ):
                castigatoare = r
        return True if castigatoare is None else castigatoare.permite

    def crawl_delay(self, agent: str) -> float | None:
        grup = self._grup(agent)
        if grup is None or grup.crawl_delay is None:
            return None
        return min(max(grup.crawl_delay, 0.0), CRAWL_DELAY_MAXIM_SEC)


def _cale(url_sau_cale: str) -> str:
    p = urlsplit(url_sau_cale)
    cale = p.path or "/"
    if p.query:
        cale += "?" + p.query
    return unquote(cale) if "%" in cale else cale


_regex_cache: dict[str, re.Pattern[str]] = {}


def _regex(model: str) -> re.Pattern[str]:
    r = _regex_cache.get(model)
    if r is None:
        if len(_regex_cache) > 2000:
            _regex_cache.clear()
        ancorat = model.endswith("$")
        corp = model[:-1] if ancorat else model
        expr = ".*".join(re.escape(parte) for parte in corp.split("*"))
        r = _regex_cache[model] = re.compile(expr + ("$" if ancorat else ""), re.DOTALL)
    return r


def parseaza(continut: str) -> Robots:
    continut = continut[:MAXIM_OCTETI]
    grupuri: list[Grup] = []
    sitemapuri: list[str] = []
    curent: Grup | None = None
    ultima_a_fost_agent = False
    for linie in continut.splitlines():
        linie = linie.split("#", 1)[0].strip()
        if ":" not in linie:
            continue
        cheie, _, valoare = linie.partition(":")
        cheie, valoare = cheie.strip().lower(), valoare.strip()
        if cheie == "user-agent":
            if curent is None or not ultima_a_fost_agent:
                curent = Grup()
                grupuri.append(curent)
            curent.agenti.append(valoare.lower())
            ultima_a_fost_agent = True
            continue
        ultima_a_fost_agent = False
        if cheie == "sitemap":
            if valoare:
                sitemapuri.append(valoare)
        elif curent is None:
            continue
        elif cheie in ("allow", "disallow"):
            curent.reguli.append(Regula(cheie == "allow", valoare))
        elif cheie == "crawl-delay":
            try:
                curent.crawl_delay = float(valoare)
            except ValueError:
                continue
    return Robots(tuple(grupuri), tuple(sitemapuri))


def din_status(cod: int | None, continut: str = "") -> Robots:
    """`robots.txt` după răspunsul cererii (`cod` `None` = eroare de rețea)."""
    if cod is not None and 200 <= cod < 300:
        return parseaza(continut)
    if cod in (404, 410):
        return Robots()
    return Robots(interzis_tot=True)
