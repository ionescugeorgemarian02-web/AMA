# ruff: noqa: E501
"""Interviul de onboarding din docs/19 §19.3, ca DATE (F4.4).

„Interviul acoperă: ce vinde firma, cui, la ce preț, de ce o aleg clienții, ce obiecții aude, ce concurenți are,
ce a încercat, ce nu vrea să apară niciodată, ce ton vrea și ce obiectiv are pe 90 de zile.” Fiecare întrebare
alimentează exact un câmp al brieful (`brief.CAMPURI`). Întrebările se schimbă aici, nu în logica serviciului.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Intrebare:
    cod: str
    camp: str  # câmpul din brief pe care îl alimentează
    text: str
    ajutor: str  # exemplu / îndrumare pentru cine răspunde
    min_caractere: int = 20  # sub această lungime răspunsul e socotit prea scurt
    clarificare_sablon: str = "Poți da un exemplu concret sau mai multe detalii?"  # când modelul nu răspunde


@dataclass(frozen=True)
class Sectiune:
    cod: str
    titlu: str
    intrebari: tuple[Intrebare, ...]


INTERVIU: tuple[Sectiune, ...] = (
    Sectiune(
        "afacerea",
        "Afacerea",
        (
            Intrebare(
                "nume", "nume_brand", "Cum se numește brandul și în ce domeniu activează?",
                "Numele sub care vă cunosc clienții și domeniul (de exemplu: prăjitorie de cafea, Brașov).",
                min_caractere=8,
            ),
            Intrebare(
                "ce_vinde", "ce_vinde", "Ce vindeți, concret? Enumerați produsele sau serviciile principale.",
                "Produse sau servicii cu nume, nu categorii generale.",
                clarificare_sablon="Care sunt cele 2–3 produse sau servicii care aduc cei mai mulți bani, pe nume?",
            ),
            Intrebare(
                "preturi", "preturi", "La ce prețuri vindeți? Dați cifrele pentru produsele principale.",
                "Prețuri sau intervale de preț, cu moneda și unitatea (lună, bucată, kilogram).",
                clarificare_sablon="Care este prețul exact (sau intervalul) pentru fiecare produs principal?",
            ),
        ),
    ),
    Sectiune(
        "clientii",
        "Clienții",
        (
            Intrebare(
                "public", "public_tinta", "Cui vindeți? Descrieți clientul tipic.",
                "Cine sunt, ce vârstă sau ce tip de firmă, ce îi face să cumpere.",
                clarificare_sablon="Descrieți un client real tipic: cine este, ce caută și unde vă găsește?",
            ),
            Intrebare(
                "de_ce_ne_aleg", "de_ce_ne_aleg", "De ce vă aleg clienții în loc de alții?",
                "Ce spun clienții când vă recomandă; ce faceți mai bine.",
                clarificare_sablon="Ce motiv concret au spus clienții pentru care v-au ales?",
            ),
            Intrebare(
                "obiectii", "obiectii", "Ce obiecții auziți cel mai des înainte de o comandă?",
                "Ce îi face să ezite: preț, încredere, livrare, comparație cu alții.",
                clarificare_sablon="Dați trei obiecții pe care le auziți, cu cuvintele clientului dacă le știți.",
            ),
        ),
    ),
    Sectiune(
        "piata",
        "Piața și ce s-a încercat",
        (
            Intrebare(
                "concurenti", "concurenti", "Cine sunt principalii 3–5 concurenți? Numele și, dacă îl aveți, site-ul.",
                "Nume de firme și adrese de site, separate prin virgulă.",
                min_caractere=8,
                clarificare_sablon="Numiți cel puțin trei concurenți direcți și site-ul fiecăruia.",
            ),
            Intrebare(
                "ce_a_incercat", "ce_a_incercat", "Ce ați încercat deja în marketing și ce a mers sau nu?",
                "Canale, reclame, campanii; rezultate, chiar și aproximative.",
                clarificare_sablon="Dați un exemplu: ce ați făcut, când și ce rezultat a avut?",
            ),
        ),
    ),
    Sectiune(
        "limite_si_ton",
        "Limite și ton",
        (
            Intrebare(
                "interdictii", "interdictii", "Ce nu vreți să apară niciodată în comunicarea voastră?",
                "Subiecte, cuvinte, promisiuni, comparații sau imagini de evitat.",
                clarificare_sablon="Dați exemple de subiecte, cuvinte sau promisiuni pe care nu le vreți niciodată.",
            ),
            Intrebare(
                "ton", "ton_dorit", "Ce ton vreți să aveți față de clienți?",
                "Cum ați vrea să sune brandul: prietenos, expert, cald, direct; un exemplu de brand care vă place.",
                clarificare_sablon="Descrieți tonul în câteva cuvinte și dați un exemplu de brand al cărui ton vă place.",
            ),
        ),
    ),
    Sectiune(
        "obiectiv",
        "Obiectivul pe 90 de zile",
        (
            Intrebare(
                "obiectiv", "obiectiv_90_zile", "Ce obiectiv aveți în următoarele 90 de zile?",
                "Un rezultat măsurabil: comenzi, abonamente, programări, vizitatori în cafenea.",
                clarificare_sablon="Exprimați obiectivul ca o cifră și un termen (de exemplu: 40 de abonamente noi în 90 de zile).",
            ),
        ),
    ),
)  # fmt: skip


def intrebari() -> list[Intrebare]:
    return [q for s in INTERVIU for q in s.intrebari]


def camp_intrebare(cod: str) -> Intrebare:
    for q in intrebari():
        if q.cod == cod:
            return q
    raise KeyError(cod)


def sectiune_intrebare(cod: str) -> Sectiune:
    for s in INTERVIU:
        if any(q.cod == cod for q in s.intrebari):
            return s
    raise KeyError(cod)


def valideaza() -> list[str]:
    """Probleme ale interviului ca date: coduri dublate, câmp comun, câmp necunoscut brief-ului."""
    from app.onboarding import brief

    probleme: list[str] = []
    coduri: set[str] = set()
    campuri: set[str] = set()
    for q in intrebari():
        if q.cod in coduri:
            probleme.append(f"cod dublat: {q.cod}")
        if q.camp in campuri:
            probleme.append(f"două întrebări pentru câmpul {q.camp}")
        if q.camp not in brief.CAMPURI:
            probleme.append(f"câmp necunoscut brief-ului: {q.camp}")
        coduri.add(q.cod)
        campuri.add(q.camp)
    for c in brief.CAMPURI:
        if c not in campuri:
            probleme.append(f"câmpul {c} nu are întrebare")
    return probleme
