"""Modulul media: biblioteca de active a clientului (F7.5) și inboxul de tendințe; pipeline-ul media vine
în F8.

from app import media
media.biblioteca.incarca(db, tenant_id, corp, nume_original="poza.jpg", sursa="portal", utilizator_id=u)
"""

from app.media import biblioteca, tendinte

__all__ = ["biblioteca", "tendinte"]
