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
| F1.7 Coaja panoului | verificat prin teste și în Chromium (390×844); instalarea pe telefon și push-ul real rămân la migrare | `tests/integration/test_panou.py`, `tests/unit/test_panou_static.py`, `docs/specs/img/F1.7-acasa.png` |
| F1.8 Livrarea | infrastructura și partea din panou verificate local; schimbul cu deployer-ul real rămâne la migrare | `tests/unit/test_infra_deployer.py`, `tests/integration/test_livrare_panou.py`, jobul CI `imagine` |
| F1.9 Backup | verificat local, inclusiv afișarea în panou | `tests/integration/test_backup_restore.py`, `tests/unit/test_operare_backup.py` |
| F1.10 Botul Telegram și opririle | verificat cu un client Telegram simulat; botul real rămâne la migrare. Steagurile de oprire nu sunt încă citite de nimic (modulele apar din F2) | `tests/integration/test_telegram.py`, `tests/contract/test_telegram_contract.py` |
| F2.1 Execuția durabilă | verificat local cu Postgres real și procese reale (SIGKILL, SIGTERM); imaginea și politica de restart din compose rămân la CI/migrare | `tests/chaos/test_recuperare.py`, `tests/integration/test_motor_executie.py`, `scripts/check_motor.py` |

## De verificat la migrarea pe VPS

- F0.4: măsurarea VPS-ului, refacerea tabelului 6.4, PD1.
- F1.8: `infra/vps/bootstrap.sh` pe un VPS real; Docker rootless cu porturile 80/443; certificatele Let's Encrypt; clientul de registru față de GHCR; fluxul `entrega.yml`; `migrate` cu migrările reale; subdomeniile și secretele din GitHub.
- F1.9: destinația externă reală a backupului (furnizor, capacitate, termeni); prima restaurare de test pe server; fixarea versiunilor pachetelor `apt` din imaginea de backup.
- F1.5: autentificare de pe telefon, cu aplicația de coduri, pe HTTPS (cookie-uri `__Host-`).
- F1.7: instalarea panoului pe telefon (Android și iOS), abonarea și primirea unei notificări push reale (cheile VAPID se generează cu `scripts/genereaza_vapid.py`); apelul real `pywebpush` nu a rulat niciodată.
- F1.8 (panou): promovare și revenire cap-coadă cu deployer-ul real; citirea volumului real `backup_status`.
- F1.10: crearea botului, `setWebhook` cu secretul, comenzile din conversația reală a proprietarului.
- F2.1: serviciul `worker` din compose pe un VPS real (politica `restart: unless-stopped` după o cădere reală, `stop_grace_period`); mutarea workerului de către deployer-ul real; limita de memorie a workerului sub joburi reale; numărul de conexiuni la Postgres sub încărcare; promovarea `AMA_MOTOR_VERSIUNE` la un flux modificat cu joburi în lucru.
