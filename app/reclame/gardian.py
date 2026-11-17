"""Gardianul de buget (F13.5, I3, docs/16 §16.4): reguli fixe, fără model. Nucleu pur.

Ce verifică, pe orice propunere care pornește sau mărește cheltuiala:
1. oprirea reclamelor (doar punerea pe pauză mai trece);
2. plafonul pe campanie, plafonul zilnic (suma bugetelor campaniilor active) și plafonul lunar (cheltuit +
   ritmul zilnic × zilele rămase) — „nu se depășesc niciodată”; peste plafon = refuz, cu cererea de aprobare a
   clientului;
3. creșterea maximă de buget pe zi (implicit 20%), perioada de așteptare după o schimbare (implicit 48 h) și
   numărul de schimbări automate pe zi (implicit 5) — reguli de ritm.
Scutiri (D-010): punerea pe pauză și scăderea bugetului trec mereu (reduc riscul); anularea unei schimbări și
decizia directă a proprietarului în panou sunt scutite de regulile de ritm, nu și de plafoane.
"""

import datetime as dt
from dataclasses import dataclass, field
from typing import Any

AUTOMATE = frozenset({"regula", "strateg", "test"})


@dataclass(frozen=True)
class Context:
    plafon_zilnic_bani: int
    plafon_lunar_bani: int
    plafon_campanie_bani: int
    schimbare_max_pct: int
    asteptare_ore: int
    schimbari_pe_zi: int
    suma_active_bani: int  # bugetele zilnice ale campaniilor active ale contului, fără campania propunerii
    cheltuit_luna_bani: int
    zile_ramase: int  # inclusiv azi
    schimbari_automate_azi: int
    ultima_schimbare: dt.datetime | None
    reclame_oprite: bool
    acum: dt.datetime


@dataclass(frozen=True)
class Verdict:
    permis: bool
    motive: list[str] = field(default_factory=list)
    cere_client: bool = False

    def ca_dict(self) -> dict[str, Any]:
        return {"permis": self.permis, "motive": self.motive, "cere_client": self.cere_client}


def verifica(tip: str, inainte: dict[str, Any], dupa: dict[str, Any], sursa: str, ctx: Context) -> Verdict:
    stare_noua = str(dupa.get("stare", inainte.get("stare", "pauza")))
    buget_vechi = int(inainte.get("buget_zilnic_bani", 0) or 0)
    buget_nou = int(dupa.get("buget_zilnic_bani", buget_vechi) or 0)
    if tip == "stare_anunt" or (tip == "creeaza" and stare_noua == "pauza"):
        # o reclamă dintr-o campanie sau o campanie nouă în pauză nu schimbă cheltuiala în sine
        return (
            Verdict(True)
            if not (ctx.reclame_oprite and stare_noua != "pauza")
            else Verdict(False, ["reclamele sunt oprite (oprire de urgență): repornirea e manuală"])
        )
    activa_dupa = stare_noua == "activa"
    if not activa_dupa or (tip == "buget" and buget_nou <= buget_vechi):
        return Verdict(True)  # pauză, schimbare pe o campanie oprită sau scădere: riscul nu crește
    if ctx.reclame_oprite:
        return Verdict(False, ["reclamele sunt oprite (oprire de urgență): repornirea e manuală"])
    motive: list[str] = []
    if buget_nou > ctx.plafon_campanie_bani:
        motive.append("bugetul zilnic trece de plafonul pe campanie")
    zilnic = ctx.suma_active_bani + buget_nou
    if zilnic > ctx.plafon_zilnic_bani:
        motive.append("bugetele zilnice ale campaniilor active ar trece de plafonul zilnic")
    if ctx.cheltuit_luna_bani + zilnic * max(1, ctx.zile_ramase) > ctx.plafon_lunar_bani:
        motive.append("în ritmul acesta cheltuiala lunii ar trece de plafonul lunar")
    if motive:
        return Verdict(
            False, [*motive, "o schimbare peste plafon cere aprobarea clientului"], cere_client=True
        )
    if sursa in ("anulare", "om"):
        return Verdict(True)
    if tip == "buget" and buget_vechi > 0:
        if (buget_nou - buget_vechi) * 100 > buget_vechi * ctx.schimbare_max_pct:
            motive.append(f"creștere peste {ctx.schimbare_max_pct}% într-o zi")
        if ctx.ultima_schimbare and ctx.acum - ctx.ultima_schimbare < dt.timedelta(hours=ctx.asteptare_ore):
            motive.append(
                f"perioada de așteptare de {ctx.asteptare_ore} de ore după ultima schimbare nu a trecut"
            )
    if sursa in AUTOMATE and ctx.schimbari_automate_azi >= ctx.schimbari_pe_zi:
        motive.append(f"s-au făcut deja {ctx.schimbari_pe_zi} schimbări automate azi pe acest cont")
    return Verdict(not motive, motive)
