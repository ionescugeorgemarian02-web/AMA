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
| F10.1 Colectorul de metrici | în lucru |
| F10.2 Curba de retenție YouTube | neînceput |
| F10.3 Legarea de etichete | neînceput |
| F10.4 Tablouri de bord și scor de sănătate | neînceput |
| F10.5 Raportul lunar complet | neînceput |
| F10.6 Analiza de trafic proprie | neînceput |
| F10.7 Cercetătorul de tendințe | neînceput |
| F10.8 Analistul de reclame ale concurenței | neînceput |

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
   `app/worker.py` (`MODULE_FLUXURI`), `app/config.py`, `app/connectors/contract.py`, `tests/unit/test_garzi_db.py`:
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

`ffmpeg`, Postgres 16 și `uv` există deja în imagine. Fără `pgvector`, toate testele cu bază pică la pregătire
cu „extension "vector" is not available”.

## Cereri către cealaltă sesiune

- (B → A, 2026-11-14) Nimic de schimbat în F9. Metricile (F10.1) se citesc prin cititori separați, în
  `app/connectors/metrici/`, care refolosesc `ClientHttp` și depozitul de tokenuri din F9; conectorii de publicare
  rămân neatinși.
