# Poarta F4 — lanțul verificat local

- **Poarta (docs/23):** „CariereAI și BigBrain au fiecare un Creier de brand și o strategie pe 90 de zile, aprobate.”
- **Stare:** **DESCHISĂ.** Cere materialele și aprobarea proprietarului; nu se poate trece din repo.
- **Ce s-a verificat local** (`tests/integration/test_poarta_f4.py`, durează câteva secunde; brandul fictiv „Cafeneaua Zorilor”, modelul FALS): colectare (site fals, `robots.txt` respectat) → fapte extrase, o parte aprobate de un om →
  interviu → brief complet → ghid de brand (3 variante, alegere, aprobare) → citate (≥ 20) și profil de public aprobat → concurenți, afirmații cu citat și brief de insight cu trimiteri și sondaj → strategie pe 90 de zile cu toate
  elementele, aprobată din ecranul Campanii → pachet de context al unei sarcini care conține ghidul, faptele APROBATE și strategia, fără propunerile neaprobate.
- **Comanda de pregătire** (`tests/integration/test_creier_pregatire.py`): `python -m app.creier.pregatire --client <nume> --site <URL> --recenzii <fișier.txt> --concurent "Nume=URL"` (repetabil), cu `--colecteaza` pentru a porni colectarea.
- **Ce urmează la proprietar.** (1) `python -m app.creier.pregatire --client <nume> --site … --recenzii … --concurent …` pentru CariereAI și pentru BigBrain (creează clientul și sursele); (2) workerul pornit pentru colectare, indexare și
  fluxurile cu model; (3) cheile furnizorilor în mediu și modelele reale activate în „Modele și cote”; (4) interviul din panou (`/onboarding/<client>`), brieful aprobat, ghidul ales și aprobat, citatele și profilul de public aprobat (cel puțin
  20 de recenzii / comentarii reale pe brand), cei 3–5 concurenți, brieful de insight aprobat, strategia aprobată din `/campanii/<client>`; (5) bifarea porții în `STARE.md`.
