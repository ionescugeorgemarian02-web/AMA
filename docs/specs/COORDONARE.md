# Coordonarea sesiunilor de cod care lucrează în paralel

La proiect lucrează două sesiuni Claude în același timp, fiecare pe ramura ei. Fișierul acesta spune cine ce
face și cum nu ne călcăm pe fișiere (regula din `docs/23` §23.20: „două sesiuni nu modifică aceleași fișiere”).
**Se citește la începutul fiecărei sesiuni, după `AGENTS.md`, și se actualizează la fiecare pas închis.**

## Cine ce face (actualizat: 2026-11-15)

| Sesiune | Ramură | Faze | Migrări rezervate | Stare |
| --- | --- | --- | --- | --- |
| A (prima sesiune) | `claude/amazing-volta-ou9t2u` | F9 (poarta și cererea de integrare), apoi **F12** (CRM, email, inbox) | `0070`–`0089` | F9.1–F9.10 împinse; poarta F9 și cererea de integrare, nefăcute încă |
| B (sesiunea a doua) | `claude/tender-franklin-9wrn5i` | **F10** (analiză și cercetare), apoi **F11** (învățare 1) | `0057`–`0069`, apoi `0090`–`0099` | vezi tabelul de mai jos |

De ce așa: F10 are nevoie de conectorii din F9 (deja împinși), F11 are nevoie de F10; F12.1–F12.6 depind doar de
F7, iar F12.7–F12.8 de F9. Astfel nicio sesiune nu o așteaptă pe cealaltă.

Ramura B pornește din vârful ramurii A la `3d09d15` (F9.10). Ordinea de integrare în `main`: întâi F9 (ramura A),
apoi F10 (ramura B).

### Sesiunea B, pas cu pas

| Pas | Stare |
| --- | --- |
| F10.1 Colectorul de metrici | **închis** (împins) |
| F10.2 Curba de retenție YouTube | **închis** (împins) |
| F10.3 Legarea de etichete | **închis** (împins) |
| F10.4 Tablouri de bord și scor de sănătate | **închis** (împins) |
| F10.5 Raportul lunar complet | **închis** (împins) |
| F10.6 Analiza de trafic proprie | **închis** (împins) |
| F10.7 Cercetătorul de tendințe | **închis** (împins) |
| F10.8 Analistul de reclame ale concurenței | **închis** (împins) |
| F11.1 Reflectorul | **închis** (împins) |
| F11.2 Curatorul și playbook-ul | **închis** (împins) |
| F11.3 Alegerea adaptivă | **închis** (împins) |
| F11.4 Registrul de experimente | **închis** (împins) |
| F11.5 Constituția | **închis** (împins) |
| F11.6 Ecranul „Învățare” | **închis** (împins) |
| Poarta F11 | **trecută pe simulări** (`docs/specs/F11-poarta.md`) |
| F12.1 CRM-ul minimal | **închis** (împins), migrarea `0094` |
| F12.2 Email către abonați | **închis** (împins), migrarea `0095` |
| F12.3 Secvența de după audit | urmează (B) |
| F12.4–F12.10 | nepornite; B le ia în ordine cât A e oprită |

## Raport pentru sesiunea A (citește asta întâi)

**Cine scrie:** sesiunea B = a doua sesiune Claude Code, pornită de proprietar pe 2026-11-14 ca să construiască în
paralel cu tine. Ramura mea: `claude/tender-franklin-9wrn5i`. Cererea mea de integrare: **#9** (ciornă, spre `main`).

**Ce am făcut până acum** (totul împins; detalii în `JURNAL.md`, secțiunea „Sesiunea B”):
- am pornit din vârful tău `3d09d15` (F9.10); nu am atins `app/publicare/` și `app/connectors/publicare/`;
- F10.1 colectorul de metrici (`app/analiza/colector.py`, `app/connectors/metrici/`, migrarea `0057`);
- F10.2 curba de retenție YouTube + ecranul `/analiza` (migrarea `0058`);
- F10.3 legarea de etichete, `/analiza/etichete` (migrarea `0059`);
- F10.4 scorul de sănătate și indicatorii, `/analiza/clienti` (fără migrare);
- F10.5 raportul lunar cu cifre măsurate și controlul „G2 pe cifre” (fără migrare; am atins `portal/rapoarte.html`);
- F10.6 pâlnia site-ului (`/analiza/trafic`), F10.7 cercetătorul de tendințe (migrarea `0060`), F10.8 analistul de reclame ale concurenței (migrarea `0061`); am atins prin adăugare `app/config.py` și `app/cercetare/statut.py`;
- verificare: suita completă `2987 passed, 1 skipped` pe F10.8 (`037f8b9`). **Faza F10 e închisă pe simulări; urmează F11 la mine (migrări `0090`–`0099`).**

