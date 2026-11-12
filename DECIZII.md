# Fișierul de decizii

Hotărârile luate pe parcurs, în ordine cronologică. Deciziile de arhitectură au fișier propriu în `docs/adr/`.

## De hotărât de proprietar (F0.1)

| Decizie | Stare | Valoare |
| --- | --- | --- |
| Nișa-pilot | **deschisă** | – |
| Pachetul-pilot | **deschisă** | – |
| Numele agenției | **deschisă** | – (în cod se folosește provizoriu „AMA”) |

## Decizii luate

### D-001 (2026-11-11) — Construim întâi pe git, VPS-ul vine la final

- **Context:** planul (secțiunea 23) cere VPS măsurat (F0.4) și staging înainte de F1.
- **Hotărâre (proprietar):** platforma se construiește și se validează în repo, capitol cu capitol; migrarea pe VPS se face o singură dată, la final.
- **Consecințe:** criteriile „Gata când” care cer staging, telefon sau servicii externe se verifică prin teste automate în CI și local. Ce rămâne de verificat pe VPS se adună în `docs/specs/STARE.md`, la „De verificat la migrare”. Pașii F0.3–F0.8 (inventar, VPS, cereri de aprobare, juridic, conturi) rămân ai proprietarului și curg în fundal.

### D-002 (2026-11-11) — O cerere de integrare pe fază

- **Context:** planul spune „un pas = o ramură = o cerere de integrare”.
- **Hotărâre:** până la migrare, o fază (capitol) = o cerere de integrare, cu un commit pe pas. Validarea proprietarului se face la poarta fazei.
- **Consecințe:** revizuirea „doi ochi diferiți” (24.4) se face pe fază: un model scrie, alt model revizuiește diferența față de specificație.

### D-003 (2026-11-11) — Unelte de lucru

- Manager de pachete: `uv`, cu `uv.lock` (versiuni exacte și hash-uri). Python 3.13 în imagini și CI (cerința este ≥ 3.12).
- Acces sincron la bază (SQLAlchemy 2 + psycopg 3): mai simplu de izolat pe client și compatibil cu biblioteca de workflow-uri.
- Scanarea repo-ului după chei scăpate: `detect-secrets`; vulnerabilități: `pip-audit`. Ambele rulează în CI, fixate în `uv.lock`.
