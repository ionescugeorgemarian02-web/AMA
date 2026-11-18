# FT.4 Analiza lunară automată

- **Pasul:** FT.4 (sesiunea A). Depinde de FT.1–FT.3. Migrarea `0077`.
- **Gata când:** pentru o lună, raportul spune ce a mers bine și prost, regresiile față de luna precedentă, costurile,
  porțile picate, motivele de respingere și, pentru fiecare eșec, lanțul cauzal până la evenimentul-sursă; jobul
  rulează singur pe 1 ale lunii pentru luna încheiată.
- **Hotărâri (D-018).**
  - „Bine”: componentă cu ≥ 5 urme și fără eșecuri, sau rata de eșec scăzută cu ≥ 5 pp. „Prost”: orice componentă cu
    urme rele (eșec, respins, blocat), cu codurile frecvente.
  - Regresie (ambele luni ≥ 5 urme): rata de eșec +5 pp, p95 +50%, cost (pe unitate) +30% [I].
  - Porți picate: componentele `validare` și `creier`, pe acțiune și cod. Motive de respingere: `aprobare` și `buget`.
  - Lanțul: de la eșec, din cauză în cauză (`cauza_id`) până la urma fără cauză = sursa. Părinte lipsă = „lanț
    întrerupt”, iar sursa devine prima urmă a firului. Cauza probabilă: cea mai adâncă primă urmă rea dinăuntrul
    eșecului (de exemplu conectorul care a dat 500 în fluxul eșuat). Fiecare eșec are o explicație în română.
  - Raportul (JSON) se salvează în `urme_rapoarte` (unul pe lună, agenția; regenerarea îl înlocuiește). Detaliate:
    primele 2.000 de eșecuri (`esecuri_netaiate` spune dacă s-a tăiat).
  - Jobul `urme.analiza_lunara`: cron `23 4 1 * *` (ora afacerii), în worker (`MODULE_FLUXURI`).
- **Teste:** `tests/integration/test_urme_analiza.py`.
- **NEVERIFICAT:** pragurile [I] pe volume reale; durata analizei pe o lună reală de pe VPS.
