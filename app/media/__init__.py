"""Modulul media: biblioteca de active (F7.5), inboxul de tendințe și pipeline-ul media (F8, docs/14).

from app import media
media.biblioteca.incarca(db, tenant_id, corp, nume_original="poza.jpg", sursa="portal", utilizator_id=u)
n = media.voce.sintetizeaza(db, tenant_id, ["Bună dimineața din Brașov."])  # narațiune + licența vocii (F8.1)
"""

from app.media import audio, biblioteca, tendinte, voce

__all__ = ["audio", "biblioteca", "tendinte", "voce"]
