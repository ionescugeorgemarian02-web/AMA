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
- **F2.4 — Limite anti-buclă.**
  - Construit: `limite` (nucleu pur), contoarele și escaladarea în `muta`, `bugete`, `intrerupator`, `fluxuri` (jobul `productie.tic` la minut), `coada_erori.inregistreaza_escaladare`, `Oprire.PRODUCTIE`, migrarea `0008`, ecranul Alerte cu diagnostic, flux de probă SIMULAT în `tests/`.
  - Hotărâri: „predare” = intrarea într-o stare de lucru (altfel un drum normal depășește 12 mutări); eșec = intrare în coada de erori, succes = `validat`; oprirea producției se pune prin `opriri` (extins minim: tip `productie`, canal `sistem`), nu printr-un tabel nou; fereastra întrerupătorului începe de la repornirea de om, ca să nu se redeclanșeze pe rezultate vechi.
  - Găsit: istoricul tranzițiilor e doar-adăugare pentru aplicație, deci testele întrerupătorului îl golesc ca superutilizator (cu declanșatoarele oprite) fiindcă numără rezultatele tuturor clienților; cheia `cod` e interzisă și în detaliile unei intrări de audit (am evitat-o).
  - Verificat: pragurile exacte (strict peste), un livrabil de probă care eșuează mereu se oprește la a treia rundă (două reparații permise) și apare în Alerte cu diagnostic; escaladarea se anulează cu tranzacția apelantului; producția oprită nu pornește livrabile noi, dar nu oprește ce e în lucru.
- **F2.8 — Cererile de aprobare.**
  - Construit: `reguli_aprobare` (nucleu pur), `aprobari_baza` + `aprobari` (serviciul), poarta cu `Temei` în `muta`, migrarea `0009`, jobul `productie.tic` extins (expirare + reamintiri), `app/panou/aprobari_web.py` cu șablonul `aprobari.html`.
  - Hotărâri: o cerere nouă pentru versiunea nouă preia decidentul și termenul (editarea nu prelungește termenul), ca invariantul „așteaptă aprobare ⇒ cerere în așteptare pentru versiunea curentă” să nu se rupă; starea `anulat` pentru cererea înlocuită (peste cele patru cerute); ordinea de blocare livrabil → cerere peste tot, ca expirarea și decizia simultane să nu se blocheze reciproc; o decizie după termen expiră cererea în loc să o aprobe.
  - Schimbat într-un test existent (justificat): `test_panou` verifica starea goală „Încă nimic aici” pentru `/aprobari`; ecranul are acum conținut, deci testul rămâne pentru `/productie`, iar `/aprobari` are testul lui de stare goală. Testul de drum al unui text (F2.3) trece acum prin cerere și decizie, fiindcă poarta cere temei.
  - Verificat: expirarea (cerere și livrabil `expirat`, niciodată `aprobat` / `programat` / `publicat`), decizia legată de versiune, poarta fără temei, două decizii simultane (una singură), expirare și decizie simultane, un video prin toate cele 16 stări, panoul cu CSRF, rol și audit.
- **F2.10 — Nivelurile de autonomie.**
  - Construit: `reguli_autonomie` (matricea ca date + decizia pură), `autonomie` (stocare, schimbare, retrogradare, `decide`), migrarea `0010` (`autonomie_niveluri`, `autonomie_istoric`), permisiunea `autonomie.seteaza`, porțile din `muta` (L0 și temeiul de autonomie), `NivelUmbra` în aprobări, fluxul de probă extins (parcat / aprobare / automat).
  - Hotărâri: poarta recalculează decizia (nu crede un temei de autonomie pe cuvânt), deci o retrogradare are efect imediat și pe livrabilele deja `validate`; eșantionul se alege din SHA-256(clasă + id), nu dintr-un zar, ca testul să poată alege un livrabil „din eșantion” sau nu și să dea același răspuns la fiecare apel; lista canalelor cu consimțământ e configurare (`AMA_CANALE_CONSIMTAMANT`); nu am adăugat câmpuri pentru promovarea automată (istoricul și cererile de aprobare au deja ce trebuie).
  - Verificat: „același livrabil de probă cere aprobare la L1 și trece singur la L2” cap-coadă pe motorul durabil; matricea de 25 de celule, TikTok la L1, L0 care nu publică, retrogradarea, doar proprietarul schimbă nivelul, izolarea pe client.
