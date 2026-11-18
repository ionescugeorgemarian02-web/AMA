"""Alegerea modelelor pentru un apel (8.3): nucleu pur, fără bază și fără rețea.

Pașii din 8.3, ca date și funcții:
1. profilul declară nivelul minim, capabilitățile și lanțul ordonat de modele;
2. rămân doar modelele cu capabilitățile cerute și cu condiții de folosire potrivite (uz comercial confirmat,
   fără antrenare pe date când apelul are date confidențiale, nivelul profilului);
3. cad cele cu furnizor oprit sau pe pauză, fără cheie, cu întrerupătorul deschis;
4. restul se ordonează după scorul pe profil (îl umple F3.6; acum toate sunt 0), apoi după poziția în lanț.
Cota o decide limitatorul, încercând rezervarea în această ordine (un model fără cotă rămasă se sare).

Reguli în plus: un model T4 (Claude) nu rulează pe calea critică, adică la prioritate P0 sau P1 (ADR-06);
cu oprirea „apeluri plătite” activă cad modelele plătite; „alt model decât autorul” (judecată).
"""

import datetime as dt
from dataclasses import dataclass, field
from enum import StrEnum

from app.gateway import catalog
from app.gateway.candidat import RANG_NIVEL, Candidat
from app.gateway.intrerupator import StareSanatate, deschis
from app.gateway.profiluri import Profil
from app.operare.motor import Prioritate


class Motiv(StrEnum):
    FURNIZOR_OPRIT = "furnizor_oprit"  # inactiv sau pe pauză
    MODEL_OPRIT = "model_oprit"
    FARA_CHEIE = "fara_cheie"
    UZ_COMERCIAL = "uz_comercial"
    ANTRENARE_PE_DATE = "antrenare_pe_date"
    CAPABILITATE = "capabilitate_lipsa"
    NIVEL = "nivel_prea_mic"
    INTRERUPATOR = "intrerupator_deschis"
    T4_CALE_CRITICA = "t4_pe_calea_critica"
    APELURI_PLATITE = "apeluri_platite_oprite"
    ACELASI_MODEL = "acelasi_model_ca_autorul"
    LOCAL_COADA = "local_doar_pe_coada_greu"  # modelul local se apelează doar din joburi de pe coada `greu`
    MODEL_DE_VECTORI = "model_de_vectori"  # modelele de vectori nu generează text
    ACEEASI_FAMILIE = "aceeasi_familie_ca_autorul"  # G-pool: judecătorul din altă familie decât autorul
    MODEL_INDISPONIBIL = "model_indisponibil"  # G-pool: sănătatea modelului (404, erori repetate)
    CONTEXT_MIC = "context_sau_tpm_prea_mic"  # G-pool: cererea nu încape în context / tokeni pe minut


# Motive care înseamnă „nu are voie”, nu „nu e disponibil acum”: nu se rezolvă așteptând.
INTERZIS = frozenset({Motiv.T4_CALE_CRITICA, Motiv.APELURI_PLATITE, Motiv.LOCAL_COADA})


@dataclass(frozen=True)
class Cerinte:
    prioritate: Prioritate
    acum: dt.datetime
    capabilitati: frozenset[str] = frozenset()  # în plus față de ale profilului
    date_confidentiale: bool = False
    alt_model_decat: str | None = None  # `furnizor/identificator` al autorului (judecată)
    apeluri_platite_oprite: bool = False
    coada: str | None = (
        None  # coada jobului apelant (`greu` pentru modelul local); `None` = în afara unui job
    )
    model_fixat: str | None = None  # evaluare / diagnostic: doar acest model, fără lanțul profilului
    chei_configurate: frozenset[str] | None = None  # codurile furnizorilor cu cheie; `None` = nu se verifică
    sanatate: dict[str, StareSanatate] = field(default_factory=dict)  # pe cod de furnizor
    familie_autor: str | None = None  # G-pool: modelele din această familie cad (judecată „altă familie”)
    modele_indisponibile: frozenset[str] = frozenset()  # G-pool: coduri de modele puse pe pauză
    tokeni_estimati: int | None = None  # G-pool: verificarea prealabilă a contextului și a TPM


@dataclass(frozen=True)
class Selectie:
    principal: tuple[Candidat, ...]
    degradare: tuple[Candidat, ...]
    excluse: tuple[tuple[str, Motiv], ...]  # (cod model, motiv), din lanțul principal
    excluse_degradare: tuple[tuple[str, Motiv], ...] = ()  # la fel, din lanțul de degradare

    def motive(self) -> set[Motiv]:
        return {m for _, m in self.excluse}


