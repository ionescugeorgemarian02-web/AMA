"""G1 Structură (V0, docs/09 §9.4): câmpurile obligatorii pe tip de livrabil (13.3), lungimile pe canal
(15.1), limba
română și linkurile bine formate. Datele sunt în `date/structura.toml` (lungimile sunt valori de pornire
[I]).
Nucleul (`probleme_structura`) este pur; validatorul înregistrat doar îl cheamă. Linkurile NU se verifică în
rețea."""

from typing import Any

from app.validare import registru, text_ro
from app.validare.date_validare import incarca
from app.validare.intrare import Continut, Intrare
from app.validare.probleme import Problema, verdict_din_probleme
from app.validare.verdict import Severitate, Treapta, Verdict

COD = "G1"
VERSIUNE = "1"


def _goala(valoare: Any) -> bool:
    if valoare is None:
        return True
    if isinstance(valoare, str):
        return not valoare.strip()
    if isinstance(valoare, list | tuple | dict):
        return len(valoare) == 0
    return False


def _valoare(continut: Continut, camp: str) -> Any:
    return continut.text if camp == "text" else continut.campuri.get(camp)


def _lungimea(valoare: Any, camp: str) -> int | None:
    if camp.endswith("_nr"):
        return len(valoare) if isinstance(valoare, list | tuple) else None
    return len(valoare) if isinstance(valoare, str) else None


def _probleme_campuri(tip: str, continut: Continut) -> list[Problema]:
    regula_tip = incarca("structura")["tipuri"].get(tip)
    if regula_tip is None:
        return []
    probleme = []
    for camp in regula_tip.get("obligatorii", []):
        if _goala(_valoare(continut, camp)):
            probleme.append(
                Problema(
                    "G1.camp_lipsa",
                    "",
                    f"Completează câmpul obligatoriu „{camp}” al livrabilului „{tip}”.",
                    detalii=f"câmp lipsă: {camp}",
                )
            )
    for camp, lim in regula_tip.get("liste", {}).items():
        val = continut.campuri.get(camp)
        if not isinstance(val, list):
            continue  # lipsa e raportată mai sus, dacă e obligatoriu
        n = len(val)
        if n < lim.get("min", 0) or n > lim.get("max", 10**9):
            probleme.append(
                Problema(
                    "G1.lista_in_afara_limitelor",
                    f"{camp}: {n} elemente",
                    f"„{camp}” trebuie să aibă între {lim.get('min', 0)} și {lim.get('max', '∞')} "
                    f"elemente "
                    f"(are {n}).",
                    detalii=f"{camp}: {n}",
                )
            )
    return probleme


def _probleme_lungimi(canal: str, continut: Continut) -> list[Problema]:
    limite = incarca("structura")["limite"].get(canal, {})
    probleme = []
    for camp, lim in limite.items():
        baza = camp.removesuffix("_nr")
        valori: list[tuple[str, Any]] = [(camp, _valoare(continut, baza))]
        if camp == "titlu" and isinstance(continut.campuri.get("titluri"), list):
            valori += [(f"titluri[{i}]", t) for i, t in enumerate(continut.campuri["titluri"])]
        for nume, val in valori:
            n = _lungimea(val, camp)
            if n is None:
                continue
            unitate = "elemente" if camp.endswith("_nr") else "caractere"
            if "maxim" in lim and n > lim["maxim"]:
                fragment = val[: lim["maxim"] + 1][-40:] if isinstance(val, str) else f"{n} elemente"
                probleme.append(
                    Problema(
                        "G1.peste_limita_canal",
                        fragment,
                        f"„{nume}” are {n} {unitate}, iar limita pe {canal} este {lim['maxim']}; "
                        "scurtează-l.",
                        detalii=f"{nume}: {n} > {lim['maxim']}",
                    )
                )
            elif "recomandat" in lim and n > lim["recomandat"]:
                probleme.append(
                    Problema(
                        "G1.peste_recomandarea_canalului",
                        "",
                        f"„{nume}” are {n} {unitate}; pe {canal} se recomandă cel mult {lim['recomandat']}.",
                        blocant=False,
                        severitate=Severitate.MINORA,
                        detalii=f"{nume}: {n} > {lim['recomandat']}",
                    )
                )
    return probleme


def _probleme_limba(continut: Continut) -> list[Problema]:
    probleme = []
    corp = continut.text
    if len(corp.strip()) < incarca("structura")["generale"]["text_minim"] and not _goala(corp):
        probleme.append(
            Problema(
                "G1.text_prea_scurt", corp.strip(), "Textul este prea scurt pentru un livrabil; dezvoltă-l."
            )
        )
    limba = text_ro.detecteaza_limba(corp)
    if limba.cod in ("en", "necunoscuta"):
        ce = "în engleză" if limba.cod == "en" else "într-o limbă care nu pare română"
        probleme.append(
            Problema(
                "G1.limba",
                corp.strip()[:80],
                f"Textul pare scris {ce}; rescrie-l direct în limba română.",
                detalii=f"cod={limba.cod}; cuvinte funcționale românești {limba.raport_ro:.2f}",
            )
        )
    return probleme


def _probleme_linkuri(continut: Continut) -> list[Problema]:
    probleme = []
    candidati: list[tuple[str, str]] = []
    for nume, text in continut.texte():
        candidati += [(nume, x) for x in text_ro.linkuri_in_text(text)]
        for stricat in text_ro.linkuri_stricate_in_text(text):
            probleme.append(
                Problema(
                    "G1.link_prost_format",
                    stricat,
                    f"Linkul „{stricat}” nu este bine format; scrie-l complet, cu https://.",
                    detalii="schemă greșită",
                )
            )
    for cheie in ("link", "linkuri", "link_dezabonare"):
        val = continut.campuri.get(cheie)
        for x in val if isinstance(val, list) else ([val] if isinstance(val, str) and val.strip() else []):
            if isinstance(x, str) and not text_ro.linkuri_in_text(x):
                candidati.append((cheie, x.strip()))
    vazute: set[str] = set()
    for _, link in candidati:
        if link in vazute:
            continue
        vazute.add(link)
        motiv = text_ro.motiv_link_invalid(link)
        if motiv:
            probleme.append(
                Problema(
                    "G1.link_prost_format",
                    link,
                    f"Linkul „{link}” nu este bine format ({motiv}); corectează-l.",
                    detalii=motiv,
                )
            )
    return probleme


def probleme_structura(tip: str, canal: str, continut: Continut) -> list[Problema]:
    """Toate problemele de structură ale unui conținut (nucleu pur)."""
    return [
        *_probleme_campuri(tip, continut),
        *_probleme_lungimi(canal, continut),
        *_probleme_limba(continut),
        *_probleme_linkuri(continut),
    ]


@registru.validator(
    registru.DefinitieValidator(
        COD,
        "Structură",
        VERSIUNE,
        Treapta.V0,
        10,
        descriere="Câmpuri obligatorii pe tip, lungimi pe canal, limba română, linkuri bine formate",
    )
)
def g1(intrare: Intrare) -> Verdict:
    probleme = probleme_structura(intrare.livrabil.tip, intrare.livrabil.canal, intrare.continut)
    tip_cunoscut = intrare.livrabil.tip in incarca("structura")["tipuri"]
    return verdict_din_probleme(
        COD,
        VERSIUNE,
        Treapta.V0,
        probleme,
        detalii={"tip_cunoscut": tip_cunoscut, "limite_marcate": "[I]"},
    )
