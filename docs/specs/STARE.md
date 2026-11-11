# Starea construcției

Actualizat la fiecare pas închis. „Verificat” înseamnă: testele de acceptare trec în CI/local (D-001).

| Pas | Stare | Dovadă |
| --- | --- | --- |
| F0.1 Decizii de pornire | deschis (proprietar) | `DECIZII.md` |
| F0.2 Repo și reguli | făcut; protecția ramurii `main` o activează proprietarul în GitHub | CI |
| F0.3–F0.8 | ale proprietarului, în fundal | – |
| F1.1 Aplicația de bază | verificat | `tests/unit/test_baza.py` |
| F1.2 Dependențe fixate | verificat | `tests/unit/test_garzi.py`, `make guards`, `make audit` |

## De verificat la migrarea pe VPS

- F0.4: măsurarea VPS-ului, refacerea tabelului 6.4, PD1.