- **Rezultat general F2.3, F2.4, F2.8, F2.10:** `make check` verde, 1304 de teste (1087 la F2.3) în 155 s. Specificațiile sunt `docs/specs/F2.3.md`, `F2.4.md`, `F2.8.md`, `F2.10.md`; starea pașilor, în `docs/specs/STARE.md`. Neverificat și simulat: fluxul de probă (`# SIMULAT:` în `tests/integration/fluxuri_livrabil.py`), livrarea reală a notificărilor, minutul întreg al jobului `productie.tic` pe staging, pragurile (valori de pornire).
- Propuneri notate, nefăcute: ecranul de setare a nivelurilor de autonomie (acum doar API de serviciu); calibrarea pragurilor pe date reale; reluarea unui livrabil oprit la limită din ecranul Producție (F2.9, peste `productie.reia_de_om`); un observator extern care să repornească întrerupătorul doar cu confirmare în Telegram (acum doar panoul și comanda `/porneste productie`).

## 2026-11-12 — Sesiunea 3: închiderea fazei F2 (F2.5, F2.9, poarta F2)

### 17. Pașii F2.5, F2.9 și poarta F2 — un agent de cod (Sonnet), pe ramura `claude/amazing-volta-ou9t2u`
- Un commit pe pas, `make check` verde înainte de fiecare.
- **F2.5 — Executorul de efecte externe.**
  - Construit: `app/operare/efecte/` (stări ca date, modele, servicii, executor), `app/connectors/contract.py` și `registru.py`, migrarea `0011` (`efecte_de_trimis`, `conectori_pauze`), garda `scripts/check_efecte.py`, conectorul fals `tests/conector_fals.py` (SIMULAT, „platforma” în fișiere ca să supraviețuiască unui proces omorât). Fluxul de probă al livrabilului cere acum efectul de publicare în loc să sară direct în `publicat`.
  - Hotărâri: notarea `în trimitere` se face într-o tranzacție separată, înainte de conector (altfel un SIGKILL ar șterge urma încercării și `verifica` n-ar mai fi cerut); „verifică întâi” se decide după numărul de încercări (> 0), nu după stare, ca să rămână adevărat și după o reluare de om; o singură încercare odată pe efect, prin încuietoare de sesiune în Postgres (dispare când procesul moare); un efect `în trimitere` nu se anulează de om; reîncercările temporare sunt ale pasului durabil (pauză crescătoare), iar la epuizare se face o ultimă `verifica`.
  - Găsit: la epuizarea reîncercărilor biblioteca aruncă propria excepție (`DBOSMaxStepRetriesExceeded`), pe care aplicația nu are voie s-o importe; fluxul prinde deci `Exception` și trece la pasul de epuizare. Jurnalul de audit refuză cheile cu „cod”/„cheie” (am folosit `tip_eroare`, `idem`) și acceptă doar rezultatele `ok`/`esec`/`refuzat`.
  - Verificat: același efect de două ori = o postare; conector care postează apoi dă eroare = fără retrimitere; SIGKILL înainte de trimitere și după înregistrarea la „platformă” = exact o postare; oprire globală și pe client; anulare dacă nu mai e valabil; autentificare = pauză fără pierdere; baza refuză tranziții nepermise; izolare pe client.
