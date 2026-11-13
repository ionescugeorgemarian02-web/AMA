"""G7 Originalitate și drepturi (docs/09 §9.4, docs/21 §21.11): textul nu copiază sursele colectate și
activele au licență.

- V1 (determinist): suprapunerea de shingle-uri (5 cuvinte consecutive, fără diacritice și majuscule) dintre
text și documentele
  colectate ale clientului, inclusiv ale concurenței. Sursele al căror text NU se reutilizează (concurența,
  forumuri) blochează la
  prag mic sau la un fragment copiat lung; materialele clientului doar avertizează la copiere aproape
  integrală. Dovada este fragmentul
  suprapus, exact din text. Activele media declarate (`active`) cer o licență înregistrată; media propriu-
  zisă vine în F8.
- V2 (local): similaritate vectorială (căutarea existentă a Creierului + `gateway.vectorizeaza`) față de
pasajele surselor nereutilizabile:
  o parafrază apropiată este avertisment. Un gateway indisponibil dă „necalculat”, nu blocare.
"""

import re
import zlib
from dataclasses import dataclass

from sqlalchemy import select

from app import cercetare, creier
from app.validare import afirmatii, registru
from app.validare.date_validare import incarca
from app.validare.intrare import Intrare
from app.validare.probleme import Problema, verdict_din_probleme
from app.validare.verdict import Severitate, Treapta, Verdict

COD = "G7"
VERSIUNE = "1"
VERSIUNE_V2 = "1"
CUVANT = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class Suprapunere:
    containment: float  # partea din shingle-urile textului care apare în sursă
    rand_maxim: int  # cel mai lung fragment copiat, în cuvinte
    fragment: str  # fragmentul, exact din text


def cuvinte_cu_pozitii(text: str) -> list[tuple[str, int, int]]:
    b = afirmatii.baza(text)
    return [(m.group(0), m.start(), m.end()) for m in CUVANT.finditer(b)]


def shingles(cuvinte: list[str], n: int) -> list[int]:
    return [zlib.crc32(" ".join(cuvinte[i : i + n]).encode()) for i in range(max(0, len(cuvinte) - n + 1))]


def suprapunere(text: str, surse: list[set[int]], n: int) -> Suprapunere:
    """Suprapunerea textului cu un set de shingle-uri sursă (nucleu pur)."""
    cp = cuvinte_cu_pozitii(text)
    sh = shingles([c for c, _, _ in cp], n)
    if not sh:
        return Suprapunere(0.0, 0, "")
    uniune: set[int] = set().union(*surse) if surse else set()
    potrivit = [s in uniune for s in sh]
    cel_mai_lung, start, i = 0, 0, 0
    while i < len(potrivit):
        if potrivit[i]:
            j = i
            while j + 1 < len(potrivit) and potrivit[j + 1]:
                j += 1
            lungime = (j - i) + n  # shingle-uri consecutive → cuvinte copiate
            if lungime > cel_mai_lung:
                cel_mai_lung, start = lungime, i
            i = j + 1
        else:
            i += 1
    fragment = ""
    if cel_mai_lung:
        a, z = cp[start][1], cp[start + cel_mai_lung - 1][2]
        fragment = text[a:z]
    return Suprapunere(sum(potrivit) / len(sh), cel_mai_lung, fragment)


def probleme_suprapunere(s: Suprapunere, *, sursa: str, nereutilizabila: bool) -> list[Problema]:
    prag = incarca("originalitate")["prag"]["nereutilizabila" if nereutilizabila else "reutilizabila"]
    if s.containment < float(prag["containment"]) and s.rand_maxim < int(prag["rand_minim_cuvinte"]):
        return []
    if nereutilizabila:
        return [
            Problema(
                "G7.copiat_din_sursa",
                s.fragment[:300],
                f"Fragmentul „{s.fragment[:80]}…” apare aproape identic în „{sursa}” (text care nu se "
                f"reutilizează, "
                f"{s.containment:.0%} din text suprapus); rescrie-l cu cuvintele tale.",
                detalii=f"{sursa}: {s.containment:.0%}, rând de {s.rand_maxim} cuvinte",
            )
        ]
    return [
        Problema(
            "G7.copie_a_materialelor_clientului",
            s.fragment[:300],
            f"Textul repetă aproape integral materialele clientului („{sursa}”, {s.containment:.0%}); "
            f"aduce ceva nou.",
            blocant=False,
            severitate=Severitate.MAJORA,
            detalii=f"{sursa}: {s.containment:.0%}",
        )
    ]


def probleme_active(active: tuple[dict[str, object], ...]) -> list[Problema]:
    probleme = []
    for a in active:
        if not str(a.get("licenta") or "").strip():
            nume = str(a.get("nume") or a.get("sursa") or "activ")
            probleme.append(
                Problema(
                    "G7.activ_fara_licenta",
                    nume[:120],
                    f"Activul „{nume}” nu are o licență înregistrată; înregistrează licența sau scoate "
                    f"activul.",
                    detalii="licența lipsește",
                )
            )
    return probleme


