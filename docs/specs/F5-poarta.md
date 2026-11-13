# Poarta F5 — validare și aprobări

- **Criteriul** (`docs/23` §23.8, `docs/09` §9.9): cel puțin 95% din materialele intenționat greșite sunt blocate și cel mult
  10% din cele bune sunt respinse pe nedrept.
- **Cum se măsoară:** `tests/integration/test_poarta_f5.py` rulează bancul (F5.7) pe seturile ÎNGHEȚATE din `evaluare/aur/`
  (amprentele din `INGHETAT.toml` se verifică în același test), cu validatorii DETERMINIȘTI (V0–V2), judecătorii (V3 / V4)
  opriți și orice apel la gateway interzis. Pașii V2 care cer vectori prin gateway (G4@V2, G7@V2) sunt omiși și listați.
  Aceeași măsurătoare: `python -m app.validare.banc` sau butonul din `/validatoare`.
- **Rezultat (local, 13.11.2026): TRECUTĂ.** Materiale greșite blocate **107 / 107 (100%)**; materiale bune respinse pe nedrept
  **3 / 63 (4,76%)** — bun-017 („ora 15:00” neacoperită de registru), bun-042 („cea mai închisă”) și bun-060 („cel mai ușor”),
  toate de G2, conservator prin construcție (docs/09 §9.3: o afirmație neacoperită blochează).

| Validator | Materiale greșite vizate: blocate / total (prinse chiar de el) | Set de aur: exemple · TP / FP / FN / TN · precizie · recall · respinse pe nedrept |
| --- | --- | --- |
| G1 Structură | 12 / 12 (12) | 38 · 22 / 0 / 0 / 16 · 100% · 100% · 0% |
| G2 Fapte | 21 / 21 (21) | 40 · 22 / 0 / 0 / 18 · 100% · 100% · 0% |
| G3 Politici | 22 / 22 (21) | 39 · 23 / 0 / 0 / 16 · 100% · 100% · 0% (o severitate: critică în loc de majoră) |
| G4 Ton | 8 / 8 (8) | 33 · 17 / 0 / 0 / 16 · 100% · 100% · 0% |
| G7 Originalitate | 10 / 10 (10) | 31 · 14 / 0 / 0 / 17 · 100% · 100% · 0% |
| G8 Lizibilitate și conversie | 12 / 12 (12) | 32 · 16 / 0 / 0 / 16 · 100% · 100% · 0% |
| G9 Juridic | 12 / 12 (12) | 32 · 16 / 0 / 0 / 16 · 100% · 100% · 0% |
| G10 Limbă | 10 / 10 (10) | 39 · 16 / 0 / 0 / 23 · 100% · 100% · 0% |

- **Înainte de îmbunătățirea validatorilor** (prima rulare a bancului, aceleași seturi): 99 / 107 (92,5%) blocate, 5 / 63 (7,9%)
  respinse pe nedrept — poarta NU trecea. S-au îmbunătățit validatorii (F5.7, hotărârea 7), nu seturile.
- **Independență și limite.** Seturile au fost scrise și înghețate înaintea ajustărilor; nu s-au schimbat (test). Ajustările
  sunt reguli generale, testate pe texte diferite de seturi. Totuși, aceleași seturi au arătat ce lipsea, iar seturile și
  ajustările vin de la același agent: scorul de 100% este OPTIMIST. Măsura independentă vine din exemplele promovate din
  contestații și etichete (F5.8, F5.10) și din textele reale de după migrare.
- **De măsurat la migrare:** poarta cu judecătorii reali (V3 / V4) și cu modelul real de vectori (G4@V2, G7@V2); pe texte reale
  ale brandurilor proprii, anonimizate și promovate în setul de aur.
