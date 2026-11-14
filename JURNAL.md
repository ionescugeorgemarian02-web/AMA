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
- **F3.6 — Testul comparativ pe română.**
  - Construit: `criterii`, `evaluare`, setul `evaluare/sarcini/` (72) și `evaluare/prompturi/` (6), migrarea `0019`, fluxurile `gateway.evaluare` / `gateway.evaluare_lunara`, `docs/specs/F3.6.md`.
  - Hotărâri: un model pe rulare prin `gateway.apeleaza(model=…)` (lanțul profilului nu contează la evaluare, nici nivelul minim); apelurile de evaluare se scriu pentru un client intern cu buget propriu, ca jurnalul (care cere client) să rămână uniform; sarcinile și rezultatele sunt la nivel de agenție (date sintetice); ieșirea în afara schemei înseamnă scor 0, nu rulare eșuată; amânarea oprește rularea și o reia fără refacere; modelul local se evaluează pe coada `greu` (regula din F3.5).
  - Găsit: auditul refuză chei cu „token”, deci `bugete.seteaza_client` cu `tokeni_zi` ar fi picat (nepăzit de testele F3.8): cheile apar acum ca „jetoane”, cu test; fabrica de teste trebuia să curețe și rulările de evaluare.
  - Verificat: vezi spec; scoruri 1,0 / mediu / slab pe toate profilurile; rutarea alege modelul bun.
  - NEVERIFICAT: orice model real; evaluarea umană.
- **F3.10 — Ecranul „Modele și cote”.**
  - Construit: `situatie` (cote), `registru.seteaza_limite` / `seteaza_termeni`, `evaluare.porneste`, rute și șablon extinse în `gateway_web.py` / `gateway_registru.html`, `docs/specs/F3.10.md`.
  - Hotărâri: s-a extins ecranul existent (același URL, aceeași pagină), nu s-a adăugat altul; formularele de editare stau în `<details>`, ca pagina să rămână citibilă pe telefon; un furnizor activ nu poate pierde uzul comercial (se dezactivează întâi); cheile cu „token” apar ca „jetoane” în audit; editarea este doar a proprietarului, citirea a oricărui rol de agenție.
  - Găsit: numele clienților de probă (prefix de UUID de timp) se pot repeta, deci un test nu poate identifica un client după nume.
  - Verificat: vezi spec. NEVERIFICAT: aspectul pe telefon.
- **F3.11 — Planificatorul de capacitate (A4).**
  - Construit: `app/planificare` (`reguli` pur, `capacitate`, `costuri`, `fluxuri`), `gateway.situatie.capacitate_profil`, `productie.amana` / `elibereaza`, condiția `nu_inainte_de` în `muta`, migrarea `0020`, joburile zilnic și la cerere, `docs/specs/F3.11.md`.
  - Hotărâri: „amânat” = un câmp `nu_inainte_de` verificat de `muta` la `planificat → briefat` (efect real, fără să ocolească mașina de stări); se amână doar ce ajută o axă depășită, termenul cel mai îndepărtat întâi; P0 și termenele sub 48 de ore nu se ating, iar dacă ele singure depășesc capacitatea, alerta o spune; capacitatea ignoră degradarea la modelul local (prudent) și modelele inutilizabile acum; fără data de început a unui livrabil (F6), toate cele planificate din orizontul de 14 zile sunt muncă de pornit; rularea repetată e sigură (ce e amânat iese din planul de azi).
  - Găsit: un test al planificatorului vede livrabilele rămase de la alte teste (baza e comună), deci planul se poate restrânge la clienți (`clienti=`); fără cheia furnizorului în mediu un model nu contează în capacitate (la fel ca în rutare).
  - Verificat: vezi spec. NEVERIFICAT: costurile, pragurile, rularea la ora ei, alerta pe canale reale.
- **Poarta F3.**
  - Construit: `tests/integration/test_poarta_f3.py` și `tests/integration/fluxuri_poarta_f3.py` (flux de probă care mută pasul pe `greu` la `local_doar_pe_coada_greu` și se reprogramează la `Amanat`).
  - Verificat: pe cele cinci scenarii de cădere (plus unul fără cădere), toate cele șase profiluri se termină; strategia și consiliul se amână curat; clasificarea și rescrierea degradează la local; auditul (`dbos.workflow_status`) nu arată niciun flux eșuat, iar jurnalul de apeluri niciun `esec`. Rulat de trei ori la rând, stabil (~9 s).
  - Notat în `docs/specs/STARE.md` ca trecută local doar pentru partea verificabilă; „testul comparativ rulat pe modele reale” rămâne deschis.
- **Rezultat general F3.8, F3.9, F3.5, F3.6, F3.10, F3.11 și poarta F3:** `make check` verde la fiecare pas (1640 → 1803 de teste, ~200 s). Neverificat și simulat: orice model real, memoria și viteza modelului local, eficacitatea gărzii de injecții pe modele reale, ecranul pe telefon, costurile și pragurile (valori de pornire), canalele reale de alertă. Un test vechi (`tests/chaos/test_programare.py`, ticuri de un secund cu SIGKILL) a picat sporadic în execuția completă sub încărcare (de 3 ori din 7) și trece izolat; nu atinge codul acestei sesiuni, dar merită stabilizat.
- Propuneri notate, nefăcute: ecran pentru profiluri și lanțuri (acum date fără interfață); ecranul planului de capacitate; recalibrarea costurilor din jurnalul de apeluri; calendarul de postări cu date de început (F6) pentru planificator; mascarea numelor proprii cu modelul local; stabilizarea testului de programare sub încărcare.

### Revizuire la închiderea F3 (orchestrator)

- Am rulat integral `make check` pe ramura F3: 1805 teste trec.
- Testul `tests/chaos/test_programare.py` cădea sub încărcare (reprodus cu procesorul ocupat: 4 din 5 rulări). Cauze, ambele în test, nu în planificator: (1) ticul aflat în lucru la SIGKILL își scrisese urma, dar nu fusese notat ca terminat, deci pasul se reia („cel puțin o dată” la cădere) și apare de două ori în fișierul de probă; (2) ticurile recuperate rulează în paralel, iar testul citea fișierul înainte să se așeze toate. Testul așteaptă acum șirul fără goluri și acceptă o dublură doar pentru ticul aflat în lucru la cădere. Verificat: 6 rulări la rând sub încărcare, fără eșec.
- De reținut pentru fazele următoare: un pas cu efect în afara bazei trebuie să fie idempotent (executorul de efecte din F2.5 respectă deja regula prin „verifică înainte de reîncercare”).

## 2026-11-12 — Sesiunea 6: faza F4, Creierul de brand (F4.1, F4.2, F4.3, F4.6, F4.7)

