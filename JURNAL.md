# Jurnal de lucru

Jurnal progresiv, cronologic: ce s-a făcut, cine a făcut (ce model), ce s-a verificat și ce a rămas deschis.
Cea mai nouă intrare este jos. Se completează la fiecare pas de lucru, nu doar la final de fază.
Diferența față de `CHANGELOG.md`: acolo stă ce s-a schimbat în produs; aici stă cum s-a lucrat.

## 2026-11-11 — Sesiunea 1: fundația și faza F1

### 1. Citirea planului și modul de lucru
- Citit documentul de arhitectură v1.1 (27 de secțiuni, 17 faze, 146 de pași): secțiunile 1, 6, 18, 20–24, 27.3.
- Hotărâri ale proprietarului: construim întâi pe git, validăm după fiecare capitol, VPS-ul vine la final (D-001); lucru cu subagenți și modele mai ieftine la sarcinile ușoare.
- Mod de lucru ales: orchestratorul (modelul principal) scrie fundația, specificațiile de lucru pentru subagenți și face revizuirea; subagenții (Sonnet) scriu pașii, în paralel doar pe fișiere separate; o cerere de integrare pe fază (D-002).

### 2. F0.2 — Repo și reguli (orchestrator)
- Documentul împărțit pe secțiuni în `docs/` cu un script (27 de fișiere + `index.md`).
- Generate cele 16 ADR-uri, structura de directoare din 24.1, `AGENTS.md`, `CLAUDE.md`, `DECIZII.md`, `CHANGELOG.md`, șablonul de cerere de integrare.
- Rămas la proprietar: protecția ramurii `main` în GitHub; deciziile F0.1 (nișă, pachet, nume).

### 3. F1.1 — Aplicația de bază (orchestrator)
- FastAPI, `/healthz`, `/readyz`, configurare din mediu, jurnale JSON cu corelare, UUIDv7 propriu (fără dependență).
- Verificat: 9 teste în `tests/unit/test_baza.py`.

### 4. F1.2 — Dependențe fixate (orchestrator)
- `uv.lock` cu hash-uri; `scripts/check_pins.py` (dependențe `==`, imagini `@sha256:`, acțiuni GitHub pe SHA); `detect-secrets`; `pip-audit`.
- SHA-urile acțiunilor `actions/checkout` și `astral-sh/setup-uv` luate cu `git ls-remote`, nu din memorie.
- Problemă întâlnită: scanerul de secrete a prins parolele implicite de dezvoltare din `app/config.py` și din CI. Rezolvat: scoase parolele din valorile implicite; marcate explicit cele două rânduri din CI.
- Verificat: `make check` verde (ruff, mypy strict, gărzi, 16 teste). Nerulat local: `make audit` (cere rețea; rulează în CI).

### 5. Commit, împingere, cerere de integrare
- Commit `90085a5` împins pe `claude/amazing-volta-ou9t2u`; deschisă cererea de integrare nr. 1, ca ciornă.

### 6. Valul 1 de subagenți (Sonnet, în paralel, pe fișiere separate) — în lucru
- Subagent A: F1.3–F1.6 (Postgres și migrări, clienți/utilizatori/roluri cu izolare la nivel de rând, autentificare cu al doilea factor, jurnal de audit și de evenimente). Fișiere: `app/`, `migrations/`, `tests/`.
- Subagent B: F1.8–F1.9 (Dockerfile, compose, proxy, instalarea VPS-ului, livrare, backup cu test real de restaurare). Fișiere: `infra/`, `.github/workflows/`, `Dockerfile`, `docs/runbooks/`.
- Urmează: revizuirea ambelor de către orchestrator (alt model decât autorul, secțiunea 24.4), apoi valul 2: F1.7 (coaja panoului) și F1.10 (botul Telegram).

### 7. Jurnalul de lucru
- La cererea proprietarului, creat acest fișier și adăugată regula în `AGENTS.md`: fiecare sesiune și fiecare subagent își consemnează munca aici.

### 8. Instantaneu intermediar
- La cererea proprietarului (tot proiectul stă pe git; containerul de lucru este temporar), munca în curs a subagenților a fost împinsă ca instantaneu „WIP, nerevizuit” (`79c9209`), după o scanare de secrete.

