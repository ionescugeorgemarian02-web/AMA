"""Etapa de idee a unui livrabil (F-idee, D-032), înaintea briefului: momentul real → critica → validarea →
alegerea.

1. **Propunerea** (`propune`, promptul `continut.idei@1`, profilul `creatie`): din slotul de calendar,
   publicul, oferta și faptele pachetului de context, autorul propune 5 concepte. Fiecare pornește de la un
   moment real din viața publicului (loc, timp, acțiune), are o singură idee (`mesaj_unic`), o dovadă
   (aliasul unui fapt aprobat) și 4–7 cadre observabile (subiect concret + acțiune vizibilă + context, cu
   interogări de stock în engleză), plus cadrele care cer material propriu al clientului.
2. **Critica** (`critica`, `continut.critica_idee@1`): note 1–5 pe șase criterii fixe, obiecții concrete și o
   variantă îmbunătățită a celui mai bun concept. Criticul e alt model decât autorul când lanțul profilului
   are unul; altfel același model, iar rezultatul se marchează `autoevaluare`.
3. **Validarea deterministă** (`probleme_concept`): substantiv concret și verb de acțiune pe fiecare cadru,
   mișcare pe ≥ 60% din cadre la video, cel mult un cadru doar cu text, fără majoritate de cadre doar cu
   obiecte, dovada trimite la un fapt aprobat, materialul propriu nu se acoperă cu stock, cadrele de stock
   nu cer continuitate de personaj sau loc („același biciclist”, „a doua zi”) și nici reacții jucate
   („pietonii întorc capul”): acelea sunt material propriu sau filmare regizată.
4. **Alegerea** (`alege`, pur): scorul criticii, cu realismul, onestitatea și fezabilitatea eliminatorii
   sub 3, plus validarea (în care intră și cadrele de stock obiectate de critic). Varianta îmbunătățită de
   critic e candidat cu notele conceptului din care vine și câștigă la scor egal. Fără un concept bun, cel
   mai bun se rescrie o singură dată cu obiecțiile (și se critică din nou); dacă pică iar, ideea merge la
   om (`alege_manual`).

`pregateste` rulează tot lanțul într-o tranzacție și persistă conceptele, notele și alegerea
(`idei_concepte`), cu urmă și audit. Conceptul ales intră în brief (`brief.idee_aleasa`), iar postarea și
scriptul se scriu din el.
"""

import json
import re
import unicodedata
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import creier, gateway, productie
from app.continut import brief, calendar, prompturi
from app.continut.modele import IdeeConcept
from app.creier import context
from app.ids import new_id
from app.operare import audit, urme
from app.operare.motor import Prioritate
from app.productie import Stare

PROMPT_IDEI = "continut.idei@1"
PROMPT_CRITICA = "continut.critica_idee@1"
PROFIL = "creatie"
NUMAR_CONCEPTE = 5
CRITERII = ("specificitate", "realism", "relevanta", "fezabilitate", "noutate", "onestitate")
ELIMINATORII = ("realism", "onestitate", "fezabilitate")
NOTA_MINIMA_ELIMINATORIE = 3
PRAG_MISCARE_VIDEO = 0.6
ANTERIOARE = 8  # câte concepte alese anterior primește autorul (noutatea)


# --- modelele ---


