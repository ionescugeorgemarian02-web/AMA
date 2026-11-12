"""Gărzile gateway-ului (F3.9) ca interceptori: injecții (ordinea 5) și date personale (ordinea 10),
înaintea bugetului.

- `garda_injectii`: caută tentative de injecție în blocurile de date externe (și în afara lor: text
  nemarcat care arată a instrucțiune), adaugă la mesajul de sistem instrucțiunea „date, nu instrucțiuni”
  când există blocuri externe și lasă SEMNALE (în jurnalul de apeluri și în jurnalul aplicației, fără
  conținut). Nu blochează: textul a intrat oricum ca date.
- `garda_date_personale`: maschează deterministic mesajele (G12) înainte de rutare. Ce ajunge la furnizor,
  în jurnal și în conținutul păstrat este varianta mascată; opțional, răspunsul se demască pentru apelant
  (`demasca=True`).
Furnizorii care antrenează pe date nu primesc conținut marcat confidențial: `date_confidentiale` ajunge în
rutare (F3.4).
"""

from typing import Any

from app.gateway import extern, injectii, interceptori
from app.gateway.mascare import Masca
from app.gateway.tipuri import Mesaj
from app.logging import get_logger

log = get_logger("app.gateway")


def semnale(ctx: Any) -> list[dict[str, Any]]:
    return ctx.extra.setdefault("semnale", [])  # type: ignore[no-any-return]


class GardaInjectii:
    nume = "garda_injectii"

    def inainte(self, ctx: Any) -> None:
        gasite: list[injectii.Semnal] = []
        are_blocuri = False
        for m in ctx.mesaje:
            if extern.are_blocuri(m.continut):
                are_blocuri = True
            for sursa, corp in extern.blocuri(m.continut):
                gasite += injectii.cauta(corp, sursa)
            if m.rol == "user":
                in_afara = extern.BLOC.sub("", m.continut)
                gasite += injectii.cauta(in_afara, "nemarcat")
        if are_blocuri:
            ctx.mesaje = _cu_instructiune(ctx.mesaje)
        if gasite:
            unice = sorted({(s.cod, s.sursa) for s in gasite})
            semnale(ctx).extend({"tip": "injectie_suspecta", "cod": c, "sursa": s} for c, s in unice)
            log.warning(
                "posibilă tentativă de injecție în conținut extern",
                extra={
                    "tenant": str(ctx.tenant_id), "componenta": ctx.componenta,
                    "coduri": sorted({c for c, _ in unice}),
                },
            )  # fmt: skip

    def dupa(self, ctx: Any, rezultat: Any, eroare: BaseException | None) -> None:
        return None


def _cu_instructiune(mesaje: tuple[Mesaj, ...]) -> tuple[Mesaj, ...]:
    if mesaje and mesaje[0].rol == "system":
        if extern.INSTRUCTIUNE in mesaje[0].continut:
            return mesaje
        return (Mesaj("system", mesaje[0].continut + "\n\n" + extern.INSTRUCTIUNE), *mesaje[1:])
    return (Mesaj("system", extern.INSTRUCTIUNE), *mesaje)


class GardaDatePersonale:
    nume = "garda_date_personale"

    def inainte(self, ctx: Any) -> None:
        masca = Masca(cui=bool(getattr(ctx, "mascheaza_cui", False)))
        ctx.mesaje = tuple(Mesaj(m.rol, masca.text(m.continut)) for m in ctx.mesaje)
        ctx.extra["masca"] = masca
        if masca.rezumat():
            semnale(ctx).append({"tip": "date_personale_mascate", "pe_tip": masca.rezumat()})

    def dupa(self, ctx: Any, rezultat: Any, eroare: BaseException | None) -> None:
        return None


def inregistreaza() -> None:
    interceptori.adauga(GardaInjectii(), ordine=5)
    interceptori.adauga(GardaDatePersonale(), ordine=10)
