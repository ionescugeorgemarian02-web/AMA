"""Alegerea adaptivă (F11.3, treapta N4, docs/11 §11.4): ce tipar de hook și ce slot să fie folosite mai des.

Un „bandit” cu eșantionare Thompson, câteva zeci de linii, fără bibliotecă specializată:

- **Variantele**: valorile unei etichete (tiparul de hook, slotul), cu recompensele postărilor care le-au
  folosit (F10.3: interacțiuni raportate la afișări, citite la 72 de ore: recompensa e deci întârziată).
- **Starea unei variante**: o distribuție Beta(α, β). Fiecare postare adaugă recompensa ei la α și restul
  până la 1 la β, cu o **pondere care scade liniar la zero în 90 de zile** (rezultatele vechi cântăresc
  mai puțin).
- **Pornire la rece**: orice variantă pornește de la media nișei (`MEDIE_NISA`, cu greutatea a două
  postări), nu de la zero. Media nișei e o constantă de pornire [I]; mediile agregate pe nișă, din datele
  mai multor clienți, NU sunt construite (cer categoria de nișă pe client și clauza din contract, 11.6).
- **Alegerea**: cu probabilitatea `EXPLORARE` (15%) se alege o variantă dintre cele mai puțin testate;
  altfel se trage câte o valoare din distribuția fiecărei variante și câștigă cea mai mare. Generatorul de
  numere e dat din afară (în teste, cu sămânță fixă).
- **Unde se aplică**: la alegerea hook-ului (F6.3), prin punctul de extensie
  `continut.scriere.inregistreaza_preferinta_tipar`: preferința doar departajează variantele de calitate
  apropiată. Pentru sloturi dă o recomandare ordonată (`recomanda`); mutarea automată a sloturilor de
  publicare (F9.7) nu e legată aici.
"""

import datetime as dt
import random
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import productie
from app.analiza import EtichetePostare, etichete
from app.continut import scriere

EXPLORARE = 0.15  # 11.4: cel puțin 15% din alegeri merg pe variante mai puțin testate
FEREASTRA_ZILE = 90
MEDIE_NISA = 0.03  # [I] interacțiuni pe afișare, punctul de pornire al unei variante noi
GREUTATE_PORNIRE = 2.0  # cât cântărește media nișei, în postări
PUBLICARI_MINIME = 10  # 11.2: sub atâtea publicări pe variantă, concluzia e fragilă
TIP = "interactiuni_pe_afisari"
DIMENSIUNI = ("tipar_hook", "slot")


@dataclass(frozen=True)
class Observatie:
    varianta: str
    recompensa: float  # între 0 și 1
    vechime_zile: float


@dataclass(frozen=True)
class Varianta:
    valoare: str
    alfa: float
    beta: float
    publicari: int  # câte postări au folosit-o în fereastră

    @property
    def medie(self) -> float:
        return self.alfa / (self.alfa + self.beta)

    @property
    def de_incredere(self) -> bool:
        return self.publicari >= PUBLICARI_MINIME


def pondere(vechime_zile: float) -> float:
    """Scade liniar de la 1 (azi) la 0 (la 90 de zile și peste)."""
    return max(0.0, 1.0 - max(0.0, vechime_zile) / FEREASTRA_ZILE)


def stare(
    optiuni: list[str], observatii: list[Observatie], *, medie_nisa: float = MEDIE_NISA
) -> list[Varianta]:
    """Nucleu pur: distribuția fiecărei opțiuni, pornind de la media nișei."""
    out = []
    for o in optiuni:
        alfa, beta, n = medie_nisa * GREUTATE_PORNIRE, (1 - medie_nisa) * GREUTATE_PORNIRE, 0
        for x in observatii:
            w = pondere(x.vechime_zile)
            if x.varianta == o and w > 0:
                r = min(1.0, max(0.0, x.recompensa))
                alfa, beta, n = alfa + w * r, beta + w * (1 - r), n + 1
        out.append(Varianta(o, alfa, beta, n))
    return out


def alege(variante: list[Varianta], rng: random.Random, *, explorare: float = EXPLORARE) -> Varianta:
    """Nucleu pur: explorare garantată, apoi eșantionare Thompson."""
    if not variante:
        raise ValueError("nicio variantă de ales")
    if rng.random() < explorare:
        minim = min(v.publicari for v in variante)
        return rng.choice([v for v in variante if v.publicari == minim])
    return max(variante, key=lambda v: rng.betavariate(v.alfa, v.beta))


def _observatii(db: Session, tenant_id: uuid.UUID, dimensiune: str, acum: dt.datetime) -> list[Observatie]:
    de_la = acum - dt.timedelta(days=FEREASTRA_ZILE)
    randuri = db.execute(
        select(EtichetePostare).where(
            EtichetePostare.tenant_id == tenant_id,
            EtichetePostare.recompensa.is_not(None),
            EtichetePostare.recompensa_tip == TIP,
            EtichetePostare.publicat_la >= de_la,
        )
    ).scalars()
    out = []
    for r in randuri:
        valoare = (
            r.tipar_hook if dimensiune == "tipar_hook" else etichete.eticheta_slot(r.zi_saptamana, r.ora)
        )
        if valoare:
            zile = (acum - r.publicat_la).total_seconds() / 86400
            out.append(Observatie(valoare, float(r.recompensa or 0.0), zile))
    return out


def variante_client(
    db: Session,
    tenant_id: uuid.UUID,
    dimensiune: str,
    optiuni: list[str] | None = None,
    *,
    acum: dt.datetime | None = None,
) -> list[Varianta]:
    """Starea variantelor unui client pe o dimensiune (`tipar_hook` sau `slot`), cea mai bună medie întâi.
    Fără `optiuni`, variantele sunt cele deja întâlnite. Datele sunt doar ale clientului (11.6, punctul 7)."""
    if dimensiune not in DIMENSIUNI:
        raise ValueError(f"dimensiune necunoscută: {dimensiune}")
    obs = _observatii(db, tenant_id, dimensiune, acum or dt.datetime.now(dt.UTC))
    opt = optiuni if optiuni is not None else sorted({o.varianta for o in obs})
    return sorted(stare(opt, obs), key=lambda v: (-v.medie, v.valoare))


def recomanda(
    db: Session,
    tenant_id: uuid.UUID,
    dimensiune: str,
    optiuni: list[str],
    rng: random.Random | None = None,
    *,
    acum: dt.datetime | None = None,
) -> str | None:
    """Varianta de folosit acum, dintre `optiuni`; `None` dacă nu e nimic de ales."""
    if not optiuni:
        return None
    # Tragerea nu apără nimic secret: e un generator obișnuit, cu sămânță dată în teste.
    rng = rng or random.Random()  # noqa: S311
    return alege(
        variante_client(db, tenant_id, dimensiune, list(dict.fromkeys(optiuni)), acum=acum), rng
    ).valoare


def _preferinta_tipar(db: Session, lv: productie.Livrabil, tipare: list[str]) -> str | None:
    """Fără nicio postare măsurată a clientului nu există preferință: o tragere la întâmplare între variante
    egale ar schimba alegerea hook-ului fără niciun temei."""
    optiuni = list(dict.fromkeys(tipare))
    variante = variante_client(db, lv.tenant_id, "tipar_hook", optiuni)
    if not optiuni or all(v.publicari == 0 for v in variante):
        return None
    return alege(variante, random.Random()).valoare  # noqa: S311  # nu apără nimic secret


scriere.inregistreaza_preferinta_tipar(_preferinta_tipar)
