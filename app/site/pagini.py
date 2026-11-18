# ruff: noqa: E501  (textele paginilor: date)
"""Paginile site-ului public (docs/19 §19.1), ca DATE. Nucleu pur.

Fiecare pagină are titlu, descriere (meta), secțiuni (titlu + paragrafe sau liste) și un singur apel la acțiune,
spre auditul gratuit. Paginile dinamice (blogul, studiile de caz din platformă, starea, auditul) își adaugă
conținutul în rute. Datele firmei sunt substituenți: NEVERIFICAT (F0.1, la migrare)."""

from dataclasses import dataclass, field
from pathlib import Path

from app.finante import planuri

NUME = "AMA — Agenția Autonomă de Marketing"
NUME_SCURT = "AMA"


@dataclass(frozen=True)
class Sectiune:
    titlu: str
    paragrafe: tuple[str, ...] = ()
    lista: tuple[str, ...] = ()


@dataclass(frozen=True)
class Pagina:
    cale: str  # relativ la rădăcina site-ului: "" = Acasă
    titlu: str
    descriere: str
    sectiuni: tuple[Sectiune, ...] = ()
    in_meniu: bool = True
    eticheta_meniu: str = ""
    extra: dict[str, str] = field(default_factory=dict)


def _planuri() -> tuple[Sectiune, ...]:
    s = []
    for p in planuri.PLANURI.values():
        livr = [f"{n} {planuri.ETICHETE_LIVRABILE[t]}" for t, n in p.livrabile.items() if n]
        s.append(
            Sectiune(
                f"{p.nume} — {p.pret_lunar:,} lei / lună".replace(",", "."),
                (f"Pentru {p.pentru}. Până la {p.canale} canale.",),
                tuple(livr) + tuple(f"Nu include: {x}" for x in p.nu_include),
            )
        )
    return tuple(s)


SECTIUNI_CUM = (
    Sectiune(
        "Cum funcționează, în trei pași",
        lista=(
            "Ceri auditul gratuit: în câteva minute primești un raport despre prezența firmei tale.",
            "Alegi pachetul: platforma învață brandul tău dintr-un interviu și din materialele tale.",
            "Aprobi de pe telefon: nimic nu se publică fără aprobarea ta.",
        ),
    ),
)