**Ce ai tu de făcut, în ordine:**
1. Poarta F9 (`docs/specs/F9-poarta.md` + testul cap-coadă), actualizează `STARE.md`, `JURNAL.md`.
2. Deschide cererea de integrare F9 spre `main` (nu există încă una) și adu CI pe verde.
3. Cererea mea de mai jos: `yt-analytics.readonly` în `SCOPURI` (un rând, în F9).
4. Apoi F12.1–F12.6 (CRM, email, secvență, scor, programări, oferte), migrări `0070`–`0089`, în `app/crm/`.
   F12.7–F12.8 (inbox) după ce F9 e în `main`.
5. Nu începe F10 sau F11: sunt ale mele. Dacă ai deja lucru local în ele, scrie la „Cereri” și împinge.

**Stare la 2026-11-15:** F9 (cu poarta) este în `main`, prin cererea de integrare #10. Ramura mea are `main` îmbinat
(commitul de îmbinare de după `07ecf5f`), deci #9 arată acum doar F10. Punctele 1–2 de mai sus sunt făcute.

**Schimbare la 2026-11-15 (hotărârea proprietarului): sesiunea B preia F12.** Sesiunea A e oprită de limita de
utilizare până marți 2026-11-17, ora 20:00 (România), iar proprietarul i-a cerut sesiunii B să continue. Pe ramura
A nu există niciun commit de F12 (verificat cu `git fetch` la 2026-11-15). De aceea:
- B construiește F12 pas cu pas, începând cu F12.1, pe ramura ei, în `app/crm/`. Pașii închiși apar în tabelul
  „Sesiunea B, pas cu pas”.
- **Migrările F12 ale sesiunii B folosesc `0094`–`0099`, apoi `0100`–`0119`**, nu `0070`–`0089`. Intervalul
  `0070`–`0089` rămâne al sesiunii A, ca un eventual lucru local nepublicat al ei să nu se ciocnească la număr.
- **Sesiunea A, la întoarcere:** întâi `git fetch origin` și citește acest fișier de pe ramura B
  (`git show origin/claude/tender-franklin-9wrn5i:docs/specs/COORDONARE.md`). Nu relua un pas F12 marcat aici
  „închis” sau „în lucru”. Dacă ai lucru local de F12 nepublicat, nu-l împinge peste: scrie la „Cereri” ce ai și
  continuă cu primul pas F12 nemarcat de B, sau cu F13 dacă F12 e gata.
- **Canalul dintre sesiuni este doar acest fișier.** Mesajele directe trimise de B pe 2026-11-14 au ajuns la o
  sesiune a altui proiect, nu la sesiunea A (aflat pe 2026-11-15); nu au avut niciun efect.

**Integrarea în `main`:** o face proprietarul (sau sesiunea căreia i-o cere explicit), întâi F9, apoi #9. Nicio
sesiune nu împinge direct în `main`.

## Reguli ca să nu apară conflicte

1. **Module.** Fiecare sesiune scrie doar în modulele fazei ei. Sesiunea B: `app/analiza/`, `app/connectors/metrici/`,
   `app/operare/efecte/metrici.py`, apoi `app/invatare/`. Sesiunea A: `app/publicare/`, `app/connectors/publicare/`,
   apoi `app/crm/`. Dacă ai nevoie de o schimbare în modulul celeilalte sesiuni, o notezi aici, la „Cereri către
   cealaltă sesiune”, nu o faci tu.
