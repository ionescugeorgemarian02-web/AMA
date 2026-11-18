# FS.3 Comenzi și clienți

- **Context:** FS.1/2, docs/23, F12.1/2; CRM-ul agenției nu este CRM-ul tenantului.
- **Ce se construiește:** comenzi pentru analiză, clienți ai magazinului cu email criptat, consimțământ explicit; actualizări idempotente și versionate.
- **Ce nu:** trimitere email, import în CRM agenție, inferarea consimțământului din cumpărare.
- **Date:** comert_date, cheie tenant/magazin/tip/id, JSONB fără email în clar; email AES-GCM AAD tenant/magazin/id; versiune UTC.
- **Acceptare:** comandă repetată un singur rând; sumă zecimală exactă; email criptat; fără consimțământ nu apare pentru marketing; retragere elimină eligibilitatea; alt tenant nu vede datele.
- **Riscuri:** date protejate Shopify, retragere și evenimente vechi. Ordinea prin updated_at, fără overwrite la egalitate.
- **Module:** app/comert, conector comerț, migrare 0122, teste.
- **Depinde:** FS.2. **Deblochează:** FS.4/5. **Revizuire:** da, sesiunea A.
- **Întrebări:** niciuna; conectarea la CRM tenant viitor este API de citire, nu CRM-ul agenției.

## Revizuire A — 2026-11-18
Sumele și rambursările de import sunt exprimate în unități majore în contractul simulat
(inclusiv câmpul istoric rambursat_bani), convertite exact după ISO 4217 în unități minore.
Lista SIX 2026-09-17 este păstrată local în iso4217.json; monedele fără exponent sunt refuzate.
Importul întoarce identificatorii rândurilor invalide și continuă lotul; sincronizarea
marchează eroare parțială după procesarea loturilor. creata_la este și coloană timestamptz,
validată cu fus orar și normalizată UTC.
