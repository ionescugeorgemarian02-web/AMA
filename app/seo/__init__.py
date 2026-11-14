"""Cercetarea SEO și articolele (F7.10, C6, E5, E7): grupuri pe intenție, brief SEO, articol în trei pași,
lista
on-page deterministă, validare, publicare pe blogul agenției cu sursele citate.

    from app import seo
    for g in seo.cuvinte.grupeaza(["cum alegi cafeaua de specialitate", …]):
        seo.articole.scrie(db, tenant_id_agentie, g, surse)
"""

from app.seo import articole, cuvinte

__all__ = ["articole", "cuvinte"]