### 20. Pașii F4.1, F4.2, F4.3, F4.6, F4.7 — un agent de cod (Sonnet), pe ramura `claude/amazing-volta-ou9t2u`
- Un commit pe pas, `make check` verde înainte de fiecare. F4.4, F4.5, F4.8–F4.11 rămân pentru agenții următori.
- **F4.1 — Modelul Creierului.**
  - Construit: `app/creier` (`compartimente`, `diferenta`, `modele`, `versiuni`), migrarea `0021`, `docs/specs/F4.1.md`.
  - Hotărâri: un singur depozit versionat pentru toate compartimentele (intrări + versiuni), cu scheme Pydantic înregistrate per compartiment, în loc de un tabel per compartiment; „retras” acoperă și respingerea / înlocuirea / expirarea, distinse prin `retras_cauza`; imutabilitatea e un declanșator în bază (și proprietarul e refuzat), nu o convenție; aplicația nu are UPDATE pe `creier_intrari`, deci serializarea schimbărilor folosește un lacăt consultativ pe tranzacție, nu `FOR UPDATE`; nivelurile `nisa` / `platforma` sunt rânduri fără client, citibile de orice context autentificat.
  - Găsit: auditul refuză chei care conțin „cod”, „hash”, „cheie”, „key”, deci detaliile folosesc `compartiment`, `versiune`, `intrare`.
  - Verificat: vezi spec. NEVERIFICAT: nimic simulat.
- **F4.2 — Colectorul de surse.**
  - Construit: `app/cercetare` (`ssrf`, `robots`, `url_utile`, `html_text`, `descarcator`, `statut`, `stocare`, `colectare`, `fluxuri`, `modele`), migrarea `0022`, `docs/specs/F4.2.md`, site fals pe socket local (`tests/site_fals.py`) și materialele brandului fictiv „Cafeneaua Zorilor” (`tests/materiale_zorilor.py`).
  - Hotărâri: descărcarea de pagini e o citire și stă în `app/cercetare`, nu în `app/connectors` (garda efectelor rămâne neschimbată, cu test); extragerea cu `html.parser` (fără dependență nouă); conexiune la adresa verificată cu `Host` și SNI ale gazdei (fără a doua rezolvare), `trust_env=False`; `robots.txt` cu parser propriu (stdlib nu cunoaște `*` și `$`); frontiera colectării e un tabel, nu memorie, iar contoarele se recalculează din pagini; excepția SSRF pentru serverul local fals există doar sub `AMA_ENV=test`.
  - Găsit: `httpx.Client` păstrează cookie-urile primite (se golesc după fiecare răspuns); normalizarea unei adrese scoate numele și parola, deci adresa brută se validează înainte; User-Agent-ul trebuie să fie ASCII (setarea o impune); numele unui modul nu poate fi și numele unei funcții exportate din pachet (`colectare`); un test vechi (`test_gateway_ecran`) identifica clientul după nume, iar numele din teste se repetă ~4,6 minute (pasul F4.1 l-a întărit).
  - Verificat: vezi spec. NEVERIFICAT: orice site real; DNS / TLS reale; pagini cu JavaScript.
- **F4.3 — Vectori și căutare hibridă.**
  - Construit: `app/creier` (`pasaje`, `indexare`, `cautare`, `fluxuri`), migrarea `0023`, `gateway.vectorizeaza_cu_model` / `model_vectori`, vectorizatorul fals (`tests/vectorizator_fals.py`), setul de 27 de întrebări, `docs/specs/F4.3.md`.
  - Hotărâri: text fără diacritice cu configurația `simple` (dicționarul `romanian` stemuiește pe diacritice, iar materialele le amestecă); trei canale cu RRF; fără index vectorial aproximativ (ar tăia rezultatele după filtrul pe client); modelul vectorului se ia din același apel care l-a produs (nu dintr-o citire separată a registrului); indexarea după colectare se activează explicit de worker, nu la import (un abonat global ar fi pornit joburi în testele altor module).
  - Găsit: o întrebare cu sinonime („transportul” față de „livrarea”) depășește un sac de cuvinte, așa că întrebările de probă sunt formulate în lexicul materialelor; calitatea reală rămâne de măsurat.
  - Verificat: vezi spec. NEVERIFICAT: modelul real, prefixele lui, timpul la volum mare.
- **F4.6 — Registrul de fapte și catalogul de oferte.**
  - Construit: `app/creier` (`citat`, `fapte`, `oferte`, `extragere`, fluxurile de extragere și de expirare), `app/panou/creier_web.py` + șablon, `prompts/creier.extrage_fapte.v1.md`, migrarea `0024`, `docs/specs/F4.6.md`.
  - Hotărâri: faptele și ofertele sunt intrări ale depozitului versionat (nu tabele noi), deci sursa obligatorie și audit vin din F4.1; „respins” și „expirat” sunt cauze de retragere; `pentru_context` citește „la o dată” (aprobat până atunci, neretras, în valabilitate), nu doar „acum”; o ofertă intră în context doar cu toate faptele legate valabile; extragerea propune dar nu aprobă niciodată; citatul se verifică literal și la propunerea unui om; `demasca=True` ca citatele cu emailuri și telefoane să se potrivească literal; modelul local cere coada `greu`, deci fluxul se mută acolo.
  - Găsit: numărul de telefon inventat avea 11 cifre și nu era mascat de garda din F3.9 (corectat, 10 cifre); `COPY prompts` lipsea din imagine (adăugat; `evaluare/` are aceeași lipsă, notată ca propunere); în schema de ieșire un câmp numit `fapte` ascunde modulul `fapte` — s-au păstrat nume distincte.
  - Verificat: vezi spec. NEVERIFICAT: orice model real; ora jobului; notificarea pe canale reale.