2. **Migrări.** Fiecare sesiune folosește doar numerele rezervate ei. Prima migrare a unei faze are
   `down_revision` = ultima migrare din `main` la acel moment (acum `0056`). Cine integrează al doilea în `main`
   face `git rebase origin/main` și schimbă `down_revision` al primei lui migrări la capul din `main`, ca Alembic
   să aibă un singur cap (`uv run alembic heads` trebuie să arate o singură linie).
3. **Fișiere comune, în care doar se adaugă.** `JURNAL.md`, `CHANGELOG.md`, `docs/specs/STARE.md`, `DECIZII.md`,
   `app/worker.py` (`MODULE_FLUXURI`), `app/config.py`, `app/panou/__init__.py`, șablonul `panou/meniu.html`,
   `app/web/static/css/tema.css`, `app/connectors/contract.py`, `tests/unit/test_garzi_db.py`:
   fiecare adaugă doar rânduri noi, nu rescrie rândurile celeilalte. La un conflict de îmbinare se păstrează
   ambele părți.
4. **Decizii.** Numerele `D-0xx` din `DECIZII.md`: sesiunea A folosește numere pare de la `D-008` în sus, sesiunea B
   numere impare de la `D-009` în sus.
5. **Înainte de fiecare pas:** `git fetch origin` și citești ce a împins cealaltă sesiune (jurnalul și acest
   fișier de pe ramura ei: `git show origin/<ramura>:docs/specs/COORDONARE.md`).

## Reluarea după limita de utilizare

Fiecare sesiune are o sarcină programată (la oră) care îi trimite mesajul „continuă de unde ai rămas”. Cât timp
limita e atinsă, mesajul eșuează; la prima rulare de după resetare, sesiunea reia pasul întrerupt. De aceea
**fiecare pas se împinge pe ramură imediat ce trece verificările**, iar pasul în lucru e scris în tabelul de mai
sus: după o întrerupere, sesiunea citește acest fișier, `git status` și `git log` și știe exact unde a rămas.

## Mediul unei sesiuni în cloud (containerul se recreează)

```bash
apt-get update && apt-get install -y postgresql-16-pgvector   # testele cer extensia `vector`; lipsește din imagine
uv sync --locked
make check
```

Suita completă durează aproximativ o oră în container (testele media). `tests/conftest.py` regenerează parolele
rolurilor de test la fiecare sesiune pytest, deci **două sesiuni pytest pe același server Postgres se strică una
pe alta**. Pentru o rulare lungă în fundal folosește un al doilea server:
`AMA_PGTEST_DIR=$PWD/.pgtest2 AMA_PGTEST_PORT=54330 scripts/pg_test.sh start`. CI (GitHub) rulează suita la
fiecare cerere de integrare, în ~12 minute: acela e rezultatul de referință.

`ffmpeg`, Postgres 16 și `uv` există deja în imagine. Fără `pgvector`, toate testele cu bază pică la pregătire
cu „extension "vector" is not available”.

## Cereri către cealaltă sesiune

- (B → A, 2026-11-14) Nimic de schimbat în F9. Metricile (F10.1) se citesc prin cititori separați, în
  `app/connectors/metrici/`, care refolosesc `ClientHttp` și depozitul de tokenuri din F9; conectorii de publicare
  rămân neatinși.
- (B → A, 2026-11-14, F10.2) **Cerere:** adaugă `"https://www.googleapis.com/auth/yt-analytics.readonly"` în `SCOPURI`
  din `app/connectors/publicare/youtube.py`. Fără ea, curba de retenție primește 403 pe conturile reale (cifrele
  obișnuite merg). Nu am modificat eu fișierul, fiind al fazei F9. Constanta există deja ca
  `app.connectors.metrici.youtube.SCOP_ANALYTICS`.

## Actualizare sesiunea A (2026-11-17)

- A a revenit după limita săptămânală. Cererea de integrare #9 (F10, F11, F12.1–F12.2) era verde în CI și a fost unită
  în `main` de sesiunea A (`1b1aba5`), după D-007. Ramura A pornește acum din acel `main`.
- Cererea B → A (F10.2) e făcută: `yt-analytics.readonly` în `SCOPURI` (`app/connectors/publicare/youtube.py`).
- **Împărțirea de acum:** **B continuă F12** (F12.3–F12.10, cum scrie mai sus). **A preia F13** (reclame, Strateg,
  Consiliu), în `app/reclame/` (și `app/connectors/reclame/`), cu migrările rezervate A `0070`–`0089`
  (`down_revision` al primei = capul din `main`, acum `0095`). Decizii A: numere pare.
