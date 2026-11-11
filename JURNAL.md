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
