"""Anunțuri către oameni, trimise DUPĂ ce tranzacția s-a încheiat cu bine.

O notificare trimisă în mijlocul unei tranzacții care apoi se anulează ar anunța ceva ce nu s-a întâmplat.
`dupa_commit` leagă trimiterea de commit-ul sesiunii; la rollback nu se trimite nimic. Textele nu au voie să
conțină date de client sau secrete (doar tipul livrabilului, canalul și termenul).
"""

from collections.abc import Callable

from sqlalchemy import event
from sqlalchemy.orm import Session

from app.logging import get_logger
from app.operare import notificari
from app.operare.notificari import Nivel

log = get_logger("app.productie")


def dupa_commit(db: Session, actiune: Callable[[], object]) -> None:
    def ruleaza(_sesiune: Session) -> None:
        try:
            actiune()
        except Exception as exc:  # un canal căzut nu strică lucrul început
            log.warning("anunț nereușit", extra={"tip_eroare": type(exc).__name__})

    event.listen(db, "after_commit", ruleaza, once=True)


def anunta(db: Session, nivel: Nivel, titlu: str, text: str, *, url: str = "/alerte") -> None:
    dupa_commit(db, lambda: notificari.notifica(nivel, titlu, text, url=url))
