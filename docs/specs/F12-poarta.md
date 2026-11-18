# Poarta F12 — CRM, email, inbox

- **Poarta (docs/23 §23.15):** un lead real parcurge drumul de la audit la apel programat.
- **Cum se verifică (D-007, D-024):** `tests/integration/test_poarta_f12.py`, cap-coadă pe simulare (cutia
  poștală, motorul de audit; timpul secvenței e mutat înainte):
  1. formularul de audit → confirmarea adresei → lead cu sursă și temei → raportul de audit;
  2. secvența de după audit: pașii 1–3 prin `crm.email.trimite` (cu dezabonare); pasul 3 duce la programare;
  3. din linkul din email, de pe telefon: calificarea (de sunat azi) și rezervarea → același lead, „apel
     programat”, invitația .ics primită, sarcina pentru om, acordul de email neatins;
  4. secvența se oprește singură; proprietarul vede lead-ul și calificarea în `/crm`; urmele leagă pașii.
- **Ce nu dovedește:** un lead **real** (persoană reală, furnizor de email real, domeniu cu SPF/DKIM/DMARC,
  motorul de audit BigBrain): rămâne în STARE „De verificat la migrare (F12)”. Inboxul (F12.7–F12.8), oferta
  (F12.6), conturile-țintă (F12.9) și suportul (F12.10) au testele lor de pas.
- **Rezultat:** `make check` complet, verde (vezi JURNAL).