PAGINI: tuple[Pagina, ...] = (
    Pagina(
        "",
        "Marketing făcut de agenți, aprobat de tine",
        "Conținut, publicare și rapoarte pentru IMM-uri din România, produse de agenți AI și verificate de oameni.",
        (
            Sectiune(
                "Ce primești",
                (
                    "Postări, videoclipuri scurte și articole scrise pentru firma ta, din faptele firmei tale, "
                    "verificate automat și aprobate de tine înainte de publicare.",
                ),
            ),
            *SECTIUNI_CUM,
            Sectiune(
                "Pentru cine",
                (
                    "Firme mici și mijlocii din România care vor să apară constant, fără o echipă de marketing.",
                ),
            ),
            Sectiune(
                "Dovezi",
                ("Primele studii de caz sunt brandurile noastre proprii; le publicăm cu cifrele lor reale.",),
            ),
        ),
        eticheta_meniu="Acasă",
    ),
    Pagina(
        "audit",
        "Audit gratuit de marketing",
        "Primești gratuit un raport despre site-ul și prezența online a firmei tale, în câteva minute.",
        (
            Sectiune(
                "Ce primești",
                lista=(
                    "Ce spune site-ul tău despre ce vinzi, cui și la ce preț.",
                    "Ce lipsește ca un client nou să te aleagă.",
                    "Trei lucruri concrete de făcut luna aceasta.",
                ),
            ),
            Sectiune(
                "Cum funcționează",
                (
                    "Completezi formularul, confirmi adresa de email din mesajul primit (opt-in dublu), iar raportul "
                    "îți ajunge pe email. Nu primești alte mesaje fără acordul tău.",
                ),
            ),
            Sectiune(
                "Exemplu de raport",
                (
                    "Pentru o prăjitorie de cafea: „Site-ul spune clar ce vinzi, dar nu spune de ce ești alegerea "
                    "potrivită; prețurile există doar pe o pagină…”",
                ),
            ),
        ),
        eticheta_meniu="Audit gratuit",
    ),
    Pagina(
        "servicii",
        "Servicii și pachete",
        "Pachetele AMA, cu livrabile numărabile și cu ce nu este inclus.",
        _planuri(),
        eticheta_meniu="Servicii",
    ),
    Pagina(
        "preturi",
        "Prețuri",
        "Prețurile pachetelor, costul de pornire și întrebările frecvente.",
        (
            *_planuri(),
            Sectiune(
                "Pornire",
                (
                    f"O singură dată: {planuri.SETUP} lei (interviul, Creierul de brand și strategia pe 90 de zile).",
                ),
            ),
            Sectiune(
                "Întrebări frecvente",
                lista=(
                    "Pot renunța oricând? Da, abonamentul se oprește la sfârșitul lunii plătite.",
                    "Ce se întâmplă dacă o plată nu trece? Ai 7 zile de grație; apoi producția se oprește, "
                    "iar datele tale rămân.",
                    "Prețurile includ TVA? Nu; factura se emite conform legii.",
                ),
            ),
        ),
        eticheta_meniu="Prețuri",
    ),
    Pagina(
        "cum-lucram",
        "Cum lucrăm",
        "Agenți AI plus supraveghere umană: aprobare obligatorie, validare în cascadă, date protejate.",
        (
            Sectiune(
                "Agenți și oameni",
                (
                    "Fiecare material este scris de un agent, verificat de validatori automați (fapte, ton, "
                    "reguli juridice și ale platformelor) și aprobat de un om înainte de publicare.",
                ),
            ),
            Sectiune(
                "Ce se întâmplă cu datele tale",
                (
                    "Datele tale stau pe un server dedicat, separate de ale altor clienți. Le poți exporta sau "
                    "șterge oricând, din portal.",
                ),
            ),
        ),
        eticheta_meniu="Cum lucrăm",
    ),
    Pagina(
        "studii-de-caz",
        "Studii de caz",
        "Situație, acțiune, rezultat: proiectele publicate cu acordul brandurilor.",
        (
            Sectiune(
                "CariereAI și BigBrain",
                (
                    "Brandurile noastre proprii sunt primele studii de caz; rezultatele se publică după primele 90 de "
                    "zile, cu cifre măsurate.",
                ),
            ),
        ),
        eticheta_meniu="Studii de caz",
    ),
    Pagina(
        "blog",
        "Blog",
        "Articole despre marketingul firmelor mici, produse de platformă.",
        eticheta_meniu="Blog",
    ),
    Pagina(
        "despre",
        "Despre și contact",
        "Cine suntem, datele firmei și cum ne contactezi.",
        (
            Sectiune(
                "Datele firmei",
                lista=(
                    "Denumire: se completează la înființare",  # NEVERIFICAT: datele reale ale firmei (F0.1)
                    "CUI: se completează la înființare",
                    "Email: contact@example.invalid",
                ),
            ),
            Sectiune(
                "Programare", ("Cere auditul gratuit și te contactăm noi, în cel mult o zi lucrătoare.",)
            ),
        ),
        eticheta_meniu="Contact",
    ),
    Pagina(
        "transparenta-ai",
        "Transparență AI",
        "Ce generează AI la AMA, cum este verificat și cum este etichetat.",
        (
            Sectiune(
                "Ce este generat",
                (
                    "Textele, scripturile și, din faza media, imaginile și vocea pot fi generate de modele AI.",
                ),
            ),
            Sectiune(
                "Cum este verificat",
                (
                    "Fiecare material trece prin validatori automați și prin aprobarea unui om; cifrele și "
                    "promisiunile trebuie să existe în registrul de fapte al clientului.",
                ),
            ),
            Sectiune(
                "Cum este etichetat",
                (
                    "Materialele generate cu AI poartă eticheta platformei, unde aceasta există, și mențiunea "
                    "„Conținut creat cu ajutorul AI”.",
                ),
            ),
        ),
        eticheta_meniu="Transparență AI",
    ),
    Pagina(
        "legal",
        "Legal",
        "Termeni, confidențialitate, cookie-uri, acord de prelucrare, ștergerea datelor.",
        eticheta_meniu="Legal",
    ),
    Pagina("stare", "Starea serviciului", "Starea platformei AMA și incidentele.", eticheta_meniu="Stare"),
)

