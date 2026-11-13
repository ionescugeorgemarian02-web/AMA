"""G3 Politici (docs/09 §9.4, §9.7): aplică pachetele de reguli potrivite livrabilului — generale, ale
platformei canalului, ale
nișelor (cele refuzate mereu, celelalte când clientul le declară) — plus regulile proprii ale clientului din
bază.

V1 (determinist): fiecare regulă încălcată dă o `Problema` cu regula, fragmentul exact și instrucțiunea.
Severitatea regulii hotărăște:
`minora` = avertisment, `majora` = blochează și se repară, `critica` = carantină (nișe refuzate). Verdictul
păstrează în `detalii`
exact ce a judecat: pachetele cu versiunea și amprenta fișierului, regulile clientului cu versiunea lor,
câte reguli sunt [I]
(sursa neverificată de un om). Nișa: `campuri["nise"]` al livrabilului și `nise` din profilul de brand
aprobat al clientului.

V3 (opțional, prin gateway): promisiuni nepermise formulate liber, pe care tiparele nu le prind (medicale,
de câștig, atribute
personale, minori); rubrică da / nu cu dovadă literală, model diferit de autor.
"""

from typing import Any

from app import creier
from app.creier.compartimente import Compartiment
from app.validare import judecator, registru, reguli, reguli_client
from app.validare.intrare import Intrare
from app.validare.probleme import Problema, verdict_din_probleme
from app.validare.reguli import Context, Regula
from app.validare.verdict import Severitate, Treapta, Verdict

COD = "G3"
VERSIUNE = "1"
VERSIUNE_V3 = "1"
SEVERITATI = {"minora": Severitate.MINORA, "majora": Severitate.MAJORA, "critica": Severitate.CRITICA}


def nise_ale_livrabilului(intrare: Intrare) -> list[str]:
    """Nișele declarate: de livrabil și de profilul de brand aprobat (cheia `nise`, listă de coduri)."""

    def din_profil() -> list[str]:
        gasite: list[str] = []
        for e in creier.citire.pentru_context(
            intrare.baza(), intrare.tenant_id, Compartiment.PROFIL_BRAND, intrare.la
        ):
            val = e.continut.get("nise")
            if isinstance(val, list):
                gasite += [str(x) for x in val]
        return gasite

    declarate = intrare.continut.campuri.get("nise") or []
    din_livrabil = [str(x) for x in declarate] if isinstance(declarate, list) else []
    return sorted({*din_livrabil, *intrare.memo("g3.nise_profil", din_profil)})


def problema_din(regula: Regula, fragment: str, pachet: str) -> Problema:
    sev = SEVERITATI[regula.severitate]
    if fragment:
        instr = regula.instructiune or f"{regula.text} Reformulează sau scoate „{fragment}”."
    else:
        instr = regula.instructiune or regula.text
    return Problema(
        f"G3.{pachet}.{regula.id}",
        fragment,
        instr,
        blocant=sev is not Severitate.MINORA,
        severitate=sev,
        detalii=f"{regula.sursa.titlu} ({regula.marcaj})",
    )


def probleme_politici(
    text: str, ctx: Context, pachete: list[reguli.PachetIncarcat], ale_clientului: list[tuple[Regula, int]]
) -> list[Problema]:
    """Nucleu pur: problemele găsite de pachetele și regulile date (aceeași încălcare nu se raportează
    de două ori)."""
    probleme: list[Problema] = []
    vazute: set[tuple[str, str]] = set()
    seturi: list[tuple[str, list[Regula]]] = [(p.nume, p.pachet.reguli) for p in pachete]
    seturi.append(("client", [r for r, _ in ale_clientului]))
    for nume, lista in seturi:
        for r in lista:
            for pot in reguli.potriviri(r, text, ctx):
                cheie = (r.id, pot.fragment.lower())
                if cheie not in vazute:
                    vazute.add(cheie)
                    probleme.append(problema_din(r, pot.fragment, nume))
    return probleme


@registru.validator(
    registru.DefinitieValidator(
        COD,
        "Politici",
        VERSIUNE,
        Treapta.V1,
        40,
        descriere="Pachetele de reguli (generale, platformă, nișă) și regulile clientului",
    )
)
def g3_reguli(intrare: Intrare) -> Verdict:
    nise = nise_ale_livrabilului(intrare)
    pachete = reguli.selecteaza(intrare.livrabil.canal, nise)
    ale_clientului = reguli_client.active(intrare.baza(), intrare.tenant_id)
    ctx = Context(canal=intrare.livrabil.canal, tip=intrare.livrabil.tip, campuri=intrare.continut.campuri)
    probleme = probleme_politici(intrare.text, ctx, pachete, ale_clientului)
    toate = [r for p in pachete for r in p.pachet.reguli] + [r for r, _ in ale_clientului]
    detalii: dict[str, Any] = {
        "pachete": [
            {"pachet": p.nume, "versiune": p.pachet.versiune, "amprenta": p.amprenta} for p in pachete
        ],
        "reguli_client": [{"regula": r.id, "versiune": v} for r, v in ale_clientului],
        "nise": nise,
        "reguli_neverificate": sum(1 for r in toate if r.marcaj == "[I]"),
    }
    return verdict_din_probleme(COD, VERSIUNE, Treapta.V1, probleme, detalii=detalii)


CRITERII_V3 = {
    "fara_promisiuni_medicale": "Textul NU promite vindecare, tratament sau rezultate medicale.",
    "fara_castig_garantat": "Textul NU promite câștiguri financiare garantate sau rapide.",
    "fara_atribute_personale": "Textul NU sugerează că știe boli, datorii sau alte atribute personale "
    "ale cititorului.",
    "fara_minori": "Textul NU promovează alcool, tutun sau alte produse restricționate către minori.",
}
INSTRUCTIUNI_V3 = {
    "fara_promisiuni_medicale": "Scoate promisiunea medicală din fragmentul indicat.",
    "fara_castig_garantat": "Scoate promisiunea de câștig garantat din fragmentul indicat.",
    "fara_atribute_personale": "Scoate referirea la atribute personale ale cititorului din fragmentul "
    "indicat.",
    "fara_minori": "Scoate adresarea către minori pentru produse restricționate din fragmentul indicat.",
}


@registru.validator(
    registru.DefinitieValidator(
        COD,
        "Politici (judecător)",
        VERSIUNE_V3,
        Treapta.V3,
        40,
        foloseste_model=True,
        descriere="Promisiuni nepermise formulate liber, prin rubrică da / nu cu dovadă",
    )
)
def g3_judecator(intrare: Intrare) -> Verdict:
    return judecator.judeca(
        intrare,
        validator=COD,
        versiune=VERSIUNE_V3,
        treapta=Treapta.V3,
        prompt="validare.g3_politici",
        criterii=CRITERII_V3,
        instructiuni=INSTRUCTIUNI_V3,
    )