- **F2.9 — Ecranele Producție și Operare.**
  - Construit: `app/panou/productie_web.py` (listă, urmă, reia, anulează), `app/panou/motor_web.py` (Operare, motorul), șabloanele `productie`, `livrabil`, `operare_motor`, `_motor_stare`; `motor.joburi_pentru`, `motor.adancime_cozi`; diagnostic pentru efectele eșuate în ecranul Alerte.
  - Hotărâri: legătura livrabil → job se face după identificatorul din argumentele jobului (fluxurile primesc doar identificatori), cu verificarea că jobul de reluat aparține livrabilului vizibil, fiindcă tabelele motorului nu au RLS; „reia pasul” nu se mai oferă pentru un job care are deja un urmaș (reluarea unui job eșuat face o bifurcare, iar originalul rămâne `eșuat`); acțiunile pe programări și pe conectori sunt ale proprietarului, citirea e a oricărui rol de agenție; motorul stă la `/operare/motor`, nu peste `/operare` (care rămâne doar al proprietarului: livrare și backup).
  - Schimbat în teste existente (justificat): `test_panou` (`/productie` nu mai e stare goală; meniul operatorului are acum și legătura spre motor; textul de pe Acasă spune că publicarea e citită) și `test_productie_limite` (audit-ul `livrabil.reluat_de_om` e filtrat pe livrabilul testului, fiindcă baza de test e comună și alte teste reiau acum livrabile). Nicio aserțiune slăbită.
- **Poarta F2.**
  - Construit: `tests/chaos/test_poarta_f2.py` (cap-coadă: workeri reali, Postgres real) și un punct de oprire pentru teste în fluxul de probă (`_blocaj`, activ doar cu `AMA_PROBA_DIR` și un fișier `blocheaza.<stare>`).
  - Verificat: un video de probă (cu o rundă de reparație, deci toate cele 16 stări normale) merge de la `planificat` la `inchis`; workerul e omorât în `in_randare` și apoi după ce conectorul fals a înregistrat postarea; după repornire, exact o postare la „platformă”, o singură trimitere și o verificare, istoric exact cele 17 mutări așteptate, fără refuzuri. Rulat de patru ori la rând, stabil (~7 s).
  - Notat în `docs/specs/STARE.md` ca trecută local; validarea proprietarului la poartă rămâne a lui.
- **Rezultat general F2.5, F2.9, poarta F2:** `make check` verde. Neverificat și simulat: conectorul (FALS), fluxul de probă, ecranele pe un telefon real, canalele reale de notificare, doi workeri pe aceeași bază.
- Propuneri notate, nefăcute: reluarea automată a fluxului unui livrabil după `reia_de_om` (acum se reia starea, nu componenta); o legătură explicită livrabil → job în loc de potrivirea pe argumente; ecranul de setare a nivelurilor de autonomie; mutarea livrabilului în `esec_temporar` în timpul reîncercărilor efectului (acum rămâne în `in_publicare`).

## 2026-11-12 — Sesiunea 4: faza F3, gateway de modele (F3.1, F3.2, F3.3, F3.4, F3.7)

### 18. Pașii F3.1–F3.4 și F3.7 — un agent de cod (Sonnet), pe ramura `claude/amazing-volta-ou9t2u`
- F3.5, F3.6, F3.8–F3.11 nu au fost atinse, conform cererii. Un commit pe pas, `make check` verde înainte de fiecare.
- **F3.1 — Registrul de furnizori și modele.**
  - Construit: `app/gateway/` (`inventar`, `modele`, `registru`, `erori`), migrarea `0012` (tabelele și sămânța), ecranul `/gateway/registru`.
  - Hotărâri: cheile NU stau în bază, nici criptate: doar numele variabilei de mediu `AMA_CHEIE_*` (8.1 și 21.2 le vor în mediul serverului; baza refuză orice alt nume, deci gateway-ul nu poate fi îndreptat spre `AMA_MASTER_KEY`); registrul e la nivel de agenție dar citibil din orice context cu identitate, fiindcă lucrătorii deschid sesiuni de client; „uz comercial” se impune în bază (`CHECK`), nu doar în cod; sămânța pornește totul `inactiv`.
  - Găsit: RLS este FORȚAT și pentru proprietarul migrării, deci sămânța trebuie scrisă cu `app.agency` setat în tranzacția migrării.
  - Neverificat: toate valorile `[I]` din inventar (termeni, limite, identificatori de modele) sunt presupuneri.
