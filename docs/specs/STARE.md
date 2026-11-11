# Starea construcției

Actualizat la fiecare pas închis. „Verificat” înseamnă: testele de acceptare trec în CI/local (D-001).

| Pas | Stare | Dovadă |
| --- | --- | --- |
| F0.1 Decizii de pornire | deschis (proprietar) | `DECIZII.md` |
| F0.2 Repo și reguli | făcut; protecția ramurii `main` o activează proprietarul în GitHub | CI |
| F0.3–F0.8 | ale proprietarului, în fundal | – |
| F1.1 Aplicația de bază | verificat | `tests/unit/test_baza.py` |
| F1.2 Dependențe fixate | verificat | `tests/unit/test_garzi.py`, `make guards`, `make audit` |
| F1.3 Baza de date și migrările | verificat | `tests/integration/test_migratii.py` (înainte și înapoi) |
| F1.4 Clienți, utilizatori, roluri | verificat | `tests/isolation/` (refuz impus de bază) |
| F1.5 Autentificare | verificat prin teste HTTP; proba de pe telefon rămâne la migrare | `tests/integration/test_autentificare_http.py` |
| F1.6 Jurnalul de audit și de evenimente | verificat | `tests/integration/test_audit.py` |
| F1.8 Livrarea | partea de infrastructură verificată local; partea din panou urmează | `tests/unit/test_infra_deployer.py`, jobul CI `imagine` |
| F1.9 Backup | partea de infrastructură verificată local; afișarea în panou urmează | `tests/integration/test_backup_restore.py` |

## De verificat la migrarea pe VPS

- F0.4: măsurarea VPS-ului, refacerea tabelului 6.4, PD1.
- F1.8: `infra/vps/bootstrap.sh` pe un VPS real; Docker rootless cu porturile 80/443; certificatele Let's Encrypt; clientul de registru față de GHCR; fluxul `entrega.yml`; `migrate` cu migrările reale; subdomeniile și secretele din GitHub.
- F1.9: destinația externă reală a backupului (furnizor, capacitate, termeni); prima restaurare de test pe server; fixarea versiunilor pachetelor `apt` din imaginea de backup.
- F1.5: autentificare de pe telefon, cu aplicația de coduri, pe HTTPS (cookie-uri `__Host-`).
