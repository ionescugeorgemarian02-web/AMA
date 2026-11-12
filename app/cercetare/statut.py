"""Statutul surselor (docs/12 §12.1) ca DATE: ce are voie colectorul și ce nu.

Fiecare sursă a unui client are un statut; statutul hotărăște dacă platforma o poate citi automat (crawl
politicos), dacă acceptă încărcare manuală și dacă textul colectat se poate reutiliza în livrabile (docs/21
§21.11: materialele concurenței se analizează, nu se refolosesc). Sursele cu „fără API oficial” sau „scraping
interzis de termeni” nu au crawl: intră doar manual, prin inboxul de tendințe (12.2).
"""

from dataclasses import dataclass
from urllib.parse import urlsplit

from app.cercetare.url_utile import domeniu_inregistrat


@dataclass(frozen=True)
class StatutSursa:
    cod: str
    eticheta: str
    din_12_1: str  # rândul din tabelul 12.1
    crawl_automat: bool
    incarcare_manuala: bool
    reutilizare_text: bool  # textul poate ajunge, ca atare, în livrabile (altfel doar analiză)
    nota: str


STATUTE: dict[str, StatutSursa] = {
    s.cod: s
    for s in (
        StatutSursa(
            "site_client",
            "Site-ul clientului",
            "Site-ul și materialele clientului",
            True,
            True,
            True,
            "Crawl cu permisiunea clientului, cu respectarea robots.txt.",
        ),
        StatutSursa(
            "material_client",
            "Materiale ale clientului",
            "Site-ul și materialele clientului",
            False,
            True,
            True,
            "Text lipit sau fișier text / markdown încărcat de client.",
        ),
        StatutSursa(
            "recenzii_client",
            "Recenzii publice ale clientului",
            "Recenziile publice ale clientului",
            False,
            True,
            True,
            "API cu acces aprobat sau încărcare manuală; nu se citesc automat paginile platformelor.",
        ),
        StatutSursa(
            "site_concurenta",
            "Site public al concurenței",
            "Site-urile publice ale concurenței",
            True,
            True,
            False,
            "Crawl politicos, cu respectarea robots.txt, doar pentru analiză; textul nu se reutilizează.",
        ),
        StatutSursa(
            "tendinte_retele",
            "Tendințe TikTok și Instagram",
            "Tendințe TikTok și Instagram",
            False,
            True,
            False,
            "Fără API oficial; scraping interzis de termeni. Doar prin inboxul de tendințe.",
        ),
        StatutSursa(
            "reddit",
            "Reddit",
            "Reddit",
            False,
            True,
            False,
            "Gratuit doar necomercial. Nu automat; doar observații lipite de un om.",
        ),
        StatutSursa(
            "google_ads_transparency",
            "Google Ads Transparency Center",
            "Google Ads Transparency Center",
            False,
            True,
            False,
            "Fără API oficial. Doar manual.",
        ),
    )
}

# Domenii pe care colectorul nu le citește niciodată automat, oricare ar fi statutul declarat (12.1: fără API
# oficial / scraping interzis de termeni / acces doar prin API). Lista de domenii permise și interzise
# editabilă din
# panou (12.3) rămâne propunere.
DOMENII_FARA_CRAWL = frozenset(
    {
        "tiktok.com",
        "instagram.com",
        "facebook.com",
        "fb.com",
        "reddit.com",
        "google.com",
        "youtube.com",
        "x.com",
        "twitter.com",
        "linkedin.com",
        "whatsapp.com",
        "t.me",
    }
)


class SursaInterzisa(ValueError):
    """Statutul sau domeniul sursei nu permite operațiunea cerută."""


def statut(cod: str) -> StatutSursa:
    try:
        return STATUTE[cod]
    except KeyError:
        raise SursaInterzisa(f"statut necunoscut: {cod}") from None


def verifica_site(cod_statut: str, url: str) -> None:
    """Un site se poate citi automat doar dacă statutul o permite și domeniul nu e pe lista interzisă."""
    s = statut(cod_statut)
    if not s.crawl_automat:
        raise SursaInterzisa(f"„{s.eticheta}”: {s.nota}")
    gazda = urlsplit(url).hostname or ""
    if domeniu_inregistrat(gazda) in DOMENII_FARA_CRAWL:
        raise SursaInterzisa(
            f"{gazda}: domeniu care nu se citește automat (termeni sau lipsa unui API oficial)"
        )


def verifica_manual(cod_statut: str) -> None:
    s = statut(cod_statut)
    if not s.incarcare_manuala:
        raise SursaInterzisa(f"„{s.eticheta}” nu acceptă încărcare manuală")