- **F4.6 — închidere (agent de preluare).** Ultimul `make check` al autorului precedent dădea „2040 passed, 3 errors”: cele trei erori erau la *setup* în `tests/isolation/test_creier_rls.py` (F4.1), a cărui fixtură crea o intrare `registru_fapte` cu conținutul `{"afirmatie": "a"}`; F4.6 a înregistrat schema `ContinutFapt` (tip, subiect, afirmație de minimum 5 caractere), deci `valideaza_continut` o respingea. Reparat în test (conținut valid, aceleași aserțiuni de izolare), nu în cod. Rezultat: `make check` 2043 teste trecute.
- **`COPY evaluare` în Dockerfile** (commit separat): `app/gateway/evaluare.py` citește `evaluare/sarcini` și `evaluare/prompturi` la rulare, iar directorul lipsea din imagine.
- **F4.7 — Constructorul de context.**
  - Construit: `app/creier` (`buget`, `citire`, `pachete`, `context`), migrarea `0025` (`pachete_context`), secțiunea „Pachetul de context” pe `/productie/{id}`, `docs/specs/F4.7.md`. Pornit de la o ciornă nerulată a autorului precedent; revizuită critic.
  - Schimbat față de ciornă: (1) obligatoriile se rezervă primele, indiferent de poziția secțiunii; (2) `citire.pentru_context` refuză registrul de fapte și oferte (nicio a doua cale spre fapte) și citește și constrângerile de nivel platformă; (3) relevanța pe tulpini ușoare, faptele ofertelor alese intră prin ele, `fapte_relevante` în `lipsuri` când nu se potrivește niciunul; (4) pasajele se taie la 1200 de caractere înainte de buget, ca să se numere ce se trimite; (5) textul profilului randat cu etichete, nu concatenare de valori; (6) declanșator care refuză un pachet legat de livrabilul altui client; (7) testele rescrise cu aserțiuni exacte (ciorna avea `or True`), plus teste de izolare, de pasaj ostil, de buget și de „la o dată”.
  - Găsit: `Decimal("50").normalize()` se serializa „5E+1” (F4.6): ar fi trimis cifra greșită în prompt; corectat în `Valoare` cu test de regresie. Nivelurile de nișă / platformă primesc doar sursa „agregat”; nivelul platformei e comun întregii baze de test, deci testul care îl folosește îl retrage la final.
  - Verificat: vezi spec. NEVERIFICAT: vectori reali, calitatea relevanței lexicale, estimatorul de tokeni față de tokenizatori reali, consumul de către autori (F6).
  - Propuneri: nișa clientului (pentru constrângerile de nișă); legarea constructorului de primul pas al producției de text (F6.x); `ca_text` ar putea primi un plafon de caractere pe secțiune.

## 2026-11-12 — Sesiunea 7: închiderea fazei F4 (F4.4, F4.5, F4.9, F4.10, F4.11, F4.8, poarta F4)

### 21. Un agent de cod (Sonnet), pe ramura `claude/amazing-volta-ou9t2u`
- Un commit pe pas, `make check` verde înainte de fiecare. Poarta F4 propriu-zisă (CariereAI și BigBrain) rămâne a proprietarului.
- **F4.4 — Asistentul de onboarding.**
  - Construit: `app/onboarding` (`interviu`, `brief`, `clarificare`, `completare`, `sesiuni`, `fluxuri`, `modele`, `prompturi`), migrarea `0026`, două prompturi, ecranul `/onboarding`, `docs/specs/F4.4.md`, DECIZII D-005.
  - Hotărâri: poarta de aprobare e a COMPARTIMENTULUI (în `creier.versiuni`), nu a ecranului, ca niciun serviciu să nu poată ocoli completitudinea; trei compartimente noi în loc de tabele paralele; clarificarea cade pe șablonul din interviu dacă gateway-ul nu răspunde; câmpul respins de verificator cade pe răspunsul clientului, nu rămâne gol.
  - Găsit: auditul refuză cheia `cod`; cheia de idempotență a jobului trebuie să fie unică pe sesiune în teste; o valoare repetată „Nu știu” după clarificări trebuia tratată ca substitut.
  - NEVERIFICAT: orice model real.
- **F4.5 — Profilul de brand.**
  - Construit: `app/onboarding/ghid.py`, migrarea `0027`, promptul de ton, fluxul `onboarding.propune_ton`, ecranul ghidului, randarea ghidului în pachetul de context, `docs/specs/F4.5.md`.
  - Hotărâri: verificările unei variante sunt deterministe și separate de schemă (canale, vocabular interzis în exemple, suprapuneri); o variantă care pică îi ia modelului TOT rezultatul (nicio variantă salvată), nu doar variantei greșite; alegerea creează o versiune nouă a intrării, aprobarea e pasul separat al unui om; randarea ghidului întoarce `None` pentru profiluri vechi.
  - Găsit: `context.construieste` cu `la` implicit (acum, la secundă) nu vede o aprobare făcută în aceeași secundă; testele dau `la` explicit.
  - NEVERIFICAT: model real; aprobarea reală pentru CariereAI / BigBrain.
- **F4.9 — Profilul de public și vocea clientului.**
  - Construit: `app/onboarding/{extractie,citate,public}.py`, două prompturi, fluxurile `onboarding.extrage` (generic pe pasaje, refolosit de F4.10) și `onboarding.profil_public`, materiale de probă inventate (26 de texte), `docs/specs/F4.9.md`.
  - Hotărâri: citatul e respins de reguli deterministe (literal, date personale, nume de autor, lungime), nu judecat de model; profilul de public se aprobă doar de om chiar dacă compartimentul permite aprobarea de sistem (`inregistreaza_cere_om`); poarta cere 20 de citate, deci „Gata când” e impus de cod, nu doar de test; extragerile refolosesc `creier_extrageri` (aceeași idempotență ca la fapte).
  - Găsit: garda de date personale nu maschează numele proprii (decizie F3.9 deschisă), deci semnăturile de autor se resping la verificare, nu la gateway.
  - NEVERIFICAT: orice model real; recenzii reale; aprobarea reală pentru CariereAI / BigBrain.
- **F4.10 — Harta pieței și brieful de insight.**
  - Construit: `app/onboarding/{piata,sondaj}.py`, două prompturi, fluxurile `onboarding.extrage` (tip `afirmatii`) și `onboarding.brief_insight`, concurenți inventați, `docs/specs/F4.10.md`.
  - Hotărâri: poarta brieful rulează și sondajul (nu doar ecranul), deci nicio cale nu aprobă un brief cu trimiteri false; un brief cu o afirmație fără trimitere se salvează ca ciornă, nu se pierde; numele concurentului vine din sursă, nu din model; eșantionul depinde de amprenta conținutului (reproductibil, nu „norocos” la a doua rulare); afirmațiile concurenței se aprobă de sistem după verificare, brieful doar de om (`inregistreaza_cere_om`).
  - Găsit: o trimitere către un identificator inexistent trebuia raportată, nu să arunce `IntrareInexistenta`; un test trebuie să încerce aprobarea de sistem ÎNAINTE de cea umană (după aprobare, tranziția e refuzată pe altă cale).
  - NEVERIFICAT: modele reale; site-uri reale de concurență.
- **F4.11 — Strategia pe 90 de zile, prima formă.**
  - Construit: `app/onboarding/strategie.py`, promptul de strategie, fluxul `onboarding.strategie`, ecranul `/campanii` (două șabloane), secțiunile la cerere ale constructorului de context, `lant_onboarding.py` (ajutor de test pentru lanțul brief → insight), `docs/specs/F4.11.md`.
  - Hotărâri: schema este și poarta (o strategie incompletă nu există pe nicio cale, nici din editor); strategia se construiește doar din context APROBAT și lipsa oricărui element al contextului oprește propunerea (nu se improvizează); secțiunile noi ale pachetului sunt la cerere ca să nu schimbe pachetele existente (F4.7); relevanța faptelor fiind lexicală, întrebarea strategiei poartă produsele și prețurile din brief.
  - Găsit: `context.construieste` cu `la` implicit (acum, la secundă) nu vede ce s-a aprobat în aceeași secundă: strategia cere `la` exact; un analist de agenție nealocat nu vede niciun client (RLS), deci testele ecranelor folosesc proprietarul.
  - NEVERIFICAT: model real; aprobarea reală pentru CariereAI / BigBrain.
