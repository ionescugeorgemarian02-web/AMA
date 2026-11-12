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
| F2.2 Cozile | verificat local (executor în proces, Postgres real); mai mulți workeri și ferestre lungi de rată rămân la migrare | `tests/integration/test_motor_cozi.py`, `tests/unit/test_motor_cozi.py` |
| F2.6 Planificatorul de timp | verificat local (timp real cu cron de o secundă, ceas controlat, SIGKILL); „la minut pe staging” rămâne la migrare | `tests/integration/test_motor_programare.py`, `tests/chaos/test_programare.py` |
| F2.7 Watchdog și coada de erori | verificat local cu procese reale (SIGKILL cu supervizor simulat, job care strică workerul), Postgres real și ecranul în teste HTTP; politica de restart/healthcheck din compose și canalele de notificare rămân la migrare | `tests/chaos/test_watchdog.py`, `tests/integration/test_watchdog.py`, `tests/integration/test_alerte_panou.py`, `tests/isolation/test_motor_rls.py` |
| F2.3 Mașina de stări a livrabilului | verificat local (Postgres real, două conexiuni concurente); componentele reale care mută starea apar din F3 | `tests/unit/test_productie_stari.py`, `tests/integration/test_productie_tranzitii.py`, `tests/isolation/test_productie_rls.py` |
| F2.4 Limite anti-buclă | verificat local (Postgres real, motor durabil în proces); pragurile sunt valori de pornire, nemăsurate; alerta critică nu a plecat pe canale reale | `tests/unit/test_productie_limite.py`, `tests/integration/test_productie_limite.py`, `tests/integration/test_productie_proba.py`, `tests/integration/test_productie_panou.py` |
| F2.8 Cererile de aprobare | verificat local (Postgres real, motor durabil, rute HTTP); notificările către client și portalul vin cu F7 | `tests/integration/test_productie_aprobari.py`, `tests/integration/test_aprobari_panou.py`, `tests/integration/test_productie_proba.py`, `tests/isolation/test_aprobari_rls.py` |
| F2.10 Nivelurile de autonomie | verificat local (Postgres real, motor durabil); promovarea automată L1 → L2 și acordul clientului nu sunt construite; nu există încă detectarea unui incident critic | `tests/unit/test_productie_autonomie.py`, `tests/integration/test_productie_autonomie.py`, `tests/isolation/test_autonomie_rls.py` |
| F2.9 Ecranele Producție și Operare | verificat local prin teste HTTP (rute reale, Postgres real, motor durabil, flux de probă SIMULAT); nu s-au văzut pe telefon sau în Chromium | `tests/integration/test_productie_ecrane.py` |
| F2.5 Executorul de efecte externe | verificat local (Postgres real, procese reale cu SIGKILL, motor durabil); conectorul este FALS, niciun conector real și nicio rețea; alerta de reautorizare nu a plecat pe canale reale | `tests/integration/test_efecte.py`, `tests/chaos/test_efecte.py`, `tests/isolation/test_efecte_rls.py`, `tests/unit/test_garda_efecte.py` |

## De verificat la migrarea pe VPS

- F0.4: măsurarea VPS-ului, refacerea tabelului 6.4, PD1.
- F1.8: `infra/vps/bootstrap.sh` pe un VPS real; Docker rootless cu porturile 80/443; certificatele Let's Encrypt; clientul de registru față de GHCR; fluxul `entrega.yml`; `migrate` cu migrările reale; subdomeniile și secretele din GitHub.
- F1.9: destinația externă reală a backupului (furnizor, capacitate, termeni); prima restaurare de test pe server; fixarea versiunilor pachetelor `apt` din imaginea de backup.
- F1.5: autentificare de pe telefon, cu aplicația de coduri, pe HTTPS (cookie-uri `__Host-`).
- F1.7: instalarea panoului pe telefon (Android și iOS), abonarea și primirea unei notificări push reale (cheile VAPID se generează cu `scripts/genereaza_vapid.py`); apelul real `pywebpush` nu a rulat niciodată.
- F1.8 (panou): promovare și revenire cap-coadă cu deployer-ul real; citirea volumului real `backup_status`.
- F1.10: crearea botului, `setWebhook` cu secretul, comenzile din conversația reală a proprietarului.
- F2.1: serviciul `worker` din compose pe un VPS real (politica `restart: unless-stopped` după o cădere reală, `stop_grace_period`); mutarea workerului de către deployer-ul real; limita de memorie a workerului sub joburi reale; numărul de conexiuni la Postgres sub încărcare; promovarea `AMA_MOTOR_VERSIUNE` la un flux modificat cu joburi în lucru.
- F2.2: numărul real de culoare grele (`AMA_CULOARE_GREU`) pentru nucleele VPS-ului; două procese worker pe aceleași cozi (limita globală); ferestre de rată de ordinul orelor.
- F2.6: un job programat cu cron de minut rulează la minut pe staging, ore întregi; comportamentul cu doi workeri; ora României peste trecerea la ora de vară (martie), pe date reale.
- F2.7: `restart: unless-stopped` pe worker după un SIGKILL real (Docker) și healthcheck-ul `python -m app.worker --verifica` (un container `unhealthy` nu se repornește singur: de decis un sidecar); notificările push/Telegram la repornire repetată, job blocat și cauză care crește, trimise pe canalele reale; prag de 3 căderi/oră, 5 intrări/cauză și timp maxim de 1800 s calibrate pe date reale; observator extern pentru cazul „niciun worker nu rulează”; scanarea cu mii de joburi în `dbos.workflow_status` (retenție).
- F2.5: un conector real (F9) față de executor: `verifica` după timeout pe o platformă reală, consistența căutării după cheie, limitele de rată pe coada platformei; încuietoarea de sesiune cu doi workeri pe aceeași bază; jobul `efecte.tic` la minut pe staging; pragurile de reîncercare (3 × 2 s × 2) calibrate pe platforme reale.
- F2.9: ecranele Producție și Operare pe un telefon real (disponibilitatea butoanelor la o mână, lizibilitatea tabelelor late), cu date reale; reîmprospătarea HTMX la 10 s sub încărcare.
