"""Oferta, pâlnia și paginile de captare (F7.9): D2 propune, E3 scrie, cascada (G2, G3, G9) validează, un
om publică.

from app import oferta
pg = oferta.pagini.genereaza(db, tenant_id, firma=…, oferta=…, public=…, apel="Cere auditul gratuit",
                             tinta="/site/audit", slug="audit-gratuit")
oferta.pagini.publica(db, pg.id, utilizator_id=u)   # găzduită la /site/p/audit-gratuit
"""

from app.oferta import pagini

__all__ = ["pagini"]
