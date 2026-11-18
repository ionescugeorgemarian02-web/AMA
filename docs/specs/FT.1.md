# FT.1 Jurnalul unic de urme (append-only)

- **Pasul:** FT.1, faza FT „Trasabilitate totală” (sesiunea A; plan §„Adăugiri cerute de proprietar”). Migrarea `0076`.
- **Gata când:** orice componentă scrie o urmă (cine, ce, de ce, intrări/ieșiri rezumate, cost, durată, rezultat,
  id de corelare, cauza); rolul aplicației nu poate modifica sau șterge urme; clientul vede doar urmele lui;
  nicio parolă, token, email sau telefon nu ajunge în clar în jurnal.
- **Hotărâri (D-018).**
  - Tabelul `urme`: `corelare_id` (firul unei cereri/al unui job, din `app.logging.correlation_id`), `cauza_id`
    (urma-părinte, din contextul curent), `componenta`, `actiune`, `actor`, `motiv`, `rezultat`
    (`ok|esec|respins|amanat|blocat|info`), `cod`, `cost` + `unitate_cost`, `durata_ms`, `intrari`, `iesiri`, obiectul.
  - Doar adăugare: `GRANT SELECT, INSERT` pentru `ama_app` (UPDATE/DELETE/TRUNCATE revocate) și declanșatorul
    `ama_jurnal_doar_adaugare` (refuză și pentru proprietar). RLS: clientul își vede urmele, agenția pe toate.
    Fără FK spre `clienti`, ca o urmă să nu blocheze sau să nu fie blocată de tranzacția apelantului.
  - Două căi: `inregistreaza(db, …)` în tranzacția apelantului (punct de salvare: o urmă ratată nu strică acțiunea)
    și `emite(…)` în tranzacție proprie, „cel mai bun efort” (componente fără sesiune: gateway, conectori, motor).
  - `span(...)`: măsoară durata, prinde rezultatul (excepția = `esec` cu tipul ei), iar urmele din interior îl au
    drept cauză. `corelare(...)` pornește un fir nou dacă nu există.
  - Rezumatul (`rezuma`): chei care par secrete → `[ascuns]`; emailuri, telefoane, CNP, IBAN, carduri → mascate;
    texte tăiate la 200 de caractere, liste la 20, adâncime 4.
  - `AMA_URME_ACTIVE=false` oprește scrierea (diagnostic).
- **Teste:** `tests/unit/test_urme_rezumat.py`, `tests/integration/test_urme_jurnal.py`, `tests/isolation/test_urme_rls.py`.
- **NEVERIFICAT:** volumul pe VPS (retenție și partiționare: la migrare).