- **F3.2 — Clientul unificat.**
  - Construit: `adaptoare/` (`openai_compat`, `gemini`, `anthropic`), `client`, `iesire`, `structurat`, `antete`, `tipuri`, `ceas`, garda `scripts/check_gateway.py`, furnizorul fals `tests/furnizor_fals.py`.
  - Hotărâri: adaptor pe TIP de API, nu pe furnizor (OpenRouter, Groq și Cloudflare diferă prin date: adresă cu parametri, capabilități); Anthropic cere ieșirea structurată printr-o unealtă forțată; cheia Gemini merge în antet, nu în adresă (adresele ajung în jurnale); mesajul de eroare al furnizorului nu se păstrează niciodată (poate repeta promptul); `IesireInvalida` nu poartă conținutul răspunsului, fiindcă o excepție dintr-un pas durabil ajunge în tabelele motorului, fără RLS.
  - Găsit: garda trebuie să prindă și `from app.gateway import client` (submodul importat prin pachet) și `gateway.client` ca atribut; lista submodulelor „interne” se deduce din ce nu e în `__all__`.
  - Neverificat: formele cererilor / răspunsurilor sunt după documentațiile publice, din memorie; nimic nu a ajuns la un furnizor real.
- **F3.3 — Limitatoarele de cotă.**
  - Construit: `cote` (nucleu pur), `limitator`, `candidat`, `amanare`, `apel` (piesa `incearca_model`: rezervare → cerere → regularizare), migrarea `0013`, `registru.candidati`.
  - Hotărâri: rezervarea este o singură instrucțiune `INSERT … ON CONFLICT DO UPDATE … WHERE` pe contor, nu „citește apoi scrie”; limitatorul lucrează în tranzacții proprii (sesiune de agenție), ca rezervarea să rămână și dacă apelantul face rollback; contoarele sunt pe model SAU pe contul furnizorului (OpenRouter limitează pe cont); amânarea o face FLUXUL apelant (își reprogramează munca din identificatori), nu gateway-ul, care ar fi trebuit să rețină promptul în tabelele motorului, fără RLS; momentul reluării se calculează pe ceasul gateway-ului și se aplică ceasului real (altfel testul cu ceas deplasat ar fi așteptat o oră).
  - Găsit: la timeout nu știm ce a consumat furnizorul, deci rezervarea rămâne; antetele nu coboară niciodată un contor (numărătoarea noastră poate include cereri în zbor); marja de o secundă se aplică la citirea blocajului, nu la scriere (altfel se adună de două ori).
  - Neverificat: doi workeri ca procese separate (testat cu 24 de fire și conexiuni proprii), antetele reale.
- **F3.4 — Rutarea și lanțurile de rezervă.**
  - Construit: `profiluri` (date), `rutare` (nucleu pur), `intrerupator` (nucleu pur) și `sanatate` (starea în bază), `interceptori`, `apel` (traseul unui apel: model cu model, reacțiile din 7.5), migrarea `0014`, setări `AMA_GATEWAY_*`.
  - Hotărâri: profilurile stau în bază (editabile din F3.10), nu în cod; intrările unui lanț sunt modele sau `nivel:X`, iar un model necunoscut se sare (modelul local apare în F3.5 fără să strice nimic); „nu are voie” (T4 pe calea critică, apeluri plătite oprite, client oprit) înseamnă `ApelRefuzat`, nu `Amanat`: ce a oprit un om sau o regulă nu se reia singur; fără niciun model eligibil se amână peste 5 minute (furnizorii pot fi activați între timp); fiecare cerere eșuată (nu fiecare apel) numără la întrerupător, ca o cădere să-l deschidă în primul apel; ieșirile în afara schemei nu numără la sănătatea furnizorului (țin de model); `T4` se exclude după nivelul MODELULUI, nu al profilului, ca un lanț mixt să poată trece pe un model mai mic.
  - Găsit: contextul de agenție folosit în `limitator` și `sanatate` cere intrare explicită în `tests/unit/test_garzi_db.py` (garda existentă a funcționat); rezultatul unui apel cu încercări eșuate trebuie să includă și tokenii încercărilor eșuate (s-au consumat).
  - Neverificat: pragurile (3 / 3 / 120 s) sunt valori de pornire; comportamentul real al furnizorilor la cădere.