class Cadru(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subiect: str = Field(min_length=2, max_length=120)
    actiune: str = Field(min_length=2, max_length=200)
    context: str = Field(default="", max_length=200)
    tip: Literal["video", "foto", "text"]
    incadrare: str = Field(default="", max_length=60)
    interogari: list[str] = Field(default_factory=list, max_length=3)


class Concept(BaseModel):
    model_config = ConfigDict(extra="forbid")
    titlu: str = Field(min_length=3, max_length=100)
    moment_real: str = Field(min_length=20, max_length=400)
    tensiune: str = Field(min_length=10, max_length=300)
    mesaj_unic: str = Field(min_length=10, max_length=200)
    dovada: str = Field(default="", max_length=20, description="Aliasul faptului aprobat (F1, F2, …)")
    de_ce_acum: str = Field(min_length=5, max_length=300)
    cadre: list[Cadru] = Field(min_length=4, max_length=7)
    material_propriu: list[int] = Field(default_factory=list, description="Numerele cadrelor (de la 1)")


class PropunereIdei(gateway.Iesire):
    concepte: list[Concept] = Field(min_length=1, max_length=NUMAR_CONCEPTE)


class EvaluareConcept(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nr: int = Field(ge=1)
    specificitate: int = Field(ge=1, le=5)
    realism: int = Field(ge=1, le=5)
    relevanta: int = Field(ge=1, le=5)
    fezabilitate: int = Field(ge=1, le=5)
    noutate: int = Field(ge=1, le=5)
    onestitate: int = Field(ge=1, le=5)
    obiectii: list[str] = Field(default_factory=list, max_length=8)

    def note(self) -> dict[str, int]:
        return {c: int(getattr(self, c)) for c in CRITERII}


class CriticaIdei(gateway.Iesire):
    evaluari: list[EvaluareConcept] = Field(min_length=1, max_length=NUMAR_CONCEPTE + 1)
    nr_imbunatatit: int | None = None
    imbunatatit: Concept | None = None


class IdeeLaOm(creier.RegulaCreier):
    """Niciun concept nu a trecut critica și validarea, nici după rescriere: alege omul (`alege_manual`)."""


# --- validarea deterministă ---


def _norm(text: str) -> list[str]:
    fara = "".join(c for c in unicodedata.normalize("NFKD", text.lower()) if not unicodedata.combining(c))
    return [w for w in re.split(r"[^a-z0-9]+", fara) if len(w) >= 2]


def _set(text: str) -> frozenset[str]:
    return frozenset(_norm(text))


# [I] verbe de acțiune observabilă: indicativ prezent (pers. a III-a, sg. și pl.) și gerunziu, fără diacritice
VERBE_ACTIUNE = _set("""
roteste rotesc rotind rostogoleste rostogolesc invarte invart invartind pedaleaza pedaland franeaza
franand coboara cobor coborand
urca urcand curata curatand unge ung ungand strange strang strangand sare sar sarind scartaie scartaind
aluneca alunecand derapeaza cade cad cazand curge curg curgand picura picurand stropeste stropesc
spala spala spalat spaland freaca frecand sterge sterg stergand lustruieste repara reparand monteaza
montand demonteaza desurubeaza insurubeaza surubeste ajusteaza ajustand regleaza reglind regland
verifica verificand testeaza testand umfla umflan umfland pompeaza pompand schimba schimband inlocuieste
scoate scot scotand desface desfac pune pun punand aseaza asaza aseaza ridica ridicand apasa apasand
trece trec trecand trage trag tragand impinge impingand
deschide deschid deschizand inchide inchid inchizand taie taind
masoara masurand cantareste macina macinand amesteca amestecand framanta coace coc prajeste prajind
fierbe fierband toarna torn turnand varsa varsand aprinde aprind stinge ruleaza ruland alearga alergand
merge merg mergand calca calcand intra intrand iese ies iesind intoarce intorc intorcand vireaza
priveste privesc privind zambeste zambind rade razand vorbeste vorbind explica explicand scrie scriu
scriind noteaza semneaza plateste numara impacheteaza ambaleaza livreaza preda primeste primesc ia iau
muta mutand duce duc ducand bea beau gusta gustand miroase mirosind musca mananca servesc serveste
spumeaza pulverizeaza vopseste slefuieste gaureste bate bat batand loveste vibreaza tremura misca
miscand clipeste aprinde clatina clatinand leagana tinand prinde prind sprijina
saluta imbratiseaza dau intinde intind impinge apuca agata agatand insurubeaza tasteaza
deseneaza taie croieste coase imbraca dezbraca piaptana tunde spala aspira matura curata
""")
# [I] verbe care descriu o stare, nu o acțiune: un cadru doar cu ele e static
VERBE_STATICE = _set("sta stau este sunt afla zace asteapta apare arata pare exista ramane expus asezat")
# [I] substantive concrete (oameni, obiecte, locuri), forme de bază; potrivire pe prefix (articol, plural)
SUBSTANTIVE_CONCRETE = _set("""
mana maini degete deget picior picioare fata ochi om oameni femeie barbat copil copii client clienta
mecanic biciclist biciclista barista bucatar ospatar vanzator vanzatoare medic pacient elev profesor
mama tata familie prieten cuplu sofer tehnician echipa proprietar persoana coleg
lant pinion bicicleta roata roti spita ghidon pedala frana schimbator anvelopa cauciuc sa sea casca
furca rulment cablu pompa cheie surubelnita ulei vaselina carpa perie burete galeata atelier
cafea ceasca cana boabe pachet rasnita espressor filtru lapte zahar tava tejghea masa scaun usa geam
fereastra raft cutie punga sticla farfurie paine aluat cuptor tigaie oala lingura cutit foarfeca
apa ploaie zapada noroi praf strada drum trotuar parc deal munte padure pod parcare statie oras sat
casa bucatarie birou magazin vitrina curte gradina masina autobuz tren telefon laptop calculator
hartie carte caiet pix factura card bon etichetta eticheta haina geaca manusa pantof bocanc rucsac
""")
# [I] umplutură, adjective de efect și abstracțiuni: nu fac un cadru concret
_ABSTRACTE = """
calitate incredere siguranta succes solutie solutii experienta pasiune grija libertate performanta
inovatie valoare beneficiu beneficii avantaj avantaje rezultat rezultate satisfactie fericire bucurie
confort excelenta traditie profesionalism afacere brand servicii serviciu produs produse oferta
concept idee mesaj emotie atmosfera energie stil vibe esenta viziune misiune povestea poveste
"""
ABSTRACTE = _set(_ABSTRACTE) | brief.VAGI | brief.UMPLUTURA | _set("si sau cu de la in pe din un o al ai ale")
# [I] cine face acțiunea: un cadru fără om e „doar obiect” dacă nici obiectul nu se mișcă
AGENTI = _set("""
mana maini degete deget picior picioare om oameni femeie barbat copil copii client clienta mecanic
biciclist biciclista barista bucatar ospatar vanzator vanzatoare medic pacient elev profesor mama tata
familie prieten prietenii cuplu sofer tehnician echipa proprietar persoana coleg colega
""")


def _contine(cuvinte: list[str], lista: frozenset[str]) -> bool:
    """Un cuvânt din listă, exact sau cu o terminație de cel mult 4 litere (articol, plural: „mecanicul”)."""
    for w in cuvinte:
        if w in lista:
            return True
        if any(len(x) >= 4 and w.startswith(x) and len(w) - len(x) <= 4 for x in lista):
            return True
    return False


def _verb(actiune: str) -> bool:
    cuvinte = _norm(actiune)
    if re.search(r"\b(ii|le) arata\b", " ".join(cuvinte)):  # „îi arată clientului”: un gest spre cineva
        return True
    return any(w in VERBE_ACTIUNE for w in cuvinte) or _contine(
        [w for w in cuvinte if len(w) >= 6], frozenset(v for v in VERBE_ACTIUNE if len(v) >= 6)
    )


def _concret(subiect: str) -> bool:
    cuvinte = _norm(subiect)
    if _contine(cuvinte, SUBSTANTIVE_CONCRETE):
        return True
    # alt domeniu decât listele: concret = un cuvânt de conținut care nu e abstracțiune sau adjectiv de efect
    return any(len(w) >= 3 and not w.isdigit() and not _contine([w], ABSTRACTE) for w in cuvinte)


def doar_obiect(c: Cadru) -> bool:
    """Un cadru fără om (mână, client, mecanic…) în subiect, acțiune sau context."""
    return not _contine(_norm(f"{c.subiect} {c.actiune} {c.context}"), AGENTI)


# [I] ce stock-ul nu poate livra: continuitatea unui personaj sau a unui loc între cadre și reacțiile jucate
# ale trecătorilor. Un clip de stock e alt om, altă stradă, altă zi; o reacție la comandă cere figuranți.
CONTINUITATE = re.compile(
    r"\b(acelasi|aceeasi|aceiasi|aceleasi|a doua zi|ziua urmatoare|dupa revizie|dupa reparatie)\b"
)
REACTIE_JUCATA = re.compile(
    r"\b(intorc\w* capul|isi intorc\w*|se intorc\w* spre|se uita\w* (spre|la|dupa)|privesc\w* (spre|dupa)"
    r"|reactioneaza|aplauda|ridica din sprancene)\b"
)
# [I] semnele unei obiecții de fezabilitate sau onestitate pe un cadru (textul criticului, fără diacritice)
OBIECTIE_CADRU = re.compile(
    r"nu se gase|nu exista|greu de gasit|nu se poate|nu se filmeaza|imposibil|trucaj|figurant|nerealist"
    r"|prezentat drept|prezentat ca|luat drept|nu poate garanta|continuitate|filmeaza la"
)
_NUMAR_CADRE = re.compile(r"\bcadr(?:ul|ele)\s+(\d+(?:\s*(?:,|si)\s*\d+)*)")


def _text_norm(text: str) -> str:
    """Litere mici, fără diacritice, cuvintele (și cifrele, „cadrul 5”) despărțite de un spațiu."""
    fara = "".join(c for c in unicodedata.normalize("NFKD", text.lower()) if not unicodedata.combining(c))
    return " ".join(w for w in re.split(r"[^a-z0-9]+", fara) if w)


def cadre_obiectate(obiectii: list[str]) -> dict[int, str]:
    """Cadrele (numărul, de la 1) pe care criticul le obiectă pentru fezabilitate sau onestitate: obiecția
    numește cadrul („Cadrul 4 …”, „Cadrele 1 și 5 …”) și spune că nu se găsește, nu se poate filma, e
    prezentat drept altceva sau pretinde continuitate. Prima obiecție pe cadru."""
    out: dict[int, str] = {}
    for ob in obiectii:
        t = _text_norm(ob)
        if not OBIECTIE_CADRU.search(t):
            continue
        for m in _NUMAR_CADRE.finditer(t):
            for nr in re.findall(r"\d+", m.group(1)):
                out.setdefault(int(nr), ob)
    return out


def _alias(dovada: str) -> str:
    m = re.match(r"\s*\[?(F\d+)\]?", dovada)
    return m.group(1) if m else ""


def probleme_concept(
    concept: Concept,
    fapte: dict[str, dict[str, Any]],
    *,
    video: bool = False,
    obiectii: list[str] | None = None,
) -> list[str]:
    """Nucleu pur: ce face conceptul nefilmabil, static, vag sau necinstit. Listă goală = trece.
    `obiectii`: obiecțiile criticului pe acest concept; un cadru de stock obiectat pentru fezabilitate sau
    onestitate (`cadre_obiectate`) e o problemă: se scoate, se filmează la client sau conceptul se rescrie."""
    out: list[str] = []
    imagini = [(i, c) for i, c in enumerate(concept.cadre, start=1) if c.tip != "text"]
    for i, c in imagini:
        if not _concret(c.subiect):
            out.append(f"cadrul {i} e vag: „{c.subiect}” nu numește un om, un obiect sau un loc care se vede")
        if not _verb(c.actiune):
            static = any(w in VERBE_STATICE for w in _norm(c.actiune))
            out.append(
                f"cadrul {i} e static: „{c.actiune}” "
                + ("descrie o stare" if static else "nu are un verb de acțiune")
                + "; arată ce se întâmplă (se rotește, curăță, strânge, coboară)"
            )
    if video and imagini:
        cu_miscare = sum(1 for _, c in imagini if c.tip == "video" and _verb(c.actiune))
        if cu_miscare / len(imagini) < PRAG_MISCARE_VIDEO:
            out.append(
                f"la video, doar {cu_miscare} din {len(imagini)} cadre au mișcare; cel puțin "
                f"{PRAG_MISCARE_VIDEO:.0%} trebuie să fie filmări cu acțiune"
            )
    texte = len(concept.cadre) - len(imagini)
    if texte > 1:
        out.append(
            f"{texte} cadre doar cu text: cel mult unul (apelul la acțiune); restul se arată în imagine"
        )
    obiecte = sum(1 for _, c in imagini if doar_obiect(c))
    if imagini and obiecte * 2 > len(imagini):
        out.append(
            f"{obiecte} din {len(imagini)} cadre arată doar obiecte; momentul real are oameni care fac ceva"
        )
    alias = _alias(concept.dovada)
    if fapte and alias not in fapte:
        out.append(f"dovada „{concept.dovada}” nu trimite la un fapt aprobat din pachet")
    elif not fapte and concept.dovada.strip():
        out.append("dovada citează un fapt, dar pachetul nu are fapte aprobate")
    for nr in concept.material_propriu:
        if not 1 <= nr <= len(concept.cadre):
            out.append(f"materialul propriu cere cadrul {nr}, care nu există")
        elif concept.cadre[nr - 1].interogari:
            out.append(
                f"cadrul {nr} trebuie să arate clientul real (material propriu): nu se acoperă cu stock"
            )
    for i, c in imagini:
        if i in concept.material_propriu:
            continue
        if not c.interogari:
            out.append(f"cadrul {i} nu are interogări de stock (sau trebuie marcat ca material propriu)")
        elif any(re.search(r"[ăâîșțşţ]", q, re.IGNORECASE) for q in c.interogari):
            out.append(f"cadrul {i}: interogările de stock se scriu în engleză")
    stock = [(i, c) for i, c in imagini if i not in concept.material_propriu and c.interogari]
    semnalate: set[int] = set()
    for i, c in stock:
        t = _text_norm(f"{c.subiect} {c.actiune} {c.context}")
        if CONTINUITATE.search(t) or REACTIE_JUCATA.search(t):
            semnalate.add(i)
        if CONTINUITATE.search(t):
            out.append(
                f"cadrul {i} cere continuitate („{c.subiect}”, {c.context or c.actiune}): stock-ul e alt om, "
                "alt loc, altă zi; e material propriu sau filmare regizată"
            )
        elif REACTIE_JUCATA.search(t):
            out.append(
                f"cadrul {i} cere o reacție jucată („{c.actiune}”): stock-ul nu o are; e filmare regizată"
            )
    obiectate = cadre_obiectate(obiectii or [])
    for i, _c in stock:
        if i in obiectate and i not in semnalate:
            out.append(f"cadrul {i} obiectat de critic: {obiectate[i]}")
    return out


# --- alegerea (pură) ---


@dataclass
class Evaluat:
    nr: int
    sursa: Literal["propus", "imbunatatit", "rescris"]
    concept: Concept
    note: dict[str, int] = field(default_factory=dict)
    obiectii: list[str] = field(default_factory=list)
    probleme: list[str] = field(default_factory=list)

    @property
    def scor(self) -> int | None:
        return sum(self.note.values()) if self.note else None

    @property
    def eliminat(self) -> str:
        if not self.note:
            return "fără note de la critic"
        slabe = [c for c in ELIMINATORII if self.note.get(c, 0) < NOTA_MINIMA_ELIMINATORIE]
        return f"eliminat la {', '.join(slabe)} (sub {NOTA_MINIMA_ELIMINATORIE})" if slabe else ""

    @property
    def bun(self) -> bool:
        return not self.eliminat and not self.probleme


@dataclass
class Alegere:
    evaluate: list[Evaluat]
    ales: Evaluat | None
    motiv: str

    @property
    def de_rescris(self) -> Evaluat | None:
        """Cel mai bun concept nereușit (de rescris cu obiecțiile), dacă nu s-a ales nimic."""
        if self.ales is not None or not self.evaluate:
            return None
        return max(self.evaluate, key=lambda e: (e.scor or 0, e.sursa == "imbunatatit", -e.nr))


def alege(
    propunere: PropunereIdei,
    critica_: CriticaIdei,
    fapte: dict[str, dict[str, Any]],
    *,
    video: bool = False,
    sursa: Literal["propus", "rescris"] = "propus",
) -> Alegere:
    """Scorul criticii (suma notelor; realismul, onestitatea și fezabilitatea sub 3 elimină) plus validarea
    deterministă, care include obiecțiile criticului pe cadre de stock anume (`cadre_obiectate`).

    Varianta îmbunătățită de critic e candidat ca oricare altul, dacă trece `probleme_concept`. Scorul ei
    estimat sunt notele conceptului din care vine (criticul a scris-o rezolvând exact obiecțiile acelea, deci
    obiecțiile nu i se mai aplică); la scor egal întrece orice concept propus, iar un concept propus cu scor
    mai mare care pică validarea (de pildă pe cadrele obiectate) nu o mai blochează. Determinist."""
    note = {e.nr: e for e in critica_.evaluari}
    evaluate: list[Evaluat] = []
    for nr, c in enumerate(propunere.concepte, start=1):
        e = note.get(nr)
        evaluate.append(
            Evaluat(
                nr,
                sursa,
                c,
                e.note() if e else {},
                list(e.obiectii) if e else [],
                probleme_concept(c, fapte, video=video, obiectii=e.obiectii if e else []),
            )
        )
    if critica_.imbunatatit is not None and critica_.nr_imbunatatit in note:
        e = note[critica_.nr_imbunatatit]
        evaluate.append(
            Evaluat(
                e.nr,
                "imbunatatit",
                critica_.imbunatatit,
                e.note(),
                list(e.obiectii),
                probleme_concept(critica_.imbunatatit, fapte, video=video),
            )
        )
    buni = sorted(
        (e for e in evaluate if e.bun), key=lambda e: (-(e.scor or 0), e.sursa != "imbunatatit", e.nr)
    )
    if buni:
        a = buni[0]
        eticheta = (
            "varianta îmbunătățită de critic a conceptului" if a.sursa == "imbunatatit" else "conceptul"
        )
        return Alegere(evaluate, a, f"{eticheta} {a.nr}: scor {a.scor}/{5 * len(CRITERII)}, validare trecută")
    return Alegere(evaluate, None, "niciun concept nu a trecut critica și validarea")


# --- apelurile ---


def _text_fapte(fapte: dict[str, dict[str, Any]]) -> str:
    return "\n".join(f"[{a}] {f['tip']}: {f['text']}" for a, f in fapte.items()) or "(niciun fapt aprobat)"


def _text_concepte(concepte: list[Concept]) -> str:
    return "\n\n".join(
        f"Concept {i}:\n{json.dumps(c.model_dump(mode='json'), ensure_ascii=False)}"
        for i, c in enumerate(concepte, start=1)
    )


def _anterioare(db: Session, livrabil_id: uuid.UUID) -> str:
    rows = db.execute(
        select(IdeeConcept.concept)
        .where(IdeeConcept.ales.is_(True), IdeeConcept.livrabil_id != livrabil_id)
        .order_by(IdeeConcept.creat_la.desc())
        .limit(ANTERIOARE)
    ).scalars()
    return "\n".join(f"- {c.get('titlu', '')}: {c.get('moment_real', '')}" for c in rows) or "(niciunul)"


@dataclass
class _Intrare:
    lv: productie.Livrabil
    slot: Any
    fapte: dict[str, dict[str, Any]]
    context: str

    @property
    def video(self) -> bool:
        return "video" in self.lv.tip


def _intrare(db: Session, livrabil_id: uuid.UUID, utilizator_id: uuid.UUID | None = None) -> _Intrare:
    lv = productie.blocheaza(db, livrabil_id)
    slot = calendar.intrarea_livrabilului(db, lv.id)
    if slot is None:
        raise creier.RegulaCreier("livrabilul nu vine dintr-un calendar")
    pachet = brief.pachet_livrabil(db, lv, slot, utilizator_id=utilizator_id)
    return _Intrare(lv, slot, brief.fapte_disponibile(pachet), context.ca_text(pachet))


def propune(
    db: Session,
    livrabil_id: uuid.UUID,
    *,
    intrare: _Intrare | None = None,
    de_rescris: Evaluat | None = None,
) -> tuple[PropunereIdei, str]:
    """Conceptele autorului (5) sau, cu `de_rescris`, rescrierea unui concept cu obiecțiile lui (1).
    Întoarce propunerea și modelul care a scris-o. Ridică `gateway.Amanat` / `EroareGateway`."""
    x = intrare or _intrare(db, livrabil_id)
    obiectii = "-"
    if de_rescris is not None:
        motive = [
            *de_rescris.obiectii,
            *de_rescris.probleme,
            *([de_rescris.eliminat] if de_rescris.eliminat else []),
        ]
        obiectii = (
            "Rescrie O SINGURĂ dată conceptul de mai jos, rezolvând fiecare obiecție; "
            "întoarce un singur concept.\n"
            f"{json.dumps(de_rescris.concept.model_dump(mode='json'), ensure_ascii=False)}\nObiecții:\n"
            + "\n".join(f"- {m}" for m in motive)
        )
    prompturi.asigura()
    r = gateway.apeleaza(
        db,
        prompt=PROMPT_IDEI,
        schema=PropunereIdei,
        tenant_id=x.lv.tenant_id,
        componenta="continut.idei",
        livrabil_id=x.lv.id,
        prioritate=Prioritate.P2,
        profil=PROFIL,
        max_tokeni=3500,
        temperatura=0.8,
        variabile={
            "tip": x.lv.tip,
            "canal": x.lv.canal,
            "pilon": x.slot.pilon,
            "subiect": x.slot.subiect,
            "unghi": x.slot.unghi or "-",
            "numar": "1" if de_rescris is not None else str(NUMAR_CONCEPTE),
            "fapte": _text_fapte(x.fapte),
            "context": x.context,
            "anterioare": _anterioare(db, x.lv.id),
            "obiectii": obiectii,
        },
    )
    if not isinstance(r.iesire, PropunereIdei):
        raise TypeError("ieșirea nu respectă schema promptului")
    return r.iesire, r.model


def _alt_model_permis(db: Session, autor: str) -> bool:
    """Are lanțul profilului un alt model activ decât autorul?"""
    p = gateway.registru.profil(db, PROFIL)
    if p is None:
        return False
    activi = {c.cod for c in gateway.registru.candidati(db) if c.model_activ and c.stare_furnizor == "activ"}
    return any(cod != autor and cod in activi for cod in p.lant)


def critica(
    db: Session,
    livrabil_id: uuid.UUID,
    propunere: PropunereIdei,
    *,
    autor: str,
    intrare: _Intrare | None = None,
) -> tuple[CriticaIdei, str, bool]:
    """Notele, obiecțiile și varianta îmbunătățită. Întoarce critica, modelul criticului și `autoevaluare`
    (True când criticul a fost chiar autorul: lanțul nu are alt model sau celălalt nu a putut răspunde)."""
    x = intrare or _intrare(db, livrabil_id)
    prompturi.asigura()

    def cere(alt: str | None) -> gateway.Rezultat:
        return gateway.apeleaza(
            db,
            prompt=PROMPT_CRITICA,
            schema=CriticaIdei,
            tenant_id=x.lv.tenant_id,
            componenta="continut.critica_idee",
            livrabil_id=x.lv.id,
            prioritate=Prioritate.P2,
            profil=PROFIL,
            max_tokeni=3000,
            alt_model_decat=alt,
            variabile={
                "tip": x.lv.tip,
                "canal": x.lv.canal,
                "subiect": x.slot.subiect,
                "fapte": _text_fapte(x.fapte),
                "context": x.context,
                "anterioare": _anterioare(db, x.lv.id),
                "concepte": _text_concepte(propunere.concepte),
            },
        )

    r: gateway.Rezultat | None = None
    if _alt_model_permis(db, autor):
        try:
            r = cere(autor)
        except (gateway.Amanat, gateway.FurnizoriIndisponibili):
            r = None  # celălalt model nu răspunde acum: autoevaluare, marcată
    if r is None:
        r = cere(None)
    if not isinstance(r.iesire, CriticaIdei):
        raise TypeError("ieșirea nu respectă schema promptului")
    return r.iesire, r.model, r.model == autor


# --- lanțul, persistat ---


def concepte(db: Session, livrabil_id: uuid.UUID) -> list[IdeeConcept]:
    return list(
        db.execute(
            select(IdeeConcept)
            .where(IdeeConcept.livrabil_id == livrabil_id)
            .order_by(IdeeConcept.runda, IdeeConcept.sursa, IdeeConcept.nr)
        ).scalars()
    )


def _cu_dovada(c: Concept, fapte: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {**c.model_dump(mode="json"), "dovada_text": fapte.get(_alias(c.dovada), {}).get("text", "")}


def _salveaza(
    db: Session, x: _Intrare, runda: int, a: Alegere, *, autor: str, critic: str, autoevaluare: bool
) -> IdeeConcept | None:
    ales = None
    for e in a.evaluate:
        rand = IdeeConcept(
            id=new_id(),
            tenant_id=x.lv.tenant_id,
            livrabil_id=x.lv.id,
            runda=runda,
            nr=e.nr,
            sursa=e.sursa,
            concept=_cu_dovada(e.concept, x.fapte),
            note=e.note,
            scor=e.scor,
            obiectii=e.obiectii,
            probleme=[*e.probleme, *([e.eliminat] if e.eliminat else [])],
            ales=e is a.ales,
            motiv=a.motiv if e is a.ales else "",
            model_autor=autor,
            model_critic=critic,
            autoevaluare=autoevaluare,
        )
        db.add(rand)
        if e is a.ales:
            ales = rand
    db.flush()
    return ales


def pregateste(
    db: Session, livrabil_id: uuid.UUID, *, utilizator_id: uuid.UUID | None = None
) -> dict[str, Any]:
    """Etapa de idee a unui livrabil `planificat`: întoarce conceptul ales (dict). Idempotent: un concept ales
    se refolosește. Ridică `IdeeLaOm` (conceptele rămân salvate, apelantul face commit) când nimic nu trece,
    `gateway.Amanat` (nimic salvat) sau `RegulaCreier`."""
    # întâi lacătul: două fluxuri pe același livrabil nu dublează ideea
    lv = productie.blocheaza(db, livrabil_id)
    existente = concepte(db, livrabil_id)
    ales = next((r for r in existente if r.ales), None)
    if ales is not None:
        return {**ales.concept, "id": str(ales.id)}
    if existente:
        raise IdeeLaOm("niciun concept nu a trecut critica și validarea: alege omul")
    if Stare(lv.stare) is not Stare.PLANIFICAT:
        raise creier.RegulaCreier(f"ideea se gândește pentru un livrabil planificat, nu „{lv.stare}”")
    x = _intrare(db, livrabil_id, utilizator_id)
    propunere, autor = propune(db, livrabil_id, intrare=x)
    cr, critic, autoev = critica(db, livrabil_id, propunere, autor=autor, intrare=x)
    a = alege(propunere, cr, x.fapte, video=x.video)
    rand = _salveaza(db, x, 1, a, autor=autor, critic=critic, autoevaluare=autoev)
    runde = 1
    if rand is None and (tinta := a.de_rescris) is not None:
        runde = 2
        rescris, autor2 = propune(db, livrabil_id, intrare=x, de_rescris=tinta)
        rescris = PropunereIdei(
            concepte=rescris.concepte[:1], dovezi=rescris.dovezi, incredere=rescris.incredere
        )
        cr2, critic2, autoev2 = critica(db, livrabil_id, rescris, autor=autor2, intrare=x)
        a = alege(
            rescris, cr2.model_copy(update={"imbunatatit": None}), x.fapte, video=x.video, sursa="rescris"
        )
        if a.ales is not None:
            a.motiv = f"rescris cu obiecțiile conceptului {tinta.nr}: {a.motiv}"
        rand = _salveaza(db, x, 2, a, autor=autor2, critic=critic2, autoevaluare=autoev2)
    detalii = {
        "concepte": len(propunere.concepte),
        "runde": runde,
        "autoevaluare": autoev,
        "ales": str(rand.id) if rand else None,
        "motiv": a.motiv,
    }
    audit.record(
        db,
        "continut.idee_aleasa" if rand else "continut.idee_la_om",
        obiect_tip="livrabil",
        obiect_id=x.lv.id,
        utilizator_id=utilizator_id,
        tenant_id=x.lv.tenant_id,
        actor_tip=None if utilizator_id else "sistem",
        detalii=detalii,
    )
    urme.inregistreaza(
        db,
        "continut",
        "idee",
        rezultat="ok" if rand else "blocat",
        motiv=a.motiv[:200],
        obiect_tip="livrabil",
        obiect_id=str(x.lv.id),
        iesiri=detalii,
    )
    if rand is None:
        raise IdeeLaOm(a.motiv)
    return {**rand.concept, "id": str(rand.id)}


def alege_manual(db: Session, idee_id: uuid.UUID, *, utilizator_id: uuid.UUID) -> IdeeConcept:
    """Omul alege un concept salvat al unui livrabil care nu are încă unul ales (după `IdeeLaOm`)."""
    rand = db.get(IdeeConcept, idee_id)
    if rand is None:
        raise creier.RegulaCreier("conceptul nu există")
    if any(r.ales for r in concepte(db, rand.livrabil_id)):
        raise creier.RegulaCreier("livrabilul are deja un concept ales")
    rand.ales, rand.decis_de, rand.motiv = True, utilizator_id, "ales de om"
    db.flush()
    audit.record(
        db,
        "continut.idee_aleasa",
        obiect_tip="livrabil",
        obiect_id=rand.livrabil_id,
        utilizator_id=utilizator_id,
        tenant_id=rand.tenant_id,
        detalii={"ales": str(rand.id), "motiv": "ales de om"},
    )
    urme.inregistreaza(
        db,
        "continut",
        "idee",
        rezultat="ok",
        motiv="ales de om",
        obiect_tip="livrabil",
        obiect_id=str(rand.livrabil_id),
        iesiri={"ales": str(rand.id)},
        actor=str(utilizator_id),
    )
    return rand
