# FS.6 Poarta Shopify

- **Context:** FS.1–5, docs/23. Exclusiv magazin simulat; nu validează operații reale.
- **Construiește:** tests/integration/test_poarta_fs.py, OAuth→HTTP→catalog/comenzi/clienți→HMAC→consimțământ→atribuire→panou. Completează catalogul cu descriere, handle, imagini și variante pentru consumatorii conținut/reclame.
- **Nu:** acces real, înregistrarea webhook-urilor, integrarea F10/F12 dincolo de API public, merge PR.
- **Date:** migrare 0124 adaugă JSONB detalii catalog, compatibilă; whitelist pentru câmpuri comerciale.
- **Acceptare:** schimb OAuth semnat; token criptat folosit prin antet; catalog complet cu variante; eveniment duplicat nu dublează; acord retras elimină clientul CRM; venit atribuit în luna UTC; panou afișează succes fără secrete; acces între tenanți refuzat.
- **Riscuri:** simularea nu dovedește contractul Admin API real; toate operațiile reale în STARE „De verificat la migrare”.
- **Module:** zona C, teste și specificații; comune doar adăugări.
- **Depinde:** FS.1–5. **Deblochează:** revizuire A și migrare VPS.
- **Revizuire obligatorie:** da, alt model pentru OAuth/RLS/cifre; sesiunea A înainte de integrare.
- **Întrebări:** niciuna. make check complet o singură dată aici, fără pytest concurent.

## Surse oficiale consultate

- https://shopify.dev/docs/apps/build/authentication-authorization/authenticate-standalone-apps?lang=node
- https://shopify.dev/docs/apps/build/webhooks/verify-deliveries

Skill folosit: shopify:shopify (referința admin și căutarea documentației oficiale).
Nu s-au generat operații GraphQL; helper-ele locale ale skillului nu sunt instalate în mediu.
Validarea executabilă folosește teste HTTP locale, ruff, mypy și gărzi; nu se pretinde validare a API-ului real.