- **F3.7 — Registrul de prompturi și jurnalul de apeluri.**
  - Construit: `prompturi` (registru, randare, fișiere), `jurnal` (scriere, citire, retenție), `serviciu` (`gateway.apeleaza`), `fluxuri` (curățarea zilnică), migrarea `0015`, ecranele `/gateway/apeluri` și `/gateway/apeluri/{id}`.
  - Hotărâri: conținutul (mesajele trimise după interceptori și răspunsul validat) stă într-un tabel SEPARAT de metadate, cu `tenant_id`, RLS și `expira_la` de 30 de zile, nu în tabelele motorului, nu în jurnalele aplicației; metadatele rămân; jurnalul se scrie într-o tranzacție proprie (rămâne și dacă apelantul face rollback) și un eșec de scriere nu pierde răspunsul; versiunea activă a unui prompt e înghețată de un declanșator, nu doar de cod; variabilele unui prompt se potrivesc exact (lipsă sau în plus = refuz) și se completează într-o singură trecere, ca un text din exterior să nu poată introduce alte locuri de șablon; un apel se numără în bugetul livrabilului dacă a ajuns la cel puțin un furnizor, inclusiv când a eșuat; livrabilul de altă firmă și sesiunea altui client sunt refuzate înainte de orice apel; promptul și schema sunt legate (numele clasei), ca un apel să nu ceară alt format decât cel pentru care a fost scris promptul.
  - Găsit: `jurnal` trebuie exportat de pachet ca panoul să-l poată folosi fără să încalce garda; ștergerea zilnică folosește scop de agenție (încă o intrare în `test_garzi_db`).
  - Neverificat: nicio dată personală nu e mascată până la F3.9; retenția a fost verificată cu ceas controlat; nu există încă niciun prompt real în `prompts/`.
- **Rezultat general F3.1–F3.4 și F3.7:** vezi raportul. Specificațiile sunt `docs/specs/F3.1.md`, `F3.2.md`, `F3.3.md`, `F3.4.md`, `F3.7.md`; starea pașilor în `docs/specs/STARE.md`.
- Propuneri notate, nefăcute: coada pe furnizor din motor (`coada_furnizor`) nu e legată, fiindcă gateway-ul nu știe furnizorul înainte de rutare; alertă când un profil rămâne fără niciun furnizor (acum se amână cu 5 minute, fără alertă); ecran de editare a termenilor, limitelor și profilurilor (F3.10); `inregistreaza_consum` poate primi `diagnostic` cu modelul și profilul, pentru ecranul de producție.

## 2026-11-12 — Sesiunea 5: închiderea fazei F3 (F3.8, F3.9, F3.5, F3.6, F3.10, F3.11, poarta F3)

### 19. Pașii F3.8, F3.9, F3.5, F3.6, F3.10, F3.11 și poarta F3 — un agent de cod (Sonnet), pe ramura `claude/amazing-volta-ou9t2u`
- Un commit pe pas, `make check` verde înainte de fiecare.
- **F3.8 — Bugete și priorități.**
  - Construit: `bugete` (consum, interceptor, editare), `reguli_buget` (nucleu pur), migrarea `0016` (`gateway_bugete_implicite`, `gateway_bugete_client`, `gateway_consum_client`), `docs/specs/F3.8.md`, D-004.
  - Hotărâri: consumul stă în contoare proprii, nu în jurnal (jurnalul se scrie după apel, într-o tranzacție separată: două apeluri simultane ar fi citit același total); apelul se rezervă atomic pe zi și pe lună în aceeași tranzacție, iar tokenii și prețul-umbră se adaugă după apel; apelul care nu a ajuns la niciun furnizor eliberează rezervarea; P1 continuă până la 1,5 × buget (8.5 nu spune cât), P0 niciodată oprit; „avertizat” este o coloană setată atomic, ca notificarea să plece o singură dată.
  - Verificat: client de test peste buget: P2 și P3 amânate (cu momentul resetării zilei / lunii), P1 la plafonul lui, P0 trece; 24 de fire pe un buget de 10 → exact 10 apeluri; cota furnizorului nu consumă din bugetul clientului; izolare pe client.
  - Neverificat: valorile implicite (de pornire), notificarea pe canale reale, doi workeri.
