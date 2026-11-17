# Poarta F10 — „un raport lunar complet, din date reale, fără cifre introduse manual”

**Stare: parțială.** Ce se poate dovedi fără conturi reale este dovedit; restul e la migrare.

| Cerință | Stare | Dovadă |
| --- | --- | --- |
| Cifrele se citesc singure, la intervale | verificat pe platformă simulată | `tests/integration/test_analiza_colector.py` |
| Raportul lunar se compune din aceste cifre, fără introducere manuală | verificat | `tests/integration/test_analiza_etichete.py` (raportul cu 4 postări, 4000 de afișări) |
| Cifrele din text sunt verificate („G2 pe cifre”) | verificat | `tests/unit/test_analiza_raport_cifre.py` |
| „Din date reale” (conturile agenției) | **neverificat: cere conturi și aprobări API** | `STARE.md`, „De verificat la migrare (F10)” |

Pașii F10.1–F10.8 sunt închiși pe simulări (vezi `STARE.md`). Ce NU s-a construit în F10 și e spus în specificații:
formularea cu model a unghiurilor (C2, C3), autorul de insight cu model (K3), alerta automată la client „în risc”.