- **F4.8 — Ecranul „Creierul de brand”.**
  - Construit: `app/panou/creier_ecran_web.py` (patru pagini, patru șabloane), `creier.rezumat_pe_compartimente` / `propuneri_in_asteptare`, rând de meniu, `docs/specs/F4.8.md`.
  - Hotărâri: editarea construiește formularul din conținutul aprobat și păstrează valorile câmpurilor absente din cerere; toate schimbările trec prin serviciul Creierului (audit, schemă, poartă), nu prin SQL din panou; faptele și ofertele nu se editează în editorul generic (au circuite cu verificări proprii); operatorul poate propune, doar proprietarul decide.
  - Verificat în plus: șase pagini în Chrome headless, într-un `iframe` de 390 px (fereastra headless nu coboară sub 500 px): nicio derulare orizontală; capturi în scratchpad.
  - Găsit: un analist de agenție nealocat nu vede niciun client (RLS), deci testele de permisiuni verifică refuzul acțiunilor, nu conținutul paginilor.
  - NEVERIFICAT: telefon real; editarea JSON pe telefon.
- **Poarta F4 — lanțul verificat local.**
  - Construit: `tests/integration/test_poarta_f4.py` (un test cap-coadă), `app/creier/pregatire.py` (comanda de pregătire a unui brand propriu) cu `tests/integration/test_creier_pregatire.py`, `docs/specs/F4-poarta.md`.
  - Starea: **poarta propriu-zisă este DESCHISĂ** (cere materialele și aprobarea proprietarului). Local s-a dovedit doar că lanțul funcționează cu modele false.
  - Găsit pe parcurs: un test al F4.10 depindea de ordinea (UUIDv7) în care afirmațiile erau oferite modelului fals (stabilizat în commitul F4.8); `SursaColectare` are `url_radacina`, nu `url` (un șablon nu l-ar fi afișat fără eroare).
- **Propuneri în afara pasului (pentru F5, F6, F13).**
  - F6 (producția): să ceară `context.construieste(..., sectiuni_extra=("strategie",))`; secțiunea nu e implicită ca să nu schimbe pachetele F4.7.
  - Documentul 10.1 trebuie actualizat cu cele trei compartimente adăugate (D-005).
  - Nișa clientului (constrângeri de nișă) și cine fixează țintele strategiei.
  - Portalul clientului (F7) poate refolosi `app.onboarding.sesiuni` (interviul) și aprobările din `creier.aproba`.
  - Un job lunar pentru „vocea clientului” și trimestrial pentru harta pieței (12.7) — folosesc aceleași fluxuri `onboarding.extrage`.
  - O garda statică pentru `sesiune_agentie` în `app/creier/pregatire.py` e acum în lista cunoscută din `tests/unit/test_garzi_db.py`.


- **Reparatie CI `check` (commit `0516c9d`).** 36 de teste de integrare (creier_*, onboarding_*, campanii_panou) picau în CI cu `PermissionError: [Errno 13] Permission denied: '/var/lib/ama'`. Cauza: `AMA_MEDIA_DIR` avea implicit `/var/lib/ama/media`, iar testele care salvează surse nu îl suprascriau; local rulam ca root (directorul exista deja), în CI ca utilizator fără drepturi. Reparatie: `tests/conftest.py` fixează `AMA_MEDIA_DIR` pe un director temporar (șters la ieșire) dacă variabila nu e setată; testele care o suprascriu explicit rămân neschimbate. Nicio verificare slăbită.

- **Reparatie CI `check` (commit `c0bbba1`, jobul anulat la 15 minute).**
  - Dovada din jurnalul jobului 131579635150: pytest a pornit la 23:52:01 UTC și a ajuns la 26% (~565 de teste) până la 00:04:36, apoi nimic până la anulare (00:06:17). Mai bine de un sfert dintre teste erau deja `F` (≈60), iar între 23:59:44 și 00:04:09 un singur rând de 72 de teste a durat 4 min 25 s (în rest 30–50 s), cu serii de 9 teste picate la rând (chaos/watchdog, `test_alerte_panou`, `test_motor_cozi`, `test_onboarding_*`) — adică așteptări care expiră (20–30 s fiecare), nu aserțiuni. În jurnalul Postgres nu apare nicio eroare în acele intervale: blocajul era în procesul pytest. `pytest -q` nu scrie numele testelor picate decât la final, deci un job anulat nu spune care sunt.
  - Cauza exactă a opririi **NU a putut fi reprodusă**: suita completă trece local cu `AMA_MEDIA_DIR` pe director temporar, ca utilizator fără root (`nobody`), pe CPython 3.12.3 (ca CI) și 3.13, pe 1 și 2 nuclee, sub încărcare CPU, cu Postgres `en_US.UTF-8` și `fsync` pornit, cu ceasul (procesul pytest și Postgres) mutat peste miezul nopții UTC și în 2027, fără nicio conexiune sau căutare DNS spre exterior (cârlig de audit pe socket-uri). Nu pretindem că ținta e atinsă pentru blocajul din CI; reparațiile de mai jos scot defectele reale găsite și fac următorul blocaj vizibil și scurt.
  - Defecte reale găsite și reparate: (1) `test_gateway_cote::test_zece_la_suta_…` aștepta resetarea zilnică „2026-11-13” cu ceasul real al zilei în care fusese scris (pica din 13.11.2026 00:00 UTC); acum folosește ceasul controlat. (2) `test_gateway_evaluare::test_fluxul_de_evaluare_…` compara amânarea calculată cu ceasul controlat (2026-11-13 00:00:01) cu `datetime.now()` real, deci pica după acel moment; acum compară cu ceasul controlat. (3) Mascarea datelor personale (`app/gateway/mascare.py`) lua cifrele unui UUIDv7, despărțite prin `-`, drept card (≈0,26% dintre UUID; 527 din 200 000) sau telefon, iar marcajul `[afirmatie:<uuid>]` din prompt ajungea mascat: modelul nu mai putea cita sursa, deci testele `test_onboarding_*` picau aleatoriu (≈1 rulare din 10 pe `test_onboarding_piata`/`strategie`, „assert 8 >= 9”). Detecțiile care ating un UUID se ignoră acum; testele noi pică fără reparație.
  - Plafon de timp: `faulthandler_timeout = 100` în `pyproject.toml` (tracebackurile tuturor firelor în jurnal) și, în `tests/conftest.py`, un plafon de 120 s pe test (SIGALRM, biblioteca standard; `AMA_TEST_PLAFON_SEC`) care îl pică cu numele lui; după 3 teste depășite rularea se oprește (cod 3), ca un blocaj să nu consume tot jobul de 15 minute. Testele picate sau mai lente de 20 s se scriu imediat în jurnal (`[PICAT] …`, `[LENT] …`). `timeout-minutes` rămâne 15.
  - Verificat: `make check` (2177 de teste, 6 min 7 s) și `make guards` verzi, local, ca root. Rămâne deschis: o nouă rulare CI; dacă se blochează din nou, jurnalul va conține numele testului și tracebackul firelor.

