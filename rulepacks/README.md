# Pachete de reguli (docs/09 §9.7, docs/21 §21.8–21.12)

Fișiere TOML versionate, **modificabile doar prin revizuire umană** (cerere de integrare). Niciun cod al aplicației nu are voie
să scrie aici (gardă: `tests/unit/test_reguli_garzi.py`), iar optimizatorul nu are drept de scriere. Regulile pe client trăiesc în
baza de date (`reguli_client`), cu autor uman obligatoriu.

- `general.toml`: reguli valabile pe orice canal (sănătate, câștig nerealist, atribute personale, minori, discriminare).
- `<platforma>.toml`: regulile unei platforme (`meta.toml` = Facebook + Instagram, `tiktok.toml`, `linkedin.toml`, `email.toml`).
- `nise/<nisa>.toml`: regulile unei nișe; `se_aplica = "mereu"` pentru nișele refuzate (21.12), `"nisa"` când clientul declară nișa.

O regulă are: `id`, `text`, `potrivire` (`cuvant` | `lista` | `regex` | `calcul` | `obligatoriu`), `tipare`, `severitate`
(`minora` = avertisment, `majora` = blochează și se repară, `critica` = carantină), `sursa` (politica platformei sau legea, cu URL),
`marcaj` (`[I]` = sursa NU a fost verificată de un om, `verificat`), `verificat_la`, cel puțin un exemplu care trebuie blocat
(`exemple_blocate`) și unul care trebuie să treacă (`exemple_trece`). Un test rulează automat exemplele fiecărei reguli.

Tiparele se scriu **fără diacritice și cu litere mici** (textul se compară în această formă; pozițiile fragmentelor se păstrează).
Toate regulile de început sunt `[I]`: sursele (adrese ale politicilor și acte normative) nu au fost verificate de un om, iar
`verificat_la` este data scrierii, nu a unei verificări la sursă.
