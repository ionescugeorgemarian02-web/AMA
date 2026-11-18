# Poarta FT — Trasabilitate totală

- **Criteriul (plan, §„Adăugiri cerute de proprietar”):** o lună simulată produce un raport care explică fiecare eșec
  până la evenimentul-sursă.
- **Cum se verifică (simulare accelerată, ca D-014):** `tests/integration/test_poarta_ft.py`, cu componentele reale:
  - 30 de zile; sursa fiecărei zile e urma planificatorului, care pune în coadă jobul zilei (motorul real, executor
    în proces). Jobul publică printr-un `ClientHttp` real spre o platformă SIMULATĂ (500 în zilele 3, 10, 17, 24;
    429 în zilele 5, 15, 25; 400 în ziua 8) sau, în zilele 4, 13, 22, emite un refuz de tranziție al producției.
  - O cerere care trimite un brief gol: poarta reală a Creierului o oprește.
  - Raportul lunii (`analiza.genereaza`) e cel salvat și arătat în `/urme`.
- **Ce trebuie să fie adevărat:** fiecare eșec are lanțul neîntrerupt de la o sursă fără cauză până la el și o
  explicație; fiecare job căzut își are cauza probabilă în conector, cu statusul platformei; refuzurile au motivul;
  poarta Creierului apare la „porți picate”; indicatorii conectorului numără eșecurile.
- **Rezultat:** trecută pe simulare; raportul se calculează pe clientul simulat (`analizeaza(..., tenant_id=)`). `make check`: vezi `JURNAL.md`.
- **Rămâne la migrare:** o lună reală pe VPS (volum, durata analizei, pragurile [I]).