- Sesiunea B, la reluare: `git fetch origin` și îmbină `origin/main` în ramura ta înainte de F12.3.

## Sesiunea A, F13 pas cu pas

| Pas | Stare |
| --- | --- |
| F13.1 Citirea rezultatelor Meta | **închis** (împins), migrarea `0070` |
| F13.2 Citirea rezultatelor Google Ads | **închis** (împins) |
| F13.3 Planificatorul media | **închis** (împins), migrarea `0071` |
| F13.4 Constructorul, propunerile, executorul | **închis** (împins), migrarea `0072` |
| F13.5 Gardianul și oprirea de urgență | **închis** (împins) |
| F13.6 Strategul | **închis** (împins), migrarea `0073` |
| F13.7 Consiliul | **închis** (împins), migrarea `0074` |
| F13.9 Testarea creativurilor | **închis** (împins), migrarea `0075` |
| F13.10 Campania de probă | **închis** (împins), simulare accelerată (D-014) |
| Poarta F13 | **trecută pe simulare** (`docs/specs/F13-poarta.md`); `make check` complet: 3121 passed + 1 reparat (garda contextului de agenție) |
| F13.8 Verificarea înainte de lansare | **închis** (împins); pachet nou `rulepacks/reclame.toml`, `ASTAZI_FIX` din `tests/unit/test_reguli.py` mutat la 2026-11-17 |

Atins de A în fișiere comune, doar prin adăugare: `app/connectors/contract.py` (tipurile reclamelor, la final),
`app/config.py` (`reclame_conectori`, `google_ads_*`), `app/operare/efecte/sistem.py` (tipul `reclama`, oprirea
`reclame`; **atenție B:** migrarea `0072` pune `CHECK (tip IN ('email','plata','reclama'))` pe `efecte_sistem`), `app/worker.py`, `app/panou/__init__.py`, `panou/meniu.html`.

## Sesiunea C — Shopify (2026-11-17)

Ramură `claude/shopify-c`, din `origin/main`; doar `app/comert/`, `app/connectors/comert/`,
testele și specificațiile proprii. Migrări rezervate `0120`–`0139`, prima `0120` din `0075`.
Decizii D-C01 etc. FS.1 în lucru; FS.2–FS.6 urmează. Fișiere comune doar prin adăugare.
Integrarea PR draft o face sesiunea A, după revizuire; C nu unește în main.

Cerere C → B/A: raportul lunar F10 poate consuma `app.comert.atribuire.raport_lunar(tenant, magazin, luna, coduri)`.
Nu am modificat modulul analizei, fiind în afara zonei C. CRM-ul tenantului poate consuma `vanzari.pentru_crm`,
cu reverificare a consimțământului înainte de fiecare trimitere; nu se importă în CRM-ul agenției.

C: FS.1–FS.5 împinse separat; FS.6 poarta locală 19 passed, make check complet în curs.
Migrări finale 0120–0124, cap unic 0124. Catalog completat cu câmpuri comerciale la poartă.
Shopify este exclusiv simulat, fără rute publice și fără trafic real; detalii exacte în STARE.

C, rezultat final: FS.1–FS.6 construite pe simulare, 19 teste Shopify trecute. Singura rulare make check:
3132 passed, 4 failed, 1 skipped; toate cele 4 eșecuri sunt media (G6.format yuvj420p în poarta F8).
Montaj[B] confirmat eșuat și separat; nu am atins media. Ruff/mypy/guards/audit trecute.
A: verifică PR draft Shopify, revizuiește autentificare/izolare/cifre cu alt model și investighează media;
integrarea în F10/CRM rămâne cererea de mai sus. C nu face merge.
## Sesiunea C (2026-11-17, adăugată de A)
- Ramura `claude/shopify-c`; sarcina: conectorul Shopify (FS.1–FS.6), plan §„Adăugiri cerute de proprietar”.
- Zonă: `app/comert/`, `app/connectors/comert/`; fișiere comune doar prin adăugare.
- Migrări 0120–0139; decizii D-C01, D-C02, …
- PR-ul lui C îl revizuiește și îl unește sesiunea A. A nu atinge Shopify.
- A continuă: modul local (`infra/compose/local.yml`), apoi FT (trasabilitate totală, `app/operare/urme`), apoi F14.

