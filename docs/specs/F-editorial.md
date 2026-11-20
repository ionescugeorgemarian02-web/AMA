# F-editorial — calitatea editorială a imaginilor și a materialelor video

Sursa: cererea proprietarului din 2026-11-20 („Instrucțiuni pentru Claude privind calitatea editorială”),
după testul „Atelierul Spița”. Pe atunci regizorul primise doar sigla și o pusese în toate cele cinci scene.
Clipul trecuse G6, iar imaginea de feed nu conținea decât text și siglă. Baza de lucru este ramura Codex
`codex/agentie-pilot` (PR #20). Decizia aferentă: D-030 în `DECIZII.md`.

## Decizii

1. **Rolul vizual** e o coloană nouă, `active.rol_vizual`, cu valorile `logo`, `fotografie`, `filmare`,
   `ilustratie`, `coperta`, `export` sau `NULL` (incert). Este separat de `categorie`, care descrie tipul
   fișierului. Lângă el stă `active.subiect`, un text scurt despre ce se vede, de exemplu „transmisie: lanț pe
   pinion”, folosit la potrivire. Migrarea `0142` completează rolul pentru activele existente:
   `sursa='identitate'` primește `logo`, `compozitor` primește `coperta`, `montaj` primește `export`,
   `animatie` primește `ilustratie`, `stock`/`generat` primesc `fotografie` sau `filmare` după categorie. Restul
   rămâne `NULL`. Operatorul clasifică activele cu `biblioteca.clasifica(db, activ_id, rol, subiect)` și din
   panou.
2. **Selecția pentru scene** (`media.selectie`) e deterministă și pură. Filtrează după client, licență validă și
   rol (`fotografie`, `filmare`, `ilustratie`), apoi alege după subiect: potrivirea cuvintelor normalizate,
   fără diacritice și pe prefix, dintre indicația vizuală a bătăii și `subiect` + `descriere`. Sigla, coperțile
   și exporturile nu intră niciodată în scene. Sigla poate apărea doar în semnătură, adică în închiderea
   clipului.
3. **Storyboardul** (`regizor.storyboard`) se construiește ÎNAINTE de voce și montaj. Fiecare scenă are:
   replica, subiectul vizual cerut, `activ_id` ales (sau nimic) și motivul alegerii. O scenă fără material
   potrivit:
   - într-un material **educativ**: primește o ilustrație (clipul animat al bătăii) și o notă onestă;
   - într-o **prezentare a afacerii reale** (atelier, produs, echipă, local): blochează livrabilul cu o
     cerere precisă, de forma „Încarcă o fotografie verticală cu {subiect}”. Cererea apare în panou, iar după
     încărcare livrabilul se poate relua.

   Natura materialului vine din brieful vizual: `natura: educativ | prezentare`.
4. **Brieful vizual** extinde brieful livrabilului. Câmpurile noi sunt `idee_editoriala`, `ce_vede_publicul`
   și `informatie_in_plus`, iar pentru video `indicatie_vizuala` pe fiecare bătaie, care trebuie să fie
   observabilă. Validarea respinge indicațiile vagi: fără substantiv concret, sau doar adjective de tipul
   „dinamic”, „premium”, „modern”. Prompturile primesc versiuni noi (`@v3`).
5. **Machete** (în `sabloane` și `compozitor`): `foto_dominanta`, `detaliu_explicat`, `carusel`. Fiecare are
   un sistem tipografic restrâns, cu rolurile titlu, legendă și corp. Poziția titlului se alege după zona cea
   mai liniștită din fotografie (varianța luminozității), iar subiectul e protejat la decupare. Exportul se
   verifică la 360 px lățime: înălțimea literei titlului trebuie să rămână de cel puțin 14 px. Macheta se alege
   din brief și din activele disponibile.
6. **Montaj**: schimbarea cadrului cade pe începutul replicii care îl cere. O scenă care refolosește un activ cu
   alt zoom contează tot ca reutilizare. Durata urmează vocea: nu se prelungește materialul până la 30 s.
   Subtitrările se mută sus când zona subiectului sau prețul stă jos. Pilotul exportă și o **mostră audio**
   (numele afacerii, prețul, îndemnul final), sintetizată cu vocea folosită la randare.
7. **Verdict editorial** (`control.verdict_editorial`), separat de G6. Pe PNG-ul final și pe câte un cadru din
   fiecare scenă a MP4-ului verifică automat:
   - sigla e singurul subiect;
   - același activ e repetat;
   - textul iese din cadru;
   - lipsește material;
   - exportul aparține altei versiuni.

   Relevanța și compoziția le evaluează vizual operatorul sau un model cu imagini. Când e un singur model,
   evaluarea apare marcată „autoevaluare”. Când modelul primește doar text, evaluarea vizuală rămâne
   „neverificată”. La respingere, verdictul dă motivul și etapa de reluat. Ecranul de aprobare arată separat
   G6 și verdictul editorial, plus planșa cu câte un cadru pe scenă.
8. **Demonstrația A/B** e un test determinist (`tests/integration/test_editorial_spita.py`) care rulează în CI
   la fiecare PR și urcă artefactele (jobul `editorial` din `ci.yml`). Textele, oferta de 120 lei și dosarul sunt
   fixe; nu se apelează niciun model. Cazul A are doar sigla: livrabilul e blocat, cu cadrele lipsă enumerate.
   Cazul B are sigla și trei fotografii reale, cu licență liberă, din Wikimedia Commons (licența e documentată
   în `tests/date/spita/LICENTE.md`). Rezultatul B: imagine de feed, carusel, MP4 vertical cu voce și
   subtitrări, storyboard, planșă, G6, verdict editorial și mostra audio.
