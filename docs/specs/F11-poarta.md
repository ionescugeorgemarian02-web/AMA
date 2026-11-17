# Poarta F11 — „o lecție promovată și una retrasă, ambele cu urmă completă”

**Stare: trecută pe date simulate.** Lanțul întreg rulează într-un singur test, prin panou.

| Cerință | Stare | Dovadă |
| --- | --- | --- |
| Reflectorul propune o lecție din postări măsurate, cu dovezi | verificat (postări simulate) | `tests/integration/test_poarta_f11.py`, `test_invatare_reflector.py` |
| Omul o promovează din panou și lecția intră în contextul autorului | verificat | `tests/integration/test_poarta_f11.py` |
| Omul anulează promovarea din panou și lecția iese din context | verificat | `tests/integration/test_poarta_f11.py` |
| Urma completă: lotul, dovezile, cine și când a decis, motivul, jurnalul | verificat | `tests/integration/test_poarta_f11.py` |
| Retragerea automată când lecția a dăunat mai mult decât a ajutat | verificat | `tests/integration/test_invatare_curator.py` |
| Învățarea nu poate atinge regulile validatorilor | verificat (declanșator în bază) | `tests/integration/test_invatare_constitutie.py` |
| Lecții din postări reale ale unui client | **neverificat: cere date reale (migrare)** | `STARE.md`, „De verificat la migrare (F11)” |

Pașii F11.1–F11.6 sunt închiși. Ce NU s-a construit în F11 și e spus în specificații: Reflectorul nu citește
diferența dintre ciornă și textul editat de om; lecțiile asemănătoare nu se unesc; sloturile de publicare nu se
mută singure după recomandare; experimentul observă, nu repartizează variantele; indicatorii de gardă nu sunt
conectați la date; rulările optimizatorului și seturile de aur în timp țin de F14.
