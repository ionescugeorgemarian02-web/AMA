# Reguli pentru agenții de cod

Fișier unic, citit la începutul fiecărei sesiuni. Sursa de adevăr pentru specificații este `docs/` (index: `docs/index.md`).

## Scopul proiectului

Platformă de marketing autonomă („Agenția Autonomă de Marketing”) pentru IMM-uri din România:
cercetare, strategie, conținut text și video, validare în cascadă, publicare și reclame prin API-uri oficiale.
Rulează pe un singur VPS dedicat, pe modele gratuite plus un model local, cu aprobare umană graduală (L0–L4).
Se construiește în 17 faze (`docs/23-…`), pas cu pas, fiecare pas cu specificație și teste de acceptare.
Până la migrarea pe VPS, validarea se face în CI și local (vezi `DECIZII.md`, D-001).

## Decizii de arhitectură (nu se încalcă fără un ADR nou, aprobat)

Cele 16 decizii sunt în `docs/adr/`. Pe scurt: monolit modular Python (ADR-01); un singur Postgres pentru date,
cozi, workflow-uri și vectori (ADR-02); execuție durabilă prin bibliotecă (ADR-03); gateway de modele propriu (ADR-04);
componente tipizate D/L/A/M/H, implicit D (ADR-05); Claude în afara căii critice (ADR-06); doar API-uri oficiale (ADR-07);
proveniență și etichetare AI (ADR-08); fără avatar în v1 (ADR-09); voce locală pe CPU (ADR-10); învățare cu promovare
controlată (ADR-11); autonomie L0–L4 (ADR-12); interfață randată pe server, întâi pentru telefon (ADR-13);
izolare multi-tenant la nivel de rând (ADR-14); media pe disc local (ADR-15); VPS dedicat, totul pornit permanent (ADR-16).

## Regulile unei sesiuni

1. Citește acest fișier, specificația pasului (`docs/specs/<COD>.md`) și ADR-urile legate.
2. Spune ce ai înțeles și ce presupui. Întreabă doar dacă lipsește ceva esențial.
3. Scrie întâi testele de acceptare din „Gata când”.
4. Scrie codul minim care trece testele.
5. Rulează toate testele și verificările. Raportează exact ce ai rulat și ce a ieșit.
6. Actualizează documentația atinsă, `CHANGELOG.md` și jurnalul de lucru `JURNAL.md` (ce ai făcut, ce ai verificat, ce a rămas deschis).
7. Deschide cererea de integrare cu șablonul completat.
8. Nu atinge nimic în afara pasului. Ce observi în plus notezi ca propunere.

Nu declari un pas „gata” fără dovada testelor rulate. Ce nu ai putut rula spui explicit.
Orice parte nefuncțională sau simulată se marchează în cod (`# NEVERIFICAT:` / `# SIMULAT:`) și în raport.

## Comenzi

```bash
uv sync --locked            # instalează exact versiunile din uv.lock (cu hash-uri)
make check                  # tot ce rulează CI: lint, tipuri, gărzi, teste
make test                   # doar testele (pornește singur un Postgres local de test)
make lint                   # ruff check + ruff format --check
make guards                 # dependențe fixate + scanare de secrete
uv run alembic upgrade head # migrări
uv run uvicorn app.main:app --reload
```

## Interzis

- Secrete în cod, în teste sau în istoricul git. Configurarea vine doar din variabile de mediu (`app/config.py`).
- Dependențe noi fără justificare în cererea de integrare. Fiecare se fixează cu `==` și intră în `uv.lock`.
- Apeluri la modele în afara `app/gateway`.
- Efecte externe (publicare, email, reclame, plăți) în afara executorului de efecte (F2.5).
- Cod fără teste. Teste slăbite ca să treacă.
- Schimbări în afara pasului curent.
- Tabele cu date de client fără coloana `tenant_id` și fără politică de securitate la nivel de rând.
- Interogări care ocolesc `app/db` (sesiunea setează clientul curent; fără ea, baza refuză).

## Convenții de cod

- Python ≥ 3.12, FastAPI, SQLAlchemy 2 (sincron, driver psycopg 3), Alembic, Pydantic 2. Interfață: Jinja2 + HTMX + Alpine.js (build CSP), fără lanț de build JS, fișiere vendorizate în `app/web/static/vendor`.
- Identificatori: UUIDv7 generați de aplicație (`app/ids.py`).
- Timp: întotdeauna UTC, `timestamptz`.
- Jurnale: JSON structurat prin `app/logging.py`; fără date personale și fără secrete în jurnale.
- Numele din domeniu (module, tabele de business, texte de interfață) sunt în română, fără diacritice în identificatori; codul tehnic generic este în engleză. Textele afișate utilizatorului sunt în română, cu diacritice.
- Fiecare modul din `app/<modul>/` își expune API-ul prin `__init__.py`; modulele nu importă detaliile interne ale altora.
- Migrările sunt compatibile cu versiunea anterioară; fiecare are `downgrade` funcțional.
- Teste: `tests/unit`, `tests/contract`, `tests/integration`, `tests/isolation`, `tests/chaos`, `tests/smoke`. CI nu face apeluri de rețea reale și nu consumă cote.

## Unde este specificația pasului curent

`docs/specs/<COD>.md` (de exemplu `docs/specs/F1.4.md`), după șablonul Ș5 din `docs/27-anexe.md`, secțiunea 27.2.
Starea fazelor: `docs/specs/STARE.md`.