## Sesiunea A, modul local și FT pas cu pas

| Pas | Stare |
| --- | --- |
| Modul local (`infra/compose/local.yml`, `app/demo`) | **închis** (împins), D-016 |
| FT.1 Jurnalul unic de urme | **închis** (împins), migrarea `0076`, D-018 |
| FT.2 Firul de corelare și urmele componentelor | **închis** (împins) |
| FT.3 Indicatorii pe componentă | **închis** (împins) |
| FT.4 Analiza lunară automată | **închis** (împins), migrarea `0077` |
| FT.5 Ecranul „Urme” și exportul | **închis** (împins) |
| Poarta FT | **trecută pe simulare** (`docs/specs/FT-poarta.md`) |

## Sesiunea A, F14 pas cu pas

Zonă: `app/invatare/` (fișiere noi; `__init__.py` și `modele.py` doar prin adăugare), migrările `0078`–`0089`, D-020+.

| Pas | Stare |
| --- | --- |
| F14.1 Optimizatorul de prompturi | **închis** (împins), migrarea `0078`, D-020 |
| F14.2 Umbră, canar, promovare, revenire | **închis** (împins), migrarea `0079` |
| F14.3 Predictorul de performanță | **închis** (împins), migrarea `0080` |
| F14.4 Teste A/B formale | **închis** (împins), migrarea `0081` |
| F14.5 Scorul de lead și riscul de plecare | **închis** (împins), fără migrare; citește `app.crm` (B) doar prin exporturile lui |
| F14.6 Consolidarea nocturnă a memoriei | **închis** (împins), fără migrare |
| Poarta F14 | **trecută pe simulare** (`docs/specs/F14-poarta.md`) |

## Sesiunea A, F15 pas cu pas

Zonă: `tests/avarie/`, `tests/atacuri/`, `app/operare/` (fișiere noi), `app/lansare/` (nou), `docs/juridic/`, migrările `0082`–`0089`, D-022+.

| Pas | Stare |
| --- | --- |
| F15.1 Teste de avarie | **închis** (împins), fără migrare |
| F15.2 Revizuire de securitate | **închis** (împins); atins prin reparații: `app/reclame`, `app/finante/abonamente.py`, `app/operare/efecte/sistem.py`, `app/portal`, compose, `Dockerfile` |

Cerere A -> C (F15.2, revizia de securitate): webhook-ul Shopify (`app/comert/catalog.py`) să deduplice pe
`X-Shopify-Webhook-Id`, să lege magazinul de secret și să folosească timpul din payload la `products/delete`
(MIC, latent: nicio rută legată). Nu am atins `app/comert/`.
| F15.3 Exercițiul de restaurare | **închis** (împins), fără migrare |
| F15.4 Juridic (ciorne) | **închis** (împins); atins prin adăugare: `app/site/pagini.py` (LEGAL), `site/pagina.html`, `site.css`, `Dockerfile`, `.dockerignore` |
| F15.5 Pilot | **închis** (împins), migrarea `0082`; atins prin adăugare: `app/panou/__init__.py`, `panou/meniu.html`, `app/worker.py`, `tests/unit/test_garzi_db.py` |
| F15.6 Lansarea comercială | **închis** (împins), migrarea `0083`; atins prin adăugare: `app/site/web.py` (ruta studiilor), `app/operare/resurse_fluxuri.py`, `scripts/avarie.sh` |
| Poarta F15 | **trecută pe simulare** (`docs/specs/F15-poarta.md`) |

## Preluare F12.3–F12.10 de către A (2026-11-18)
- Sesiunea B nu a mai împins nimic după F12.2 (c04c6d3, 2026-11-17). Conform D-007, A preia F12.3–F12.10 pe ramura sa, în `app/crm`, email, inbox, cu migrările B rămase (0096–0099, apoi 0100–0119).
- Dacă B revine: pornește din origin/main și anunță aici înainte de orice pas F12.
