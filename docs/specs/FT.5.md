# FT.5 Ecranul „Urme” și exportul

- **Pasul:** FT.5 (sesiunea A). Depinde de FT.3–FT.4. Fără migrare.
- **Gata când:** proprietarul vede în panou raportul lunii (indicatori, bine/prost, regresii, porți picate, motive
  de respingere, eșecurile cu lanțul până la sursă), îl poate regenera, deschide firul unui eșec și exportă CSV/JSON.
- **Hotărâri (D-018).**
  - `/urme?luna=AAAA-LL` (implicit luna trecută): raportul salvat sau, dacă lipsește, calculat acum (spus pe ecran).
    `POST /urme/genereaza` (CSRF) îl salvează. `/urme/fir/<corelare>`: toate urmele firului, cu legătura la cauză.
  - Exporturi: `/urme/export.json` (raportul întreg), `/urme/export.csv?ce=esecuri|indicatori|urme` (toate urmele
    lunii, maximum 50.000 de rânduri).
  - Doar rolul proprietar (urmele traversează toți clienții); legătura în meniu doar pentru el.
  - Ecranul arată primele 200 de eșecuri; exportul le are pe toate cele detaliate.
- **Teste:** `tests/integration/test_urme_ecran.py`.
- **NECONSTRUIT:** filtrul pe client în ecran (API-ul `indicatori.calculeaza` îl are); paginarea firelor foarte lungi.