def _surse_text(intrare: Intrare) -> list[tuple[str, bool, set[int]]]:
    """(nume sursă, nereutilizabilă?, shingle-uri) ale documentelor colectate ale clientului."""

    def citeste() -> list[tuple[str, bool, set[int]]]:
        cfg = incarca("originalitate")["shingles"]
        n = int(cfg["n"])
        q = (
            select(
                cercetare.Document.text,
                cercetare.Document.titlu,
                cercetare.SursaColectare.nume,
                cercetare.SursaColectare.statut,
            )
            .join(cercetare.SursaColectare, cercetare.SursaColectare.id == cercetare.Document.sursa_id)
            .where(cercetare.Document.tenant_id == intrare.tenant_id)
            .order_by(cercetare.Document.id)
            .limit(int(cfg["documente_maxim"]))
        )
        iesire = []
        for text, titlu, sursa, statut in intrare.baza().execute(q).all():
            st = cercetare.STATUTE.get(statut)
            nereutilizabila = st is not None and not st.reutilizare_text
            cuv = [c for c, _, _ in cuvinte_cu_pozitii(text)]
            iesire.append((f"{sursa}: {titlu}".strip(": "), nereutilizabila, set(shingles(cuv, n))))
        return iesire

    return intrare.memo("g7.surse", citeste)


@registru.validator(
    registru.DefinitieValidator(
        COD,
        "Originalitate",
        VERSIUNE,
        Treapta.V1,
        70,
        descriere="Suprapunere cu sursele colectate; active fără licență",
    )
)
def g7_reguli(intrare: Intrare) -> Verdict:
    cfg = incarca("originalitate")["shingles"]
    probleme = probleme_active(intrare.continut.active)
    detalii: dict[str, object] = {"documente_comparate": 0}
    if len(cuvinte_cu_pozitii(intrare.text)) >= int(cfg["text_minim_cuvinte"]):
        surse = _surse_text(intrare)
        detalii["documente_comparate"] = len(surse)
        n = int(cfg["n"])
        for nume, nereutilizabila, sh in surse:
            s = suprapunere(intrare.text, [sh], n)
            probleme += probleme_suprapunere(s, sursa=nume, nereutilizabila=nereutilizabila)
    return verdict_din_probleme(COD, VERSIUNE, Treapta.V1, probleme, detalii=detalii)


@registru.validator(
    registru.DefinitieValidator(
        COD,
        "Originalitate (vectori)",
        VERSIUNE_V2,
        Treapta.V2,
        70,
        foloseste_vectori=True,
        descriere="Parafraze apropiate de sursele nereutilizabile",
    )
)
def g7_vectori(intrare: Intrare) -> Verdict | None:
    from app import gateway
    from app.operare.motor import Prioritate
    from app.validare.ton import cosinus

    cfg = incarca("originalitate")["vectori"]
    if len(cuvinte_cu_pozitii(intrare.text)) < int(
        incarca("originalitate")["shingles"]["text_minim_cuvinte"]
    ):
        return None
    try:
        gasite = creier.cauta(
            intrare.baza(),
            tenant_id=intrare.tenant_id,
            intrebare=intrare.text[:600],
            limita=int(cfg["pasaje_maxim"]),
            doar_text=False,
        ).rezultate
        nereutilizabile = [
            r
            for r in gasite
            if (st := cercetare.STATUTE.get(_statut(intrare, r.sursa_id))) is not None
            and not st.reutilizare_text
        ]
        if not nereutilizabile:
            return verdict_din_probleme(COD, VERSIUNE_V2, Treapta.V2, [], detalii={"pasaje_comparate": 0})
        vectori = gateway.vectorizeaza(
            [intrare.text[:4000], *[r.text for r in nereutilizabile]],
            tenant_id=intrare.tenant_id, componenta="validare.g7", prioritate=Prioritate.P1,
        )  # fmt: skip
    except (gateway.Amanat, gateway.EroareGateway, creier.CautareRefuzata) as exc:
        necalculat = Problema(
            "G7.vectori_necalculati",
            "",
            "Similaritatea vectorială cu sursele nu s-a putut calcula; originalitatea cere verificare umană.",
            blocant=False,
            severitate=Severitate.MINORA,
            detalii=type(exc).__name__,
        )
        return verdict_din_probleme(COD, VERSIUNE_V2, Treapta.V2, [necalculat])
    scoruri = [cosinus(vectori[0], v) for v in vectori[1:]]
    i = max(range(len(scoruri)), key=lambda k: scoruri[k])
    detalii = {"pasaje_comparate": len(scoruri), "scor_maxim": round(scoruri[i], 3), "prag": cfg["prag"]}
    if scoruri[i] < float(cfg["prag"]):
        return verdict_din_probleme(COD, VERSIUNE_V2, Treapta.V2, [], detalii=detalii)
    parafraza = Problema(
        "G7.parafraza_apropiata",
        nereutilizabile[i].text[:200],
        "Textul pare o parafrază apropiată a unei surse nereutilizabile; rescrie-l cu cuvinte proprii.",
        blocant=False,
        severitate=Severitate.MAJORA,
        detalii=f"cosinus {scoruri[i]:.2f} ≥ {cfg['prag']}",
    )
    return verdict_din_probleme(COD, VERSIUNE_V2, Treapta.V2, [parafraza], detalii=detalii)


def _statut(intrare: Intrare, sursa_id: object) -> str:
    q = select(cercetare.SursaColectare.statut).where(cercetare.SursaColectare.id == sursa_id)
    return str(intrare.baza().execute(q).scalar_one_or_none() or "")
