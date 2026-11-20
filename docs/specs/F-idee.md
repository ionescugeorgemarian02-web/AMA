# F-idee — gândirea și validarea ideii, cu imagini reale

Sursa: verdictul proprietarului din 2026-11-20 asupra demonstrației Spița („foarte slabă; trebuiau imagini reale cu un
lanț și o bicicletă în mișcare, să reflecte realitatea; refă partea de gândire și validare a ideii”). Decizia: D-032.

## Ce era greșit
1. Lipsea etapa de **idee**: brieful trecea direct în text, iar vizualul venea la urmă, ca decor.
2. Nimeni nu întreba dacă materialul **reflectă realitatea**: ce trăiește clientul, ce se întâmplă cu adevărat cu bicicleta.
3. Cadrele erau **obiecte statice** (o piesă, un document), nu momente reale, nu acțiune.
4. Nu exista **sursă de imagini reale**: lipsea stock-ul real, video cu atât mai mult.

## Fluxul nou (înaintea briefului de livrabil)

**1. Momentul real** (`app/continut/idei.py`, promptul `continut.idei@1`). Din brieful clientului, publicul aprobat,
oferta și fapte, modelul propune **5 concepte**. Fiecare concept are:
- `moment_real`: o situație concretă din viața clientului, cu loc, timp și acțiune. De exemplu: „după o tură prin ploaie,
  lanțul scârțâie la urcare și schimbătorul sare”.
- `tensiune`: ce simte sau pierde omul în acel moment.
- `mesaj_unic`: o singură idee, nu trei.
- `dovada`: faptul aprobat care o susține.
- `de_ce_acum`: sezon, context, urgență reală.
- `cadre`: 4–7 cadre, fiecare cu **subiect concret + acțiune vizibilă + context**, plus tipul (`video`/`foto`), încadrarea
  și 2–3 interogări de stock în engleză. Exemplu: `{"subiect":"lanț de bicicletă","actiune":"se rotește pe pinion, cu
  stropi de apă","context":"stradă udă","tip":"video","incadrare":"prim-plan","interogari":["bicycle chain wet rotating",
  "cycling rain close up"]}`.
- `material_propriu`: cadrele care trebuie să arate atelierul sau oamenii reali ai clientului (stock-ul nu poate
  pretinde că este clientul).

**2. Critica** (`continut.critica_idee@1`, alt model decât autorul atunci când există; cu un singur model, rezultatul se
marchează „autoevaluare”). Fiecare concept primește note de la 1 la 5 pe criterii fixe:
- specificitate;
- realism (reflectă ce se întâmplă cu adevărat);
- relevanța pentru ofertă;
- fezabilitatea vizuală (cadrele se pot găsi sau filma);
- noutatea față de materialele anterioare;
- onestitatea (nicio promisiune fără dovadă, niciun stock prezentat drept client).

Critica scrie și obiecții concrete și o versiune îmbunătățită a celui mai bun concept.

**3. Validarea deterministă** (`probleme_concept`), pe conceptul ales:
- fiecare cadru are un substantiv concret și un verb de acțiune;
- la video, cel puțin 60% din cadre au mișcare;
- cel mult un cadru doar cu text (CTA);
- fără cadre „doar obiect” la majoritate;
- `dovada` trimite la un fapt aprobat;
- cadrele din `material_propriu` nu se acoperă cu stock.

Un concept respins se rescrie o singură dată cu obiecțiile; dacă pică din nou, merge la om.

- cadrele de stock nu cer continuitate de personaj sau loc („același biciclist”, „aceeași intersecție, a doua zi”)
  și nici reacții jucate („pietonii întorc capul”): acelea sunt material propriu sau filmare regizată;
- un cadru de stock pe care criticul îl obiectă pentru fezabilitate sau onestitate (îl numește și spune că nu se
  găsește, nu se poate filma, e prezentat drept altceva sau pretinde continuitate) pică validarea.

**4. Alegerea:** scorul criticii (cu realismul, onestitatea și fezabilitatea eliminatorii sub 3) plus validarea.
Varianta îmbunătățită de critic e candidat dacă trece validarea: scorul ei estimat sunt notele conceptului din care
vine (obiecțiile acelea nu i se mai aplică) și, la scor egal, întrece conceptele propuse. Conceptul ales intră în
brieful livrabilului (`idee`), iar scriptul și postarea se scriu **din concept**, nu din subiectul calendarului.

## Imagini reale
- `app/media/stock_commons.py` aduce stock real fără cheie din Wikimedia Commons, **foto și video** (webm/ogv convertit
  la mp4). Licențe acceptate: CC0, domeniu public, CC BY, CC BY-SA. Autorul și licența se salvează ca atribuire.
  Interogările vin din `cadre[].interogari`.
- `app/media/stock_pexels.py` și `stock_pixabay.py` sunt adaptoare gata pentru cheie (`PEXELS_API_KEY`,
  `PIXABAY_API_KEY`). Au mai multe filmări verticale de calitate. „De verificat la migrare.”
- Selecția pe cadre preferă video pentru cadrele cu acțiune și decupează vertical cu subiectul protejat. Un cadru fără
  potrivire reală devine o cerere de material, nu animație sau siglă.

## Demonstrația
Testul `test_idee_spita.py` și jobul CI `idee` (cu artefacte):
- ideile, critica, conceptul ales și motivul alegerii;
- cadrele găsite (video real cu bicicleta în mișcare și lanțul) și atribuirile;
- MP4-ul vertical, imaginea de feed, planșa și verdictul editorial.

Ideile se produc cu modelul real atunci când `ANTHROPIC_API_KEY` există, în pilot. Altfel se folosesc ideile înregistrate
dintr-o rulare reală prin puntea orchestratorului (`tests/date/idei/spita.json`), cu prompturile platformei. Fișierul spune
explicit ce model le-a scris.