## 2026-11-13 — Sesiunea 8: faza F5, Validare și aprobări (F5.1–F5.6)

### 22. Un agent de cod (Sonnet), pe ramura `claude/amazing-volta-ou9t2u`
- Un commit pe pas, `make check` verde înainte de fiecare. F5.7–F5.10 nu s-au construit (rămân pentru pașii următori).
- **F5.1 — Cadrul de validare.**
  - Construit: `app/validare/{verdict,agregare,registru,intrare,cascada,continut,depozit,autor,ciclu,fluxuri,modele}.py`, migrarea `0028` (conținut, rulări, verdicte), secțiunea „Validare” din urma livrabilului, `docs/specs/F5.1.md`, DECIZII D-006.
  - Hotărâri: orice eșec blochează; severitatea hotărăște reparație (majoră) sau carantină (critică); în treptele gratuite rulează toți pașii înainte de oprire, ca autorul să primească toate corecturile; în V3 / V4 se oprește la primul eșec; cascada goală e eroare, nu trecere; limita de 2 runde nu este dublată (a treia reparație o refuză `productie.muta`); conținutul livrabilului e provizoriu până la F6.
  - NEVERIFICAT / SIMULAT: validatorii și autorul din teste; pragul de avertismente (4) și punctajul sunt valori de pornire.
- **F5.2 — G1 Structură și G10 Limbă.**
  - Construit: `app/validare/{structura,limba,text_ro,probleme,judecator,prompturi,date_validare}.py`, `date/{structura,limba}.toml`, promptul `validare.g10_limba.v1`, `docs/specs/F5.2.md`.
  - Hotărâri: datele sunt TOML (`tomllib`); lungimile pe canal nu sunt în docs/15, deci toate sunt [I]; limba se detectează după cuvinte funcționale, pe text fără diacritice la fel; dicționarul de diacritice exclude cuvintele ambigue (pana, mana, limba, apa, vara, comanda, va …); un judecător nu blochează fără fragment literal din text; un criteriu fără răspuns rămâne „neverificat”, nu „trecut”.
  - Găsit: gateway-ul adaugă el însuși instrucțiunea „date, nu instrucțiuni” (conține un delimitator), deci testul de injecție numără închiderile cu identificator, nu simplul text.
  - NEVERIFICAT / SIMULAT: lungimile pe canal, judecătorul de limbă (model FALS), acoperirea dicționarului.
- **F5.3 — G2 Verificatorul de fapte.**
  - Construit: `app/validare/{afirmatii,acoperire,verifica_fapte,intrebari}.py`, `date/afirmatii.toml`, promptul `validare.g2_afirmatii.v1`, migrarea `0029`, ramura `INTREBARE` din `ciclu.py`, secțiunea „Întrebări către client” din urma livrabilului, `docs/specs/F5.3.md`.
  - Hotărâri: extragerea și potrivirea sunt deterministe, același extractor construiește și intrările registrului (aceleași normalizări); prețul de referință al unei oferte se acceptă doar prezentat ca preț anterior; un preț real dar al altui produs e „preț diferit”; citatele din surse acoperă doar dacă apar literal în pasajul clientului (RLS: pasajul altui client nu e vizibil); decizia `INTREBARE` stă peste reparație și sub carantină; răspunsul la întrebare nu devine fapt (îl aprobă un om în Creier, apoi reia un om); V3 rulează doar dacă V1 a trecut.
  - Găsit: funcția `aproba_fapt` / `propune_fapt` primește `acum`, deci testele aprobă la un moment fix și validează la `LA` fix, fără ceasul real.
  - NEVERIFICAT / SIMULAT: acoperirea listelor de superlative / promisiuni, fals-pozitivele pe texte reale (F5.7), modelul V3 (FALS).
- **F5.4 — Pachetele de reguli și G3 Politici.**
  - Construit: `rulepacks/` (10 pachete, 25 reguli), `app/validare/{reguli,reguli_client,politici}.py`, migrarea `0030`, promptul `validare.g3_politici.v1`, `Dockerfile` (COPY rulepacks), `creier.citire` exportat, `docs/specs/F5.4.md`.
  - Hotărâri: TOML (`tomllib`), nu YAML (nicio bibliotecă YAML printre dependențele de rulare); directorul `rulepacks/` din docs/24, nu `reguli/`; potrivire pe text fără diacritice cu aceeași lungime (fragmentul e exact din text); nișele refuzate = `critica` → carantină; mențiunile obligatorii se exprimă ca reguli `obligatoriu` (cu `daca_text` / `conditie`) — mecanismul pe care F5.6 îl refolosește; regulile clientului au aceeași schemă și aceleași exemple, autor uman în `creat_de NOT NULL`; verdictul păstrează versiunea și amprenta pachetelor.
  - Găsit: gardă care a prins singură o mențiune a directorului într-un docstring (regulile se numesc o singură dată, în încărcător); scriptul meu de rupere a liniilor lungi strica docstring-uri (reparat; verificat cu `ast`).
  - NEVERIFICAT: TOATE sursele regulilor ([I]): adrese și acte normative scrise din memorie, neverificate de un om; cuprinderea e un set mic de început; fals-pozitive pe texte reale nemăsurate.
- **F5.5 — G4 Ton și G8 Lizibilitate și conversie.**
  - Construit: `app/validare/{ton,conversie}.py`, `date/{ton,conversie}.toml`, prompturile `validare.g4_ton.v1` și `validare.g8_conversie.v1`, `docs/specs/F5.5.md`.
  - Hotărâri: rubricile (V3) rulează doar când semnalul deterministic (similaritate sub prag, hook slab) l-a ridicat: pasul întoarce `None` și nu consumă cotă; vectorii indisponibili dau „necalculat” (avertisment), nu blocare; apelurile la acțiune se numără pe GRUPE de forme imperative (aceeași grupă = un singur apel); formele ambigue cu substantive („comanda ta”) cer un complement tipic; ILA e un indice propriu, documentat, nu Flesch.
  - Găsit: două execuții `pytest` simultane pe același server Postgres se strică una pe alta (rolurile serverului își schimbă parola la fiecare sesiune): verificările complete rulează acum pe un al doilea server (port 54330) ca să nu intre în conflict cu testele de dezvoltare. Un script al meu de „reparare” a liniilor lungi a stricat literale de șir adiacente (reparat din git și din erorile de compilare; verificat cu `ast`, `ruff`, `mypy` și testele).
  - NEVERIFICAT / SIMULAT: pragul de similaritate pe un model real de vectori, listele de formule imperative și de deschideri slabe, pragurile ILA, judecătorii (model FALS).