### 9. F1.8–F1.9 — Livrare și backup: subagentul B a terminat (Sonnet)
- Construit: `Dockerfile` (imagini pe amprentă, utilizator fără drepturi, sistem de fișiere doar-citire), compose pentru staging, producție și margine (proxy, deployer, backup), configurarea Caddy, scriptul de instalare a VPS-ului, fluxul de livrare în GHCR, deployer intern (albastru/verde, cu revenire), backup criptat cu `age` + `rclone`, retenție 7/4/6, test săptămânal de restaurare, trei runbook-uri, fișa de măsurare a VPS-ului.
- Rulat de subagent: imaginea construită și pornită pe Docker real; deployer-ul a făcut albastru → verde → revenire pe Docker real; backup și restaurare pe imaginea reală pgvector; `caddy validate`; `shellcheck`; `compose config`.
- Reverificat de orchestrator: 44 de teste trec (29 deployer, 10 backup unitare, 5 de integrare cu backup → ștergere → restaurare reală); `check_pins` verde. Citite: `ci.yml`, scriptul de roluri Postgres.
- Hotărâre a subagentului, acceptată: un al treilea rol de bază, `ama_backup` (ocolește izolarea pe rând doar pentru `pg_dump`), altfel backupul ar ieși gol pe tabelele izolate.
- Neverificat (cere VPS sau GitHub): `bootstrap.sh` pe un server real, Docker rootless pe porturile 80/443, certificatele Let's Encrypt, citirea din GHCR, fluxul `entrega.yml`, stocarea externă reală. Trecute în `docs/specs/STARE.md`.
- Abatere: imaginea oficială `uv` nu a putut fi citită din mediul de lucru, așa că `uv` se instalează din PyPI cu hash-uri fixate. Pachetele `apt` din imaginea de backup nu au versiuni fixate.
- Contracte definite pentru partea de aplicație (de implementat în valul 2): `GET /intern/livrare/cerere`, `POST /intern/livrare/rezultat` (antet `X-Livrare-Token`) și fișierele JSON de stare a backupului (`ama.backup/1`).

### 10. F1.3–F1.6 — Bază, izolare, autentificare, audit: subagentul A a terminat (Sonnet)
- Construit: 4 migrări (extensii; conturi; autentificare; jurnale), `app/db` (sesiuni cu context de client aplicat la fiecare tranzacție), `app/conturi` (roluri și matricea de permisiuni, parole argon2id, TOTP cu secret criptat și protecție la reluare, coduri de recuperare, sesiuni pe server, CSRF, limitarea încercărilor în Postgres, CLI pentru primul proprietar), `app/operare` (jurnal de audit și de evenimente, doar cu adăugare, impus în bază), antete de securitate cu CSP strict.
- Dependențe noi, fixate: `sqlalchemy`, `alembic`, `psycopg[binary]`, `argon2-cffi`, `pyotp`, `cryptography`, `jinja2`, `python-multipart`.
- pgvector instalat și local (pachet apt), deci testul extensiei rulează, nu este sărit.
- Revizuire făcută de orchestrator (alt model decât autorul): citite `app/db/rls.py`, `contexte.py`, `motor.py`, migrarea de conturi, politicile din migrările 3 și 4, `dependente.py`, `limitare.py`, părțile de cookie din `sesiuni.py`. Fără obiecții care să blocheze.
- Reverificat de orchestrator: `make check` verde, 197 de teste. În plus, probă de integrare între cei doi subagenți: pornită imaginea reală pgvector cu scriptul de roluri din `infra/`, rulat `alembic upgrade head` ca `ama_owner`, verificat că `ama_app` vede 0 rânduri și că o inserare fără context este refuzată de bază, apoi `alembic downgrade base`. Toate au trecut.
- Observații notate, nerezolvate acum (propuneri):
  - Izolarea din bază separă clienții între ei; drepturile dintre rolurile aceluiași client (titular / aprobator / vizitator) sunt impuse în aplicație, nu în bază.
  - Un utilizator are o singură apartenență activă; mai multe firme pe același cont vin mai târziu, dacă e nevoie.
  - Lipsesc schimbarea și resetarea parolei și cheile de acces (WebAuthn).
  - Sub încărcare, autentificările simultane pot depăși cu puțin pragul de blocare.
  - Un test de backup a picat o dată într-o rulare completă a subagentului și a trecut la rulările următoare (inclusiv la a mea); de urmărit în CI.

