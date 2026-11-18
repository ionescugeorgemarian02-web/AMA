"""Lista de conturi-țintă (F12.9, docs/17 §17.2): firme, nu persoane, cu mini-audit și trei argumente.

- **Surse publice** (registrul firmelor, hărți deschise, site-urile firmelor) printr-un adaptor; în mediul de
  probă `SursaFirmeSimulata` (# SIMULAT). Din ce vine de la sursă se păstrează **doar câmpurile despre firmă**
  (nume, domeniu, site, pagini publice ale firmei, localitate, semnale); descrierile libere, administratorii,
  telefoanele și adresele de email nu intră nicăieri.
- **Fără date personale, verificat de două ori:** firmele care sunt persoane fizice (PFA, II, IF: numele lor e
  numele unui om) se exclud; orice valoare păstrată trece prin detectorul gateway-ului
  (`gateway.detecteaza_date_personale`: email, telefon, CNP, IBAN, card, IP) și, dacă are ceva, se aruncă.
  O pagină socială se păstrează doar dacă adresa ei poartă numele firmei (nu profilul unui om).
- **Mini-auditul** e cel al site-ului (motorul de audit din F7.2), plus semnalele sursei (site lent, pagini
  neactualizate); din ele ies **trei argumente de discuție**.
- **Platforma nu trimite singură nimic către această listă** (17.2): modulul nu are legătură cu emailul sau cu
  efectele; tu sau un om de vânzări contactați personal. Testul static ține regula.
"""

import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app import gateway
from app.crm.modele import ContTinta
from app.crm.registru import FORME_JURIDICE, CrmRefuzat, domeniu, norma_firma
from app.operare import audit, urme

PERSOANE_FIZICE = {"pfa", "ii", "if"}  # numele unei asemenea firme e numele unui om
PLATFORME = {"facebook.com", "instagram.com", "tiktok.com", "linkedin.com", "youtube.com"}
SURSE = ("registru_public", "harti_deschise", "site_firma")
LISTA = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
SEMNALE = {
    "site_lent": "site-ul se încarcă greu pe telefon",
    "pagini_neactualizate": "paginile sociale nu au mai fost actualizate de luni de zile",
    "fara_pret": "prețurile nu apar pe site",
    "fara_https": "site-ul nu are conexiune securizată",
}


@dataclass(frozen=True)
class FirmaPublica:
    """O firmă, așa cum vine de la o sursă publică (poate conține și ce nu păstrăm)."""

    nume: str
    site: str
    localitate: str
    sursa: str
    pagini: tuple[str, ...] = ()
    semnale: tuple[str, ...] = ()
    extra: dict[str, str] = field(default_factory=dict)  # descrieri, administratori, telefoane: se aruncă


class SursaFirme(Protocol):
    def cauta(self, nisa: str, localitate: str) -> list[FirmaPublica]: ...


class SursaFirmeSimulata:
    """# SIMULAT: câteva firme publice dintr-o nișă, cu capcanele datelor reale (persoane, telefoane)."""

    def cauta(self, nisa: str, localitate: str) -> list[FirmaPublica]:
        return [
            FirmaPublica(
                "Cafeneaua Boema SRL",
                "https://boema.example",
                localitate,
                "registru_public",
                ("https://facebook.com/cafeneauaboema", "https://instagram.com/ana.popescu.88"),
                ("site_lent", "pagini_neactualizate"),
                {"administrator": "Ana Popescu", "telefon": "0722 123 456"},
            ),
            FirmaPublica(
                "Bistro Central",
                "https://bistro-central.example",
                localitate,
                "harti_deschise",
                ("https://instagram.com/bistrocentral",),
                ("fara_pret",),
                {"descriere": "Scrieți-ne la rezervari@bistro-central.example sau sunați la 0744000111"},
            ),
            FirmaPublica("Popescu Ion PFA", "https://popescu-ion.example", localitate, "registru_public"),
            FirmaPublica(
                "Patiseria Dulce SRL", "http://dulce.example", localitate, "site_firma", (), ("fara_https",)
            ),
            FirmaPublica("Contact 0722111222 SRL", "https://telefon.example", localitate, "harti_deschise"),
        ]


SURSA: SursaFirme = SursaFirmeSimulata()


def are_date_personale(valoare: str) -> bool:
    return bool(gateway.detecteaza_date_personale(valoare))


def persoana_fizica(nume: str) -> bool:
    return bool(set(re.findall(r"[a-z]+", nume.lower())) & PERSOANE_FIZICE)