- **F5.6 — G7 Originalitate și G9 Juridic.**
  - Construit: `app/validare/{originalitate,juridic}.py`, `date/{originalitate,juridic}.toml`, `rulepacks/juridic.toml` (tip nou de pachet, doar pentru G9), promptul `validare.g9_juridic.v1`, `docs/specs/F5.6.md`.
  - Hotărâri: sursele nereutilizabile blochează, materialele clientului doar avertizează (reutilizarea propriilor materiale e legitimă); prețul de referință se verifică pe versiunile aprobate ale ofertei, nu pe un istoric separat; lipsa istoricului e avertisment explicit, nu trecere; judecătorul V4 folosește profilul `strategie` (T3) și rulează doar după ce V1 a trecut.
  - Găsit: la început serverul Postgres de test pornit în sesiunea anterioară nu mai rula după resetarea limitei (verificarea completă dădea sute de erori de conexiune, nu defecte de cod); verificările complete rulează pe al doilea server (port 54330).
  - NEVERIFICAT / SIMULAT: interpretarea juridică a regulii de 30 de zile (fără avocat), pragurile, vectorii (SIMULAȚI), judecătorul V4 (FALS).

## 2026-11-13 — Sesiunea 9: închiderea fazei F5 (F5.7, F5.8, F5.10, F5.9, poarta F5)

### 23. Un agent de cod (Opus), pe ramura `claude/amazing-volta-ou9t2u`
- D-007 (agentul de cod decide; nimic „de confirmat de proprietar”): D-004–D-006 adoptate, STARE rescris cu starea reală.
- **F5.7 — Seturile de aur și bancul.**
  - Preluat ciorna necomisă; revizuită: `app/db.comuta_context` (schimba orice context în mijlocul tranzacției, inclusiv client →
    agenție) înlocuit cu `restrans_la_client` (doar îngustare, punct de salvare anulat la ieșire); ciorna de test ștearsă.
  - Construit: ecranul `/validatoare` (bancul, istoricul, butonul), testele, declanșatorul pe `exemple_propuse`, spec F5.7.
  - Prima rulare: 99/107 blocate (92,5%), 5/63 respinse pe nedrept; după îmbunătățirea validatorilor (seturile neatinse,
    amprentele neschimbate): 107/107 și 3/63 (4,8%). Scor optimist (aceleași seturi au arătat ce lipsea), documentat.
  - Găsit: workerul nu importa `app.validare.fluxuri` (din F5.1); `porn\w*` prindea „pornit”; „încearcă” nu era recunoscut.
  - NEVERIFICAT / SIMULAT: vectorii și judecătorii nu sunt în scor; seturi inventate.
- **F5.8 — Calibrarea judecătorilor.**
  - Construit: `calibrare_nucleu` (eșantion, Wilson, kappa, acord, derivă), `calibrare` (coadă, etichete, statistici, alerte), jobul
    săptămânal, ecranul `/validatoare/calibrare`, migrarea `0032`, spec F5.8.
  - Hotărâri: eșantion stratificat pe judecător (un judecător rar nu dispare); acordul se exprimă și ca kappa față de adevărul
    stabilit de om; deriva se compară doar în aceeași versiune (prompt + model + validator); pragurile sunt [I].
  - Verificat: 22 de verdicte reale ale cascadei cu judecător FALS, etichete simulate → 81,8%, alertă, 4 exemple propuse.
- **F5.10 — Carantina și contestațiile.**
  - Construit: `app/validare/carantina.py`, ecranele de carantină, verdict și exemple propuse, legătura „Contestă” în urma livrabilului.
  - Hotărâri: respingerea definitivă = `anulat` (mașina de stări neschimbată); contestația este rândul din `exemple_propuse`
    (sursa `contestatie`), fără tabel separat; eliberarea în validare pornește jobul după commit.
  - Verificat: lanțul complet contestat → propus → promovat → inclus în banc.
- **F5.9 — Biroul de aprobări.**
  - Construit: `validare.birou` + `birou_nucleu`, rutele de editare și răspuns, șablonul nou, CSS, migrarea `0033`, spec F5.9.
  - Găsit: în F2 editarea unui livrabil care aștepta aprobare redeschidea cererea pe versiunea NOUĂ, nevalidată; acum aprobarea
    cere ca versiunea curentă să fi trecut validarea (punct de extensie în `productie.aprobari`), iar editarea din birou trimite
    livrabilul înapoi în validare.
  - Verificat: teste HTTP; 390 px în Chrome headless (iframe), fără derulare orizontală; captura în scratchpad.
- **Poarta F5.**
  - Testul de poartă afirmă pragurile, verifică înghețarea seturilor și interzice orice apel la gateway: 107 / 107 blocate,
    3 / 63 respinse pe nedrept (4,76%), fiecare validator vizat ≥ 95%. Cifrele pe validator în `docs/specs/F5-poarta.md`.
  - Rămâne de măsurat la migrare: judecătorii reali și vectorii reali; scorul local e optimist (documentat).
  - Propuneri: aprobarea în grup (F6, cu loturile calendarului); un set de control scris de altcineva decât autorul
    ajustărilor; exportul periodic al exemplelor promovate într-un commit revizuit.

## 2026-11-13 — Sesiunea 10: faza F6, producția de text și publicarea asistată

### 24. Un agent de cod (Opus), pe ramura `claude/amazing-volta-ou9t2u`
- **F6.1 — Strategul de conținut și calendarul.**
  - Construit: `app/continut` (calendar, fluxuri, prompturi, modele), ecranul `/calendar/{client}`, migrarea `0034`, spec F6.1, ajutorul de test `lant_continut.pana_la_strategie` și modelul fals `tests/continut_utile.py`.
  - Hotărâri (D-007): modelul propune doar conținutul, datele le așază un nucleu determinist; canalele vin din strategia aprobată; aprobarea calendarului e a unui om și creează livrabilele.
  - Găsit: pachetul de context citea strategia aprobată în aceeași secundă ca „neaprobată încă” (momentul trunchiat la secundă); calendarul cere pachetul la momentul exact.
  - Găsit: `test_gateway_apeluri_panou` depindea de ordinea testelor (apelurile lui purtau momentul fix T0, din trecut, iar lista arată ultimele 50); acum poartă momentul curent.
  - Verificat: 6 teste noi (unitare + integrare + HTTP); `make check`: 2553 trecute.