- **F3.9 — Garda de date personale și garda de injecții.**
  - Construit: `mascare`, `extern`, `injectii`, `garda` (interceptorii cu ordinea 5 și 10), `date_confidentiale` / `mascheaza_cui` / `demasca` pe `gateway.apeleaza`, `gateway.marcheaza_extern`, migrarea `0017` (`semnale`), două colecții sintetice în `tests/fixtures/gateway/`, `docs/specs/F3.9.md`.
  - Hotărâri: CUI doar la cerere (e dată de firmă, nu de persoană); marcajele sunt stabile pe apel, iar un text care imită un marcaj i se schimbă parantezele ca demascarea să nu poată scoate valori; răspunsul se salvează mascat, păstrând marcajele pe care le-am pus noi; semnalele din jurnal poartă tipuri și numere, niciodată valori sau text; injecția dă semnal, nu blocare (textul a intrat oricum ca date); fără niciun model permis pentru date confidențiale, apelul este refuzat (așteptarea nu rezolvă), nu amânat; garda `check_gateway` interzice `eval` / `exec` / `subprocess` în gateway (ieșirea unui model nu se execută).
  - Găsit: regexul de IPv4 nu trebuie să respingă un punct de final de propoziție; demascarea unei valori repetate cu alte majuscule întoarce prima formă întâlnită.
  - Verificat: toate elementele colecției de date sunt mascate (nimic la furnizorul fals, nimic în conținutul stocat); pentru fiecare dintre cele 18 atacuri: un singur bloc, instrucțiunea în sistem, delimitatorii nu pot fi rupți, ieșirea în afara schemei respinsă după o reparație.
  - NEVERIFICAT: eficacitatea pe modele reale; euristica nu prinde parafraze, alte limbi, codificări.
- **F3.5 — Modelul local și modelul de embeddings.**
  - Construit: `adaptoare/local`, `vectori`, `masurare`, `inventar_local`, migrarea `0018`, `motor.coada_curenta`, `Motiv.LOCAL_COADA` / `MODEL_DE_VECTORI` în rutare, `model=` pe `gateway.apeleaza`, serviciile `local-llm` și `embeddings` în compose, `tests/server_local_fals.py`, `docs/specs/F3.5.md`.
  - Hotărâri: embeddings pe server separat (imaginea aplicației nu poartă biblioteci de inferență) în loc de „încărcat în worker-light”; modelul local doar din joburi `greu`, cu refuz (nu amânare) în afara lor, ca greșeala de proiectare să fie vizibilă; cheia nu se trimite spre serverul intern; compose-ul în profil, fără digest (altfel livrarea ar încerca să tragă o imagine inexistentă); `http://` permis în registru doar spre nume de serviciu intern; textele de vectori nu se păstrează în jurnal.
  - Găsit: registrul nu are politică de DELETE, deci `downgrade` a migrării șterge sămânța cu RLS oprit doar în migrare; fabrica de teste nu curăța furnizorii cu cod ales explicit (reparat); un test cu socket real trebuie să dezactiveze transportul simulat.
  - Verificat: clasificare prin adaptorul local pe coada `greu`, refuz pe `io` și în afara jobului, viteze notate în registru pentru trei mărimi, vector calculat cu culoarele grele ocupate, dimensiunea verificată, server căzut → `Amanat`.
  - NEVERIFICAT: orice model real, memoria, viteza pe procesorul real, steagurile și digestul imaginii.
