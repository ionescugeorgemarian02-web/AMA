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
- La cererea proprietarului (cota de utilizare se apropie de limită), programată o trezire automată a sesiunii peste 4 ore (2026-11-11, 23:58 UTC), cu instrucțiunea de a continua din `JURNAL.md` și `docs/specs/STARE.md`: revizuirea valului 2, `make check`, CI, actualizarea cererii de integrare. Faza F2 nu începe înainte de validarea fazei F1.
