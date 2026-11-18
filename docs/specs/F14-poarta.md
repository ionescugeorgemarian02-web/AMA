# Poarta F14 — Învățare, a doua treaptă

- **Criteriul** (`docs/23` §23.17): un prompt optimizat a bătut campionul, a fost promovat și a fost măsurat
  față de grupul de control.
- **Cum se verifică** (`tests/integration/test_poarta_f14.py`, un singur test cap-coadă, pe componentele reale):
  1. Un campion (prompt de hook-uri, schema reală `PropunereHookuri`) și promptul real de reflecție din
     `prompts/invatare.reflectie.v1.md`, pe un profil al cărui model e un furnizor SIMULAT prin HTTP
     (`FurnizorFals`): toate apelurile trec prin gateway (bugete, jurnal, urme).
  2. Optimizatorul, pe setul de aur `continut.hookuri`: reflecția propune două instrucțiuni, fiecare devine o
     ciornă, cea mai bună pe antrenare bate campionul pe test cu marja, fără să piardă la conformitate (G10).
     Numărul de apeluri la model e exact cel așteptat (reflecția, 3 versiuni pe antrenare, 2 pe test).
  3. Promovarea prin jobul zilnic (`promovare.ruleaza`): umbra (20 de livrabile, candidatul produce în paralel),
     canarul (~10%), producția (candidatul activ în registru, ~90%), cu testul A/B formal declarat la intrare
     (ipoteza, efectul minim, mărimea eșantionului).
  4. Măsurarea: 10% din livrabile rămân pe campionul vechi; la eșantionul declarat, verdictul automat al
     testului e „câștigă B” cu p < α; promovarea devine `promovat`, cu câștigul scris; rutarea se încheie.
  5. Urmele, în ordine: `optimizeaza`, `etapa_umbra`, `etapa_canar`, `declara`, `etapa_productie`, `verdict`,
     `etapa_promovat`.
- **Livrabilele sunt SIMULATE:** fiecare primește un exemplu din setul de aur, se produce prin gateway cu
  versiunea rutată și se scorează cu criteriile și validatorul de limbă, în locul verdictului cascadei
  (`ruteaza` / `observa` nu sunt încă legate în autorii din F6: NECONECTAT).
- **Rezultat:** trecută pe simulare (vezi `STARE.md`); revenirea dintr-o atingere e verificată în F14.2.
