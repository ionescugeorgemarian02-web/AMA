"""Modulul media: biblioteca de active (F7.5), inboxul de tendințe și pipeline-ul media (F8, docs/14).

from app import media
media.biblioteca.incarca(db, tenant_id, corp, nume_original="poza.jpg", sursa="portal", utilizator_id=u)
n = media.voce.sintetizeaza(db, tenant_id, ["Bună dimineața din Brașov."])  # narațiune + licența vocii (F8.1)
media.pronuntie.pentru_voce(db, tenant_id, "Guji costă 49 lei.")  # normalizare + dicționarul clientului
(F8.2)
"""

from app.media import audio, biblioteca, normalizare, pronuntie, tendinte, voce

__all__ = ["audio", "biblioteca", "normalizare", "pronuntie", "tendinte", "voce"]
