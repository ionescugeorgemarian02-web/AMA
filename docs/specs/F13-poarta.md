# Poarta F13 — Reclame, Strateg, Consiliu

- **Criteriul (`docs/23` §23.16):** oprirea de urgență este testată pe o campanie reală și nicio schimbare nu a trecut
  de plafoane.
- **Cum se verifică (D-014, simulare accelerată):** `tests/integration/test_poarta_f13.py`.
  1. Campania de probă a agenției rulează 14 zile (plan aprobat → construcție în pauză → verificare înainte de lansare →
     activare de către om → citire, supraveghere, test creativ, executor zilnic, Strategul săptămânal): nicio anomalie.
  2. Încercări de a trece de plafoane din toate sursele (Strateg, Consiliu, regulă, om): toate refuzate, cu „cere
     aprobarea clientului”; niciun refuz nu are efect la platformă.
  3. Ziua 15, ora 6: cheltuiala depășește de trei ori ritmul planificat → oprirea globală `reclame`, pauza tuturor
     campaniilor la platformă (nimic nu mai cheltuie), un singur anunț CRITIC; sub oprire nimic nu repornește.
  4. `raport.depasiri` pe toată perioada: gol; toate schimbările aplicate au verdictul favorabil al gardianului;
     orice efect `reclama` provine dintr-o propunere aprobată.
  5. Repornirea e manuală: oprirea se ridică de om; campaniile rămân în pauză; cheltuiala de dinainte nu reoprește.
- **Rezultat:** trecută pe simulare (platforma de reclame SIMULATĂ, restul real).
- **Rămâne la migrare:** conturile reale Meta și Google Ads (App Review, developer token), campania reală de 14 zile cu
  bani reali, oprirea de urgență exersată pe ea, un dosar de Consiliu real deschis în Claude, calibrarea pragurilor.