DIR_JURIDIC = Path(__file__).resolve().parents[2] / "docs" / "juridic"
CIORNA = (
    "Ciornă — necesită revizuirea avocatului. Textul nu este încă cel final și nu este consultanță juridică."
)


def din_juridic(fisier: str, cale: str) -> Pagina:
    """O pagină legală din ciorna ei din `docs/juridic/` (F15.4): `# Titlu`, `descriere:`, `stare:`, apoi
    secțiuni `## ...` cu paragrafe și liste `- ...`. `stare: ciorna` pune marcajul „necesită revizuirea
    avocatului” pe pagină; după semnătura avocatului rândul se scoate din fișier."""
    randuri = (DIR_JURIDIC / fisier).read_text(encoding="utf-8").splitlines()
    titlu, meta = randuri[0].removeprefix("# ").strip(), {}
    sectiuni: list[Sectiune] = []
    curenta: dict[str, list[str]] | None = None
    nume = ""

    def inchide() -> None:
        if curenta is not None:
            sectiuni.append(Sectiune(nume, tuple(curenta["p"]), tuple(curenta["l"])))

    for r in randuri[1:]:
        r = r.strip()
        if r.startswith("## "):
            inchide()
            nume, curenta = r[3:].strip(), {"p": [], "l": []}
        elif curenta is None and ":" in r:
            k, _, v = r.partition(":")
            meta[k.strip()] = v.strip()
        elif curenta is not None and r.startswith("- "):
            curenta["l"].append(r[2:].strip())
        elif curenta is not None and r:
            curenta["p"].append(r)
    inchide()
    extra = {"ciorna": CIORNA} if meta.get("stare") == "ciorna" else {}
    return Pagina(cale, titlu, meta.get("descriere", titlu), tuple(sectiuni), in_meniu=False, extra=extra)


DOCUMENTE_JURIDICE: tuple[tuple[str, str], ...] = (
    ("termeni.md", "legal/termeni"),
    ("confidentialitate.md", "legal/confidentialitate"),
    ("cookie-uri.md", "legal/cookie-uri"),
    ("acord-prelucrare.md", "legal/acord-prelucrare"),
    ("contract-servicii.md", "legal/contract"),
)

LEGAL: tuple[Pagina, ...] = (
    *(din_juridic(f, c) for f, c in DOCUMENTE_JURIDICE),
    Pagina(
        "legal/stergere-date",
        "Instrucțiuni de ștergere a datelor",
        "Cum ceri ștergerea datelor tale, inclusiv a celor primite de la platformele sociale.",
        (
            Sectiune(
                "Cum ceri ștergerea",
                lista=(
                    "Din portal: Date → Cere ștergerea.",
                    "Prin email, de la adresa contului.",
                    "Datele se șterg în cel mult 30 de zile; jurnalul de audit se păstrează conform legii.",
                ),
            ),
        ),
        in_meniu=False,
    ),
)


TOATE: dict[str, Pagina] = {p.cale: p for p in (*PAGINI, *LEGAL)}
MENIU: tuple[Pagina, ...] = tuple(p for p in PAGINI if p.in_meniu and p.cale not in ("", "stare", "legal"))
SUBSOL: tuple[Pagina, ...] = tuple(p for p in PAGINI if p.cale in ("transparenta-ai", "legal", "stare"))
CAI_SITEMAP: tuple[str, ...] = tuple(TOATE)