def pagina_a_firmei(url: str, nume: str) -> bool:
    p = urlsplit(url if "://" in url else f"https://{url}")
    gazda = (p.hostname or "").removeprefix("www.")
    if gazda not in PLATFORME or are_date_personale(url):
        return False
    slug = re.sub(r"[^a-z0-9]", "", p.path.lower())
    cuvinte = [c for c in norma_firma(nume).split() if c not in FORME_JURIDICE and len(c) >= 4]
    return bool(cuvinte) and all(c in slug for c in cuvinte)


def curata(f: FirmaPublica) -> dict[str, Any] | None:
    """Doar câmpurile despre firmă, fără nimic personal. None: firma nu intră în listă."""
    if persoana_fizica(f.nume) or f.sursa not in SURSE:
        return None
    dom = domeniu(f.site)
    if dom is None or any(are_date_personale(v) for v in (f.nume, f.site, f.localitate)):
        return None
    return {
        "nume": f.nume.strip()[:200],
        "domeniu": dom,
        "site": f.site.strip()[:300],
        "localitate": f.localitate.strip()[:80],
        "sursa": f.sursa,
        "pagini": [u for u in f.pagini if pagina_a_firmei(u, f.nume)],
        "semnale": [s for s in f.semnale if s in SEMNALE],
    }


def argumente(mini: dict[str, Any], semnale: list[str]) -> list[str]:
    """Trei argumente de discuție: întâi semnalele, apoi constatările auditului."""
    surse = [f"Am observat că {SEMNALE[s]}." for s in semnale]
    surse += [str(c) for c in mini.get("constatari", [])]
    surse += [str(r) for r in mini.get("recomandari", [])]
    return (surse + ["Un audit gratuit arată ce aduce cele mai multe cereri din site."] * 3)[:3]


def construieste(
    db: Session,
    *,
    nisa: str,
    localitate: str,
    utilizator_id: uuid.UUID | None = None,
    sursa: SursaFirme | None = None,
) -> tuple[str, int]:
    """Construiește (sau completează) lista nișei și localității. Întoarce numele listei și câte firme noi."""
    from app.site import motor_audit  # import târziu: site-ul importă CRM-ul

    nisa, localitate = nisa.strip().lower(), localitate.strip()
    lista = "-".join(norma_firma(f"{nisa} {localitate}").split())
    if not LISTA.match(lista) or not 2 <= len(nisa) <= 60 or not 2 <= len(localitate) <= 80:
        raise CrmRefuzat("nișa și localitatea trebuie să fie cuvinte simple")
    noi, excluse = 0, 0
    for f in (sursa or SURSA).cauta(nisa, localitate):
        date = curata(f)
        if date is None:
            excluse += 1
            continue
        mini = motor_audit.motor().ruleaza(date["nume"], date["site"])
        mini = {k: mini.get(k) for k in ("rezumat", "constatari", "recomandari")}
        if are_date_personale(str(mini)):
            mini = {
                "rezumat": "Mini-auditul a fost omis: conținea date personale.",
                "constatari": [],
                "recomandari": [],
            }
        r = db.execute(
            insert(ContTinta)
            .values(
                lista=lista, nisa=nisa, mini_audit=mini, argumente=argumente(mini, date["semnale"]), **date
            )
            .on_conflict_do_nothing(index_elements=["lista", "domeniu"])
            .returning(ContTinta.id)
        ).first()
        noi += r is not None
    audit.record(
        db,
        "crm.conturi_tinta",
        obiect_tip="lista",
        obiect_id=lista,
        utilizator_id=utilizator_id,
        detalii={"noi": noi, "excluse": excluse},
    )
    urme.inregistreaza(
        db,
        "crm",
        "conturi_tinta",
        obiect_tip="lista",
        obiect_id=lista,
        intrari={"nisa": nisa, "localitate": localitate},
        iesiri={"noi": noi, "excluse": excluse},
    )
    return lista, noi


def din_lista(db: Session, lista: str) -> list[ContTinta]:
    return list(db.scalars(select(ContTinta).where(ContTinta.lista == lista).order_by(ContTinta.nume)))


def liste(db: Session) -> list[str]:
    return list(db.scalars(select(ContTinta.lista).distinct().order_by(ContTinta.lista)))


def marcheaza(db: Session, cont_id: uuid.UUID, stare: str, *, utilizator_id: uuid.UUID) -> None:
    """Omul notează că a contactat firma (personal) sau că nu e potrivită. Platforma nu contactează."""
    if stare not in ("contactat", "respins"):
        raise CrmRefuzat("stare necunoscută")
    c = db.get(ContTinta, cont_id)
    if c is None:
        raise CrmRefuzat("firmă inexistentă")
    c.stare = stare
    audit.record(
        db,
        "crm.cont_tinta_marcat",
        obiect_tip="cont_tinta",
        obiect_id=c.id,
        utilizator_id=utilizator_id,
        detalii={"stare": stare},
    )