### 11. Valul 2 — pornit subagentul C (Sonnet)
- Sarcină: F1.7 (coaja panoului instalabil: bara de jos, Acasă, temă, service worker, notificări push), partea din panou pentru F1.8 și F1.9 (promovare, revenire, starea backupului) și F1.10 (botul Telegram, butoanele de oprire din 7.8).
- Lucrează singur, ca să nu existe două migrări concurente; trebuie să lase `make check` verde.

### 12. Reluare programată
- La cererea proprietarului (cota de utilizare se apropie de limită), programată o trezire automată a sesiunii la ora 2:00, ora României (2026-11-12, 00:00 UTC; mutată de proprietar de la 23:58 UTC), cu instrucțiunea de a continua din `JURNAL.md` și `docs/specs/STARE.md`: revizuirea valului 2, `make check`, CI, actualizarea cererii de integrare. Faza F2 nu începe înainte de validarea fazei F1.

### 13. Valul 2 încheiat și revizuit — F1.7, F1.10, partea din panou pentru F1.8–F1.9
- Construit de subagentul C (Sonnet): `app/panou` (coaja instalabilă, Acasă, Operare), notificări push (`pywebpush`), rutele interne de livrare `/intern/livrare/*`, citirea stării backupului, `app/connectors/telegram` (webhook, comenzi), `app/operare/opriri.py`, migrarea `0005` (șase tabele, toate cu izolare la nivel de rând). Dependențe: `pywebpush==2.3.0` (nouă), `httpx==0.28.1` (mutată din dezvoltare în rulare).
- Revizuire făcută de orchestrator (alt model decât autorul): citite migrarea `0005`, `livrare.py`, `opriri.py`, webhook-ul și botul Telegram, rutele din `operare_web.py`, gărzile de rol din `panou/web.py`. Schimbări făcute la revizuire:
  - confirmarea repornirii din Telegram are acum o singură încercare (un cod greșit anulează cererea); înainte, codul de 6 cifre putea fi încercat nelimitat timp de 5 minute;
  - tabelul și rutele `oprituri` redenumite `opriri` (cuvântul corect), înainte ca migrarea să ajungă pe vreun server.
- Teste existente modificate de subagent, verificate și acceptate: lista de excepții CSRF (doar `/intern/livrare/rezultat` și `/telegram/webhook`, ambele păzite de jeton), lista de fișiere care au voie în context de agenție, și o aserțiune despre scripturi (acum „fără script inline”, fiindcă paginile încarcă scripturi externe).
- Rulat: `make check` verde, 384 de teste (197 înainte).
- Simulat sau neverificat: trimiterea push reală (marcată `# NEVERIFICAT:`), botul Telegram real, instalarea pe telefon, schimbul cu deployer-ul real. Trecute în `docs/specs/STARE.md`.
- De știut: steagurile de oprire se înregistrează și se auditează, dar nimic nu le citește încă; publicarea (F2.5) va fi primul consumator.
- Propuneri notate, nefăcute: preferințe de notificare pe tip și rezumatul zilnic; alertă Telegram când backupul întârzie; redirecționarea după autentificare spre `/`; curățarea jurnalului de audit.