def motiv_excludere(c: Candidat, profil: Profil, cer: Cerinte, *, degradare: bool) -> Motiv | None:
    """De ce NU poate fi folosit modelul în acest apel (primul motiv), sau `None`. Nivelul minim al
    profilului se
    aplică doar lanțului principal: lanțul de degradare există tocmai ca să coboare."""
    if "embeddings" in c.capabilitati:
        return Motiv.MODEL_DE_VECTORI
    if c.stare_furnizor != "activ":
        return Motiv.FURNIZOR_OPRIT
    if not c.model_activ:
        return Motiv.MODEL_OPRIT
    if cer.chei_configurate is not None and c.furnizor not in cer.chei_configurate:
        return Motiv.FARA_CHEIE
    if c.uz_comercial is not True:
        return Motiv.UZ_COMERCIAL
    if cer.date_confidentiale and c.antrenare_pe_date is not False:
        return Motiv.ANTRENARE_PE_DATE
    if not (profil.capabilitati | cer.capabilitati) <= c.capabilitati:
        return Motiv.CAPABILITATE
    if not degradare and c.rang < RANG_NIVEL[profil.nivel_min]:
        return Motiv.NIVEL
    if c.fara_cheie and cer.coada != "greu":
        return Motiv.LOCAL_COADA
    if c.nivel == "T4" and cer.prioritate in (Prioritate.P0, Prioritate.P1):
        return Motiv.T4_CALE_CRITICA
    if c.platit and cer.apeluri_platite_oprite:
        return Motiv.APELURI_PLATITE
    if cer.alt_model_decat is not None and c.cod == cer.alt_model_decat:
        return Motiv.ACELASI_MODEL
    if cer.familie_autor and c.familie == cer.familie_autor:
        return Motiv.ACEEASI_FAMILIE
    if c.cod in cer.modele_indisponibile:
        return Motiv.MODEL_INDISPONIBIL
    if cer.tokeni_estimati is not None and _prea_mare(c, cer.tokeni_estimati):
        return Motiv.CONTEXT_MIC
    sanatate = cer.sanatate.get(c.furnizor)
    if sanatate is not None and deschis(sanatate, cer.acum):
        return Motiv.INTRERUPATOR
    return None


def _prea_mare(c: Candidat, tokeni: int) -> bool:
    """Verificarea prealabilă (capacitatea fabricii): o cerere mai mare decât contextul modelului nu încape
    niciodată; nu are rost trimisă. Tokenii pe minut îi verifică deja limitatorul (refuz `imposibil`)."""
    return bool(c.context_tokeni) and tokeni > c.context_tokeni


def _expandeaza(lant: tuple[str, ...], candidati: list[Candidat]) -> list[tuple[Candidat, bool]]:
    """Intrările lanțului în ordine; `nivel:X` aduce toate modelele nivelului X, `rezerva:<rol>` rezervele
    rolului din catalogul G-pool, cu familiile alternate (cele necunoscute registrului se sar). Al doilea
    element spune dacă modelul vine dintr-o rezervă: o rezervă nepotrivită se sare în tăcere (nu apare la
    `excluse`), ca lanțul explicit să-și păstreze diagnosticul."""
    pe_cod = {c.cod: c for c in candidati}
    rezultat: list[tuple[Candidat, bool]] = []
    vazute: set[str] = set()
    for intrare in lant:
        rezerva = intrare.startswith("rezerva:")
        if intrare.startswith("nivel:"):
            grup = [c for c in candidati if c.nivel == intrare.removeprefix("nivel:")]
        elif rezerva:
            grup = [pe_cod[k] for k in catalog.rezerva_rol(intrare.removeprefix("rezerva:")) if k in pe_cod]
        else:
            grup = [pe_cod[intrare]] if intrare in pe_cod else []
        for c in grup:
            if c.cod not in vazute:
                vazute.add(c.cod)
                rezultat.append((c, rezerva))
    return rezultat


def _ordoneaza(lant: list[Candidat], profil: str) -> list[Candidat]:
    """Scor descrescător pe profil (lipsă = 0), apoi poziția în lanț. Înainte de F3.6 contează doar lanțul."""
    return [c for _, c in sorted(enumerate(lant), key=lambda p: (-p[1].scor.get(profil, 0.0), p[0]))]


def alege(profil: Profil, candidati: list[Candidat], cer: Cerinte) -> Selectie:
    if cer.model_fixat is not None:
        # Evaluare / diagnostic: un singur model, fără lanț și degradare; nivelul minim nu se aplică
        # (testul comparativ măsoară și modele mai slabe), celelalte reguli da.
        fixat = [c for c in candidati if c.cod == cer.model_fixat]
        ok = [c for c in fixat if motiv_excludere(c, profil, cer, degradare=True) is None]
        excluse_fix = tuple(
            (c.cod, m) for c in fixat if (m := motiv_excludere(c, profil, cer, degradare=True)) is not None
        )
        return Selectie(tuple(ok), (), excluse_fix)
    principal: list[Candidat] = []
    excluse: list[tuple[str, Motiv]] = []
    for c, din_rezerva in _expandeaza(profil.lant, candidati):
        motiv = motiv_excludere(c, profil, cer, degradare=False)
        if motiv is None:
            principal.append(c)
        elif not din_rezerva:
            excluse.append((c.cod, motiv))
    degradare: list[Candidat] = []
    excluse_degradare: list[tuple[str, Motiv]] = []
    for c, din_rezerva in _expandeaza(profil.lant_degradare, candidati):
        motiv = motiv_excludere(c, profil, cer, degradare=True)
        if motiv is None:
            degradare.append(c)
        elif not din_rezerva:
            excluse_degradare.append((c.cod, motiv))
    return Selectie(
        tuple(_ordoneaza(principal, profil.nume)),
        tuple(_ordoneaza(degradare, profil.nume)),
        tuple(excluse),
        tuple(excluse_degradare),
    )
