# FS.1 Autorizarea Shopify

- **Pasul:** FS.1, conector comerț, sesiunea C.
- **Context:** docs/23 „Adăugiri cerute de proprietar”, ADR-07, ADR-14; tokenuri criptate AES-GCM existente.
- **Ce se construiește:** domeniu myshopify.com validat; stare OAuth unică, expirabilă, legată de tenant și magazin; HMAC callback; schimb HTTP local al codului; token criptat cu AAD tenant/magazin.
- **Ce nu se construiește:** API real, instalare publică, App Review, FS.2–FS.6.
- **Contracte:** comert_magazine (tenant_id, magazin unic per tenant, token criptat, hash stare, termen UTC); contract HTTP simulat injectat. Migrare 0120 din 0077.
- **Teste de acceptare:** domeniu invalid refuzat; stare greșită refuzată; stare expirată refuzată; HMAC invalid refuzat; token legat criptografic de tenant; schimbul codului prin HTTP local.
- **Riscuri:** furt token, CSRF, asociere tenant greșită; starea consumată înainte de schimb, reautorizare la eșec.
- **Module atinse:** app/comert, app/connectors/comert, teste, migrare, documentație comună doar adăugată.
- **Depinde de:** F1 conturi/DB. **Deblochează:** FS.2.
- **Revizuire obligatorie:** da, autentificare și izolare; sesiunea A înainte de integrare.
- **Întrebări deschise:** niciuna; D-C01 fixează simularea, fără acces la magazin real.

Callback-ul primește exclusiv query string-ul brut (bytes), semnează perechile sortate
păstrând encoding-ul și refuză duplicatele, timestamp lipsă/viitor sau mai vechi de 300 s.
