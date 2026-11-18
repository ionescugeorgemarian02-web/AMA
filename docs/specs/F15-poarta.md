# Poarta F15 — Întărire și lansare

- **Criteriul** (`docs/23` §23.18): testele de avarie trec pe staging, nu rămâne nicio problemă critică de
  securitate, platforma se reface din backup în ținta de timp, juridicul e revizuit, pilotul trece patru săptămâni
  fără incident critic cu aprobarea din prima > 85%, lista 25.5 e bifată integral.
- **Cum se verifică pe simulare** (`tests/integration/test_poarta_f15.py`, un test cap-coadă, componente reale):
  1. catalogul de avarie are cele 14 scenarii; un raport 14/14 „de pe staging” (SIMULAT) bifează T1;
  2. exercițiul de restaurare real (backup -> mediu curat -> verificare) trece în 4 h;
  3. trei clienți la L1 cu preț de pilot, patru săptămâni (SIMULAT: începutul mutat cu 27 de zile), aprobări prin
     fluxul real (90% din prima), feedback săptămânal, raportul săptămânal: poarta pilotului trece la toți;
  4. două studii de caz din cifrele pilotului, publicate cu acord; lista 25.5 calculează T1, Q2, Q3, C2, C6 bifate și
     C1 (avocat), C7 (audit simulat) nebifate: lansarea rămâne oprită, cum trebuie fără resurse reale.
- **Securitate:** revizia pe Sonnet (F15.2) nu mai are probleme CRITIC sau MEDIU deschise (colecția `tests/atacuri/`).
- **Rezultat:** trecută pe simulare; `make check` complet (vezi `STARE.md`). Bifarea reală a listei rămâne „De
  verificat la migrare” (staging, avocat, contabil, clienți-pilot reali).
