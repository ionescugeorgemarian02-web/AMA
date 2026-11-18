# FS.2 Catalog Shopify

- **Context:** FS.1, docs/23; ADR-02/07/14. API simulat exclusiv local.
- **Ce se construiește:** catalog normalizat persistent, paginare HTTP injectată, upsert, tombstone la ștergere; verificare HMAC SHA256 base64 pe octeții webhook înainte de parsare.
- **Ce nu se construiește:** scriere produse în Shopify, API real, generare de conținut/reclame.
- **Contracte:** comert_produse (tenant, magazin, id extern, titlu, activ, versiune UTC); unic tenant/magazin/id. Evenimentele vechi nu înlocuiesc versiunea mai nouă. Tranzacție atomică per lot.
- **Teste de acceptare:** HMAC valid acceptat; HMAC greșit nu scrie; produs repetat nu dublează; versiune veche ignorată; ștergere păstrează tombstone; tenant străin nu vede catalogul.
- **Riscuri:** webhook în dezordine, reluare, corp prea mare (limită 1 MB), paginare infinită (limită 100).
- **Module:** comerț, conector comerț, migrare 0121, teste proprii.
- **Depinde de:** FS.1. **Deblochează:** FS.3/FS.5 și consumatori prin API public.
- **Revizuire obligatorie:** da, izolare și HMAC, sesiunea A.
- **Întrebări:** niciuna; ștergerile reale și forma livrării se verifică la migrare.