### 14. CI-ul de pe GitHub: două defecte găsite și reparate
- La prima verificare a rulărilor de pe GitHub, ambele joburi picau (și pe commit-ul revizuit al pașilor F1.3–F1.6, nu doar pe instantanee). Local totul era verde.
- Cauza 1 (jobul `check`): fixture-ul de test schimba parolele rolurilor `ama_owner`/`ama_app` la fiecare bază nouă. Rolurile sunt ale serverului, deci conexiunile următoare erau refuzate. Local nu se vedea, fiindcă Postgres-ul de test accepta conexiuni fără parolă. Reparat: parolele se generează o dată pe rulare; iar `scripts/pg_test.sh` cere acum parolă (scram) pe TCP, ca în CI. Reprodus local înainte de reparație (7 eșecuri, 36 de erori), apoi 384 de teste trec. Probabil tot asta era „testul de backup care a picat o dată” din intrarea 10.
- Cauza 2 (jobul `imagine`): testul de fum pornea imaginea fără bază, iar `/readyz` verifică de la F1.3 baza. Reparat cu `infra/deploy/ci_fum.sh`: pornește Postgres cu scriptul real de roluri din `infra/`, rulează migrările din imagine ca proprietar, pornește aplicația ca `ama_app` și verifică `/healthz` și `/readyz`. Rulat local pe Docker: trece.
- Lecție: „verde local” nu a fost de ajuns; de acum verific rulările de pe GitHub după fiecare împingere a unui pas revizuit.
- Confirmat pe GitHub: ambele joburi (`check`, `imagine`) trec pe commit-ul `2326ab6`. Faza F1 așteaptă validarea proprietarului; F2 nu pornește până atunci.

## 2026-11-12 — Sesiunea 2: faza F2 „Motorul” (F2.1, F2.2, F2.6, F2.7)

### 15. Pașii F2.1, F2.2, F2.6, F2.7 — un agent de cod (Sonnet), pe ramura `claude/amazing-volta-ou9t2u`
- Alți pași din F2 (F2.3–F2.5, F2.8–F2.10) nu au fost atinși. Un commit pe pas, `make check` verde înainte de fiecare.
- **F2.1 — Execuția durabilă.**
  - Verificat pe PyPI: `dbos` 3.5.0 este ultima versiune stabilă (2026-11-10; după ea doar pre-lansări 3.6.0aN); cere Python ≥ 3.10, SQLAlchemy ≥ 2.0.43, psycopg ≥ 3.1; aduce `croniter`, `greenlet`, `python-dateutil` (+ `tzdata`). Fixată cu `==`, `uv lock` / `uv sync --locked` curate. API-ul s-a citit din `.venv` (DBOS 3.x nu mai are baza de aplicație și are cozi „în bază”, `DBOSClient`, `run_migrations=False`).
  - Construit: `app/operare/motor/` (flux, pas, trimite, stare, regula argumentelor, migrarea sistemului), `app/worker.py`, garda `scripts/check_motor.py`, serviciul `worker` în compose, mutarea workerului de către deployer.
  - Verificat: SIGKILL în mijlocul pasului 2 → al doilea proces cu aceeași identitate termină jobul (pas 1 o dată, pas 2 reluat, pas 3 o dată); SIGTERM cu job nesfârșit → ieșire 0, jobul se reia; `ama_app` fără drept de DDL pe schema bibliotecii; web fără executor.
  - Găsit: `resume` nu reia un flux `ERROR`; recuperarea cere același `executor_id` și aceeași versiune; un proces Python cu fire ne-daemon nu iese singur la SIGTERM (iese forțat, cod 0). Detalii în `docs/specs/F2.1.md`.
  - Neverificat local: imaginea Docker, `restart: unless-stopped`, deployer-ul real (CI / migrare).
- **F2.2 — Cozile.**
  - Construit: `cozi.py` (cozile fixe, fabrica de cozi, `calculeaza_prioritate`), `declara_coada`, `trimite(…, coada, prioritate, termen)`.
  - Găsit și reparat: la lansare, firele cozilor citesc din bază limitele **vechi** și apucă să scoată joburi cu ele (după ce numărul de culoare scăzuse de la 2 la 1, au pornit două joburi grele). Soluția: configurarea cozilor se scrie înainte de lansare, prin clientul subțire. Testul a prins-o fiindcă rulează cu limite diferite în teste consecutive.
  - Limite ale bibliotecii, spuse în `docs/specs/F2.2.md`: nu are termene (codificate în prioritate, granulație un minut, stabilite la intrare); nu are preempțiune; două cozi nu pot împărți un semafor (deci `învățare` nu ocupă un culoar `greu`).
  - Verificat: două culoare/trei joburi, un culoar, `io` limitat, `urgent` cu culoarele ocupate, ordinea P0–P3 cu termene, limita de rată (fereastră 1,5 s). Suita stabilă pe trei rulări consecutive.
