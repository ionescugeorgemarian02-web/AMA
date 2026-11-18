# FT.2 Firul de corelare și urmele componentelor

- **Pasul:** FT.2 (sesiunea A). Depinde de FT.1. Fără migrare.
- **Gata când:** o cerere care pune un job în coadă, jobul și jobul-copil pus de el împart același fir, iar fiecare
  urmă își are cauza (urma-părinte); gateway, porțile cascadei, porțile Creierului, conectorii HTTP, aprobările,
  gardianul de buget al reclamelor și evenimentele de domeniu (agenți, efecte, livrabile) lasă urme.
- **Hotărâri (D-018).**
  - Motor: `trimite` scrie `motor/trimis:<flux>` (obiect = jobul) cu firul și cauza curente; la pornire, fluxul
    citește acea urmă și continuă firul (altfel firul = id-ul jobului), iar execuția e `span("motor", "flux:<nume>")`.
    Clientul urmei = parametrul `tenant_id` al fluxului. Reluarea după cădere poate repeta urma fluxului (acceptat).
  - Evenimentele de domeniu (`evenimente.emite`) se oglindesc în urme, în aceeași tranzacție; rezultatul se deduce
    din tip (`respins`, `esuat`, `blocat`, `amanat`), motivul din `date.motiv`.
  - Gateway: o urmă pe apel (cost umbră, durată, model, tokeni, cod de eroare; refuzurile de buget/cotă = `respins`
    sau `amanat`). Cascada: o urmă pe poartă (`blocat`/`respins`/`ok`, motivul = instrucțiunile). Creier: aprobări,
    propuneri, retrageri și porțile picate (scrise separat, rămân chiar dacă tranzacția se anulează).
  - Conectori (`ClientHttp`): metoda, gazda, calea, statusul (429 = `amanat`, 4xx = `respins`, 5xx/rețea = `esec`).
  - Aprobări: `aprobare/decizie:<hotarare>` cu motivul standard. Reclame: `buget/gardian:<tip>` cu motivele refuzului.
- **Teste:** `tests/integration/test_urme_propagare.py` (+ fluxurile `tests/integration/fluxuri_urme.py`).
- **NEVERIFICAT:** clienții HTTP care nu trec prin `ClientHttp` (Telegram, cercetare) nu lasă încă urme de conector.