- **F6.2 — Autorul de brief.**
  - Construit: `continut.brief`, fluxul `continut.briefuri`, migrarea `0035`, spec F6.2.
  - Hotărâri (D-007): lume închisă prin aliasuri scurte; întrebarea pentru relevanță include ce vinde clientul (altfel o idee ca „degustarea de sâmbătă” nu primea niciun fapt); fără fapte în pachet lipsa se scrie explicit.
  - Verificat: 3 teste de integrare.
- **F6.3 — Hook-uri și postări.**
  - Construit: `continut.scriere`, `continut.editor`, `continut.pipeline`, fluxul `continut.produ`, migrarea `0036`, trei prompturi, spec F6.3.
  - Hotărâri (D-007): alegerea hook-ului e deterministă (G8 + cifre fără fapt), nu prin model; autorul de reparații e o „sursă” care răspunde doar pentru livrabilele cu brief, ca testele și comportamentul F5 („fără autor”) să rămână neschimbate; aprobarea după validare printr-un punct de extensie, nu în ciclul validării.
  - Verificat: 6 teste (unitare + integrare): 10 / 10 postări validate, 2 cu reparație.
- **F6.4 — Scripturi video.**
  - Construit: `continut.scripturi`, autorul pe tip în `scriere.AUTORI`, `AutorEsuat` (coada de erori cu diagnostic), prompt, spec F6.4.
  - Hotărâri (D-007): durata o calculează sistemul din cuvinte, nu modelul; verificarea duratei rămâne în autor, nu în G1 (versiunea G1 și seturile F5 neschimbate; propunere notată).
  - Verificat: 3 teste; postările F6.3 trec în continuare (al cincilea hook, scurt, nu schimbă alegerea pentru postări).
- **F6.5 — Adaptorul pe platformă.**
  - Construit: `continut.adaptor`, migrarea `0037`, prompt, spec F6.5.
  - Hotărâri (D-007): o adaptare = un livrabil nou (aprobat și publicat separat, cu cheia lui de idempotență); ținte native [I] mai stricte decât maximele G1; canalele țintă nu se limitează la strategie.
  - Verificat: 2 teste de integrare.
- **F6.6 — Publicarea asistată.**
  - Construit: `app/publicare` (asistata, modele), ecranul `/publicare`, partajarea în `app.js`, migrarea `0038`, punctul de extensie după decizie în aprobări, spec F6.6.
  - Hotărâri (D-007): modul asistat nu e un efect extern al platformei (publică omul), deci nu trece prin executor; cheia de idempotență se păstrează pentru F9; pachetul se pregătește automat la aprobare doar pentru livrabilele din calendar.
  - Găsit: jurnalul de evenimente refuză cheia `cheie` în date (filtrul de secrete); cheia de idempotență intră ca `idem`.
  - Verificat: 5 teste (unitare + HTTP). Telefonul real și postarea reală rămân la migrare.
- **F6.7 — Capturarea feedbackului.**
  - Construit: `continut.feedback`, secțiunile `exemple` / `exemple_negative` în constructorul de context, spec F6.7.
  - Hotărâri (D-007): exemplele trăiesc în compartimentele Creierului (aprobate prin sistem), nu într-un tabel nou; contextul le aduce pe tip și canal, fără să le declare lipsă.
  - Sesiunea a fost întreruptă de limita de utilizare la mijlocul pasului; reluată după resetare (Postgres-ul de test repornit).
  - Verificat: testul de integrare.
- **F6.8 — Proba de două săptămâni (simulată).**
  - Construit: `continut.proba`, spec F6.8 cu rezultatul simulării.
  - Hotărâri (D-007): proba devine simulare accelerată; incidentul critic definit [I] (publicare fără validare / fără om / dublă / fără pachet; eroare neprinsă); carantina și coada de erori nu sunt incidente.
  - Verificat: 32 de livrabile în 14 zile pe două branduri, 0 incidente, rata 0,75 (dată de omul simulat). Proba reală, la migrare.
- **Poarta F6.**
  - Testul de poartă parcurge toți pașii F6.1–F6.8 pe brandul fictiv, cu aprobările, respingerea și linkul lipit prin rutele reale; trecut (21 s).
  - Găsit: în poartă briefurile tuturor sloturilor se scriu înaintea respingerii, deci exemplul negativ ajunge la sarcina următoare prin promptul autorului, nu prin pachetul brieful (ambele drumuri sunt testate: F6.7 și poarta).
  - Rămâne deschis (la migrare): proba reală, postarea reală, primul val F0, backupul pe VPS.
  - Propuneri: verificarea duratei scriptului ca pas G1 cu set de aur propriu; aprobarea în grup pe loturile calendarului; partea cu model a editorului E8 după F11.

## 2026-11-13 — Sesiunea 11: faza F7, site, portal, facturare

### 25. Un agent de cod (Opus), pe ramura `claude/amazing-volta-ou9t2u`
- **F7.1 — Site-ul complet.**
  - Construit: `app/site` (pagini, web, analiza, blog, modele), șabloanele `site/*`, `site.css`, `finante.planuri`, migrarea `0039`, spec F7.1.
  - Hotărâri (D-007): site sub `/site` în monolit, fără JS (bannerul e formular); analiza = contor pe (zi, pagină), fără identificatori; prețurile [I] din planuri, comune cu facturarea.
  - Verificat: 3 teste de integrare, 3 unitare.
- **F7.2 — Formularul de audit.**
  - Construit: `site.audit`, `site.motor_audit`, `efecte.sistem`, conectorul `email` (simulat), ecranul `/leaduri`, migrarea `0040`. Hotărâri (D-007): outbox separat pentru efectele fără livrabil; jetonul raportului e altul decât cel de confirmare; spamul primește același răspuns. Verificat: 2 teste.
- **F7.3 — Portalul: cont și onboarding.**
  - Construit: `portal.cont`, `portal.progres`, `portal.web`, șabloanele `portal/*`, migrarea `0041`. Hotărâri: actorul `sistem` pentru activare; pașii de progres extensibili. Găsit: testul panoului aștepta 403 pe `/` pentru client; acum redirecționare spre portal (test adaptat). Verificat: 2 teste.
- **F7.4 — Portalul: Creier, calendar, aprobări.**
  - Construit: `portal.lucru_web`, `conturi.are_aprobator_client`, decidentul implicit în aprobări. Hotărâri: lotul se aprobă într-o tranzacție (orice refuz anulează tot). Verificat: 2 teste; testele F5/F6 ale aprobărilor neschimbate.
- **F7.5 — Portalul: materiale și inboxul de tendințe.**
  - Construit: `media.biblioteca`, `media.tendinte`, `portal.materiale_web`, migrarea `0042`. Verificat: 3 teste.
- **F7.6 — Facturare.**
  - Construit: `connectors.plati` (simulat), `finante.abonamente`, `finante.web`, `site.inscriere`, `portal.cont_web`, migrarea `0043`. Hotărâri: plățile ca efecte de sistem; invitația după prima activare prin extensie; suspendarea = oprirea pe client. Verificat: 2 teste.
