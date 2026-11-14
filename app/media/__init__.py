"""Modulul media: biblioteca de active (F7.5), inboxul de tendințe și pipeline-ul media (F8, docs/14).

from app import media
media.biblioteca.incarca(db, tenant_id, corp, nume_original="poza.jpg", sursa="portal", utilizator_id=u)
n = media.voce.sintetizeaza(db, tenant_id, ["Bună dimineața din Brașov."])  # narațiune + licența vocii (F8.1)
media.pronuntie.pentru_voce(db, tenant_id, "Guji costă 49 lei.")  # normalizare + dicționarul (F8.2)
v = media.transcriere.naratiune_verificata(db, tenant_id, fraze)  # timpi pe cuvânt, fraze greșite (F8.3)
a = media.furnizori.aduce_stock(db, tenant_id, media.furnizori.cauta_stock("cafea")[0])  # cu licența (F8.4)
media.licente.foloseste(db, a.id, scop="montaj")  # singura cale de folosire: fără licență, refuz (F8.4)
lm = media.regizor.regizeaza(db, tenant_id, fraze=fr, naratiune=v, materiale=active)  # lista (F8.5)
"""

from app.media import (
    audio,
    biblioteca,
    ffmpeg,
    furnizori,
    licente,
    lista,
    normalizare,
    pronuntie,
    regizor,
    tendinte,
    transcriere,
    voce,
)

__all__ = [
    "audio",
    "biblioteca",
    "ffmpeg",
    "furnizori",
    "licente",
    "lista",
    "normalizare",
    "pronuntie",
    "regizor",
    "tendinte",
    "transcriere",
    "voce",
]
