# FT.3 Indicatorii pe componentă

- **Pasul:** FT.3 (sesiunea A). Depinde de FT.1–FT.2. Fără migrare.
- **Gata când:** pentru orice interval (o lună) și opțional un client, fiecare componentă are: volumul, numărul
  pe rezultat, rata de eșec, costul pe unitate, durata p50/p95 și cele mai frecvente 5 coduri de eșec/amânare.
- **Hotărâri (D-018).**
  - Rata de eșec = (eșec + respins + blocat) / urmele cu verdict (fără `info`, de pildă `motor/trimis`).
  - Costul se adună separat pe unitate (`usd_umbra`, `lei`, `usd`), nu se convertește.
  - Calculul e SQL în bază (`percentile_cont`), sub RLS: clientul își vede doar indicatorii lui.
- **API:** `urme.indicatori.calculeaza(db, de_la, pana_la, tenant_id=None) -> list[Indicator]` (`ca_dict()` pentru export).
- **Teste:** `tests/integration/test_urme_indicatori.py`.
- **Notă:** commitul FT.2 lăsase trei rânduri prea lungi și un import nesortat (lint); reparate aici.
