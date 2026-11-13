# Poarta F6 — prima versiune utilizabilă intern

- **Criteriul** (`docs/23` §23.9; `docs/25` §25.4, poarta de lansare 1): fazele F1–F6 încheiate; 14 zile de producție pentru
  brandurile proprii fără incident critic; primul val de cereri din F0 trimis; backup testat.
- **Cum se măsoară local:** `tests/integration/test_poarta_f6.py` parcurge lanțul complet pe brandul FICTIV „Cafeneaua
  Zorilor”, cu acțiunile omului prin rutele reale ale panoului: calendar pe 30 de zile aprobat din ecran (21 de sloturi) →
  briefuri cu fapte permise pentru toate sloturile → postare prin fluxul durabil, validată de cascada reală (cu o reparație)
  → script video în durata-țintă → adaptări pe Instagram, LinkedIn și TikTok în limite → aprobare din birou → pachet pe
  `/publicare` → link lipit → „Publicat”, verificat fără incident → respingere din birou devenită exemplu negativ în
  promptul sarcinii următoare → proba de 14 zile pe două branduri proprii (fictive), la L1, zilnic, fără incident critic,
  cu rata de aprobare din prima măsurată.
- **Rezultat (local, 13.11.2026): TRECUTĂ pe simulare** (modele FALSE, branduri FICTIVE, om simulat; D-007). Proba F6.8:
  32 de livrabile în 14 zile, 0 incidente critice, rata de aprobare din prima 0,75 (dată de omul simulat).
- **Restul condițiilor porții de lansare 1:** F1–F6 închise în CI / local (`docs/specs/STARE.md`); backupul e verificat local
  (F1.9, `tests/integration/test_backup_restore.py`), restaurarea pe VPS rămâne la migrare; primul val de cereri F0 cere
  conturi reale (la migrare).
- **De verificat la migrare (deschis explicit):** proba reală de 14 zile pe CariereAI și BigBrain cu modelele reale; o
  postare reală publicată din două atingeri de pe un telefon real; rata reală de aprobare din prima; cascada cu judecătorii și
  vectorii reali; primul val de cereri F0; backupul și restaurarea pe VPS. Abia apoi poarta de lansare 1 e trecută „pe bune”
  și pornesc discuțiile de vânzare.
