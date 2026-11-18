# Poarta F16 — Extensii (pe simulare)

- **Pasul:** poarta fazei F16 (`docs/23` §23.19, pașii F16.1–F16.6). Sesiunea A, D-026. White-label și al doilea
  server (ultimele două puncte din §23.19) rămân în afara acestei porți.
- **Scenariul cap-coadă** (`tests/integration/test_poarta_f16.py`), pe Postgres real, ffmpeg real, platforme SIMULATE:
  1. clientul e setat pe engleză; textul englez trece G1 și G10 pe regulile englezei;
  2. vorbitorul își dă acordul scris, vocea se antrenează o dată, narațiunea are licența fără probleme;
  3. trei scene devin video format C publicabil (G6), în culorile brandului;
  4. un insert video generat încape în plafon, al doilea e refuzat fără apel;
  5. oferta pleacă pe Pinterest, Google Business Profile și Threads prin executor, o dată pe canal;
  6. campania TikTok apare oprită și pornește doar prin propunere + gardian + executor;
  7. urmele FT conțin `formatul_c`, `video_extern.genereaza`, `voce_proprie.antrenare`.
- **Gata când:** testul porții trece și `make check` complet e verde.
- **Ce nu dovedește:** conturi, aplicații aprobate, bani reali, calitatea vocii și a traducerii (STARE, „De
  verificat la migrare (F16)”).
