"""Punctul de extensie al apelurilor: interceptori înainte și după fiecare apel prin gateway.

F3.8 (bugete și priorități) și F3.9 (gărzile de date personale și de injecții) se agață aici, fără să schimbe
gateway-ul. Un interceptor este orice obiect cu un `nume` și două metode:

    class Mascare:
        nume = "mascare_date_personale"

        def inainte(self, ctx: ContextApel) -> None:
            ctx.mesaje = tuple(masca(m) for m in ctx.mesaje)   # poate înlocui mesajele
            ctx.date_confidentiale = True                      # poate cere reguli mai stricte de rutare
            # poate opri apelul: raise gateway.Amanat(...) / gateway.ApelRefuzat("buget_client", "...")

        def dupa(self, ctx: ContextApel, rezultat: Rezultat | None, eroare: BaseException | None) -> None:
            # contorizare; o eroare aici NU schimbă rezultatul
            ...

    gateway.adauga_interceptor(Mascare(), ordine=10)

`inainte` rulează o singură dată, înaintea rutării (deci peste toate încercările și toate modelele), în
ordinea
crescătoare a `ordine`; `dupa` rulează mereu, în ordine inversă, cu rezultatul sau cu eroarea apelului.
Interceptorii sunt ai procesului (se înregistrează la import, ca fluxurile).
"""

from typing import Any, Protocol

from app.logging import get_logger

log = get_logger("app.gateway")


class Interceptor(Protocol):
    nume: str

    def inainte(self, ctx: Any) -> None: ...

    def dupa(self, ctx: Any, rezultat: Any, eroare: BaseException | None) -> None: ...


_interceptori: list[tuple[int, Interceptor]] = []


def adauga(interceptor: Interceptor, ordine: int = 100) -> None:
    """Înregistrează (sau înlocuiește, după `nume`) un interceptor."""
    elimina(interceptor.nume)
    _interceptori.append((ordine, interceptor))
    _interceptori.sort(key=lambda p: p[0])


def elimina(nume: str) -> None:
    _interceptori[:] = [(o, i) for o, i in _interceptori if i.nume != nume]


def toti() -> list[Interceptor]:
    return [i for _, i in _interceptori]


def ruleaza_inainte(ctx: Any) -> None:
    for i in toti():
        i.inainte(ctx)


def ruleaza_dupa(ctx: Any, rezultat: Any, eroare: BaseException | None) -> None:
    for i in reversed(toti()):
        try:
            i.dupa(ctx, rezultat, eroare)
        except Exception as exc:  # contorizarea de după apel nu are voie să schimbe ce a primit apelantul
            log.warning(
                "interceptor eșuat după apel", extra={"interceptor": i.nume, "tip_eroare": type(exc).__name__}
            )