- **F2.6 — Planificatorul de timp.**
  - Construit: `programare.py` (recurente declarate în cod și aplicate la pornire, sloturi prin `trimite(la=…)`), `AMA_PROGRAMARE_POLLING_SEC`.
  - „La minut” dovedit fără să aștept un minut: cron cu secunde în timp real (ticuri consecutive, o dată fiecare), `recupereaza_ratate` pe ferestre alese de test (12:05, 12:10 … la secunda 0; ora României peste 25 octombrie 2026: 06:00, 07:00, 07:00 UTC) și SIGKILL cu recuperarea golului.
  - Găsit: biblioteca nu are ceas injectabil și pune rulările programate pe prioritatea 0 (deci fluxurile programate trebuie să fie dispeceri mici); aplicarea repetată a programărilor păstrează pauza și ultima rulare (verificat în cod și în test).
  - Neverificat: un minut întreg pe staging, doi workeri (trecut la „De verificat la migrare”).
- **F2.7 — Watchdog și coada de erori.**
  - Construit: `semnale.py` (bătăi de inimă, căderi), `coada_erori.py` (context, cauză, triere, decizii cu audit), `watchdog.py` (firul din worker), `motor/inspectie.py` (joburi eșuate, pași, reluare), migrarea `0006`, ecranul Alerte, permisiunea `alerte.gestioneaza`, `python -m app.worker --verifica` ca healthcheck.
  - Verificat cu procese reale: SIGKILL în pasul 2 + supervizor (simulează `restart`) → jobul se termină exact o dată; un job care face `os._exit` strică workerul de două ori, apoi ajunge `epuizat`, intră în coadă ca major și repornirile se anunță o dată.
  - Găsit: `resume` nu reia un job `ERROR` (deci „reia” = bifurcare de la pasul eșuat); anularea scoate jobul din coadă (coada se păstrează acum în atributele jobului); pasul eșuat apare în listă doar dacă se încarcă și rezultatele pașilor; un pas sincron blocat nu poate fi oprit (doar anulat la hotar).
  - Un test al meu a picat în suita completă și nu izolat (număra evenimente din jurnal rămase de la alte teste); reparat cu filtru pe identificatorul jobului. Neverificat: politica de restart a Docker-ului, notificările reale, doi workeri.

### 16. Pașii F2.3, F2.4, F2.8, F2.10 — un agent de cod (Sonnet), pe ramura `claude/amazing-volta-ou9t2u`
- Alți pași din F2 (F2.5, F2.9) nu au fost atinși, conform cererii. Un commit pe pas, `make check` verde înainte de fiecare.
- **F2.3 — Mașina de stări a livrabilului.**
  - Construit: `app/productie/` (`stari` – tabelul ca date, `modele`, `tranzitii` – `muta`/`creeaza`/`versiune_noua`, `anunturi`), migrarea `0007` (tabelele `livrabile` și `livrabile_tranzitii`, funcția și declanșatorul de gardă), garda de cod `tests/unit/test_garda_livrabil.py`.
  - Găsit: refuzul trebuie scris într-o tranzacție separată ca să supraviețuiască rollback-ului apelantului, iar rândul livrabilului trebuie blocat cu `FOR NO KEY UPDATE` (nu `FOR UPDATE`): istoricul are cheie străină spre el și tranzacția separată ar aștepta la nesfârșit tranzacția apelantului. Declanșatorul din bază cere marcajul `app.muta_livrabil`, care trebuie pus înaintea modificării (o interogare face autoflush și ar trimite UPDATE-ul fără marcaj). Cheia `cod` este interzisă în jurnalul de evenimente (părți interzise ca la secrete): am numit-o `felul`.
  - Verificat: 484 de perechi de stări (permisă sau nu) față de un tabel scris a doua oară în test; refuz înregistrat și rămas după rollback; baza refuză UPDATE-ul direct, perechea nepermisă și inserarea într-o stare avansată; funcția din bază = tabelul din cod; două mutări simultane (două conexiuni) → una singură reușește.
