# Coordonarea sesiunilor de cod care lucrează în paralel

La proiect lucrează două sesiuni Claude în același timp, fiecare pe ramura ei. Fișierul acesta spune cine ce
face și cum nu ne călcăm pe fișiere (regula din `docs/23` §23.20: „două sesiuni nu modifică aceleași fișiere”).
**Se citește la începutul fiecărei sesiuni, după `AGENTS.md`, și se actualizează la fiecare pas închis.**

## Cine ce face (actualizat: 2026-11-14)

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
| F11.4 Registrul de experimente | urmează |
| F11.5–F11.6 | neîncepute |

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
