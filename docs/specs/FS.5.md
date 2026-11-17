# FS.5 Ecranul magazinului

- **Context:** FS.1–4, panou server-rendered ADR-13, RLS ADR-14.
- **Construiește:** /comert pentru tenantul activ, magazin conectat, stare/ultima sincronizare și cifre lunare per monedă; sincronizator cu cititori injectați, stare succes/eroare fără secrete.
- **Nu:** buton cu trafic real, aplicație embedded Shopify, acces la alt tenant prin URL.
- **Date:** comert_sincronizari tenant/magazin, stare, ultima reușită UTC. Migrare 0123.
- **Acceptare:** anonim refuzat; client vede doar magazinul propriu; token/email nu apar; cifre separate pe monedă; eroarea păstrează ultima reușită; succesul numără produsele.
- **Riscuri:** XSS (autoescape Jinja), date parțiale (loturile separate, starea eroare explicită).
- **Module:** comerț, teste proprii, adăugări în înregistrare panou și meniu.
- **Depinde:** FS.4. **Deblochează:** FS.6. **Revizuire:** izolare, sesiunea A.
- **Întrebări:** niciuna. Interfața este doar citire în modul simulat.
