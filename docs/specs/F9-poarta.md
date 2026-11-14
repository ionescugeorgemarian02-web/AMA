# Poarta F9 — Publicarea prin API

- **Criteriul (docs/23 §23.12).** Pe fiecare canal aprobat, o postare publică pleacă prin API, o singură dată.
  Canalele neaprobate rămân pe asistat.
- **Testul.** `tests/integration/test_poarta_f9.py`, pe clientul fictiv „Cafeneaua Zorilor” (cont de client, nu
  al agenției): aprobările Meta (pagini, Instagram), auditul YouTube și auditul TikTok „aprobate”, Community
  Management API (pagina LinkedIn) neaprobată. Drumul: OAuth prin executor pe fiecare canal → versiunea aprobată
  (cu fișier unde canalul cere) → alegerea drumului după modul canalului (`programare.alege_drumul`; blogul,
  direct din aprobare) → consimțământul TikTok → `publicare.tic` la minut → efectele, ca joburi durabile pe
  motorul real (în proces) → conectorii → platformele simulate.
- **Ce se verifică.** O singură postare publică pe Facebook (și după un răspuns pierdut, reîncercat de motor cu
  `verifica` întâi), Instagram, YouTube (public), profilul LinkedIn, TikTok (direct, vizibilitatea aleasă) și blog;
  o nouă trecere a „tic”-urilor (programare și executor) nu dublează nimic; starea citită înapoi de la fiecare
  platformă e „publicată”; pagina LinkedIn neaprobată: pachet asistat, niciun efect prin API.
- **NEVERIFICAT / SIMULAT.** Platformele sunt contracte HTTP locale (`tests/platforme/`); modelul articolului e FALS.
  Poarta se repetă la migrare pe conturile reale, după aprobările reale.
