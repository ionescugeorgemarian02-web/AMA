"""Publicarea (F6.6): modul asistat al editorului multi-canal (H1). Publicarea prin API (F9) vine aici, prin
executorul
de efecte.

    from app import publicare

    p = publicare.asistata.pregateste(db, livrabil_id)          # aprobat → programat; pachetul pe telefon
    publicare.asistata.confirma(db, p.id, link=url, utilizator_id=om)   # programat → publicat, cu linkul
"""

from app.publicare import aprobari, asistata, canale
from app.publicare.modele import PublicareAsistata

__all__ = ["PublicareAsistata", "aprobari", "asistata", "canale"]