- **F7.7 — Export și ștergere.**
  - Construit: `db.stergere`, `portal.date`, migrarea `0044`. Găsit: politicile forțate se aplică și proprietarului; ștergerea setează contextul de agenție și ocolește politicile doar pe tabelul în lucru. Verificat: 2 teste.
- **F7.8 — Raportul lunar, prima formă.**
  - Construit: `analiza.raport_lunar`, `portal.rapoarte_web`, migrarea `0045`. Hotărâri: luna după slotul livrabilelor. Verificat: 1 test.
- **F7.9 — Oferta, pâlnia și paginile de captare.**
  - Construit: `oferta.pagini`, `validare.independent`, două prompturi, `site.captare_web`, migrarea `0046`. Găsit: „gratuit” e o afirmație G2 (cere faptul aprobat). Verificat: 2 teste.
- **F7.10 — Cercetarea SEO și articolele.**
  - Construit: `seo.cuvinte`, `seo.articole`, trei prompturi. Găsit: citările [n] erau luate de G2 drept cifre; nu intră în textul validat. Verificat: 2 teste.
- **Poarta F7.**
  - Testul cap-coadă trecut pe simulare. Notă de proces: `make check` complet a rulat pe arborele cumulat F7.1–F7.10 (două rulări întrerupte de modificări făcute în paralel au fost aruncate); fiecare pas are testele lui trecute separat. Rezultat final: `make check` 2624 trecute. Commiturile intermediare F7.x nu sunt construibile izolat (fișierele comune sunt în primul pas care le atinge); vârful ramurii e cel verificat.
  - Propuneri: eliminarea EXIF (F8); CRM pentru leaduri (F12); calibrarea listei de îndemnuri G-CTA în banc.

## 2026-11-14 — Sesiunea: faza F8 (Media)
- **F8.1 — Vocea și licența ei.**
  - Construit: `media.audio`, `media.voce`, `biblioteca.incarca(licenta=, generare=)`, migrarea `0047`, spec F8.1. Hotărâri (D-007): motorul simulat ca implicit; doar vocea `verificata` se publică; vocea proprie ca țintă. Găsit: `JSONB` fără `none_as_null` scria `null` JSON (refuzat de CHECK). Verificat: 2 teste de integrare, 3 unitare.
- **F8.2 — Normalizarea textului românesc.**
  - Construit: `media.normalizare`, `media.pronuntie`, migrarea `0048`, setul de 100 de fraze. Hotărâri (D-007): acord după substantivul următor, cu excepții; compusele în 1 rămân „unu”. Găsit: „V60” se citea lipit („Vșaizeci”); acum literă și cifră se despart. Verificat: 110 teste unitare, 1 de integrare.
- **F8.3 — Transcrierea inversă și timpii pe cuvânt.**
  - Construit: `media.transcriere`, configurarea whisper.cpp, spec F8.3. Hotărâri (D-007): transcriptorul simulat măsoară momentele din semnal (energie), cuvintele din bucata `amaw`; aliniere forțată când lipsesc. Verificat: 1 test de integrare, 3 unitare.
- **F8.4 — Furnizorul de imagini și biblioteca de active.**
  - Construit: `media.licente`, `media.furnizori`, `media.ffmpeg`, migrarea `0049` (`folosiri_active` + declanșatorul care cere licența), EXIF eliminat în `biblioteca`, ffmpeg + DejaVu în CI și Dockerfile. Hotărâri (D-007): licența pe tip cu câmpuri obligatorii; regulile promptului din 14.3. Verificat: 2 teste de integrare (+ testele F7.5 neschimbate).
- **F8.5 — Lista de decizii de montaj și Regizorul.**
  - Construit: `media.lista`, `media.regizor`, promptul `media.regizor.v1.md`, `tests/media_utile.py`. Hotărâri (D-007): modelul alege doar cadrul și mișcarea; momentele le pune programul. Verificat: 2 teste de integrare.
  - Notă: o rulare `make check` a picat o dată în `test_portal_date` (blocaj reciproc între jobul de export și cel de ștergere, F7.7, independent de F8); testul trece singur și la rularea completă următoare. Propunere: serializarea joburilor de export și ștergere ale aceluiași client.
- **F8.6 — Montajul pentru formatele A și B.**
  - Construit: `media.randare`, `media.montaj`, migrarea `0050` (`randari`), configurarea `AMA_MEDIA_PRESET/FIRE/FONTURI` (testele: `ultrafast`). Verificat: 2 teste de integrare (A, B).
- **F8.7 — Subtitrări și sunet.**
  - Construit: `media.subtitrari`, `media.sunet`, `furnizori.aduce_muzica`. Găsit: în ASS `Fontsize` e înălțimea rândului (libass desenează ~0,86 din em-ul Pillow); lățimile se măsoară acum la mărimea libass. Verificat: 2 teste de integrare.
  - Găsit la F8.7: blocajul reciproc din `test_portal_date` (de două ori din patru rulări) venea din test: numărarea rândurilor ținea, într-o singură tranzacție, blocaje pe toate tabelele, iar ștergerea le ia pe rând în acces exclusiv; mai multe tabele (F8) au lărgit fereastra. Numărarea rulează acum în autocommit.
- **F8.8 — Controlul media (G6) și auditorul vizual (G5).**
  - Construit: `media.control`, `media.vizual`, controlul în montaj. Găsit: o fotografie fără mișcare în formatul B e un îngheț pentru G6 (acum fotografiile se mișcă mereu); intervalele de îngheț lipite se unesc; contrastul se măsoară pe miezul literelor, nu pe media cu marginile netezite. Verificat: 2 teste de integrare.
- **F8.9 — Testul de capacitate.**
  - Construit: `media.fluxuri`, `media.capacitate`, măsurarea rulărilor ffmpeg (`ffmpeg.masurare`). Verificat: 1 test de integrare; cifrele locale în ieșirea testului.
  - Găsit: bucla de texte fără pauză ținea GIL-ul și sufoca firele executorului (testul trecea de plafonul de 120 s); tonurile vocii simulate se memorează, stock-ul deja adus nu se mai descarcă.
- **F8.10 — Șabloane grafice și Compozitorul.**
  - Construit: `media.sabloane`, `media.compozitor`, migrarea `0051`. Găsit: în Pillow 12 masca de glifă nu mai are `tobytes`; verificarea glifei desenează caracterul. Verificat: 2 teste de integrare.
- **F8.11 — Proveniență și dezvăluire AI (G11).**
  - Construit: `media.provenienta`, pașaportul în montaj și în Compozitor, metadatele în randare, migrarea `0052`. Hotărâri (D-007): vocea sintetică cere etichetă (21.9, „sunetul generat care poate părea real”). Verificat: 2 teste.
