# Jurnalul de schimbări

Format: o intrare pe pas, cea mai nouă sus.

## Nelansat

### F6.7 — Capturarea feedbackului
- Respingerile (cu motivul standard și fraza omului) devin exemple negative, aprobările (cu ciorna, dacă omul a editat) exemple de aur, automat, în aceeași tranzacție cu decizia; pachetul de context primește exemplele aceluiași tip și canal (`creier.context.construieste(..., exemple=(tip, canal))`), iar brieful și autorii le văd în prompt.

### F6.6 — Publicarea asistată
- Modulul `app/publicare`: pachetul de publicare asistată se pregătește la aprobare (text final cu hashtag-uri, ora recomandată, dezvăluirea AI, pașii obligatorii, cheia de idempotență din 7.3), ecranul `/publicare` cu butonul „Partajează” (Web Share sau copiere) și formularul pentru linkul postării, verificat pe domeniul canalului; livrabilul trece `programat → publicat`. Tabelul `publicari_asistate` (migrarea `0038`).
- `productie.aprobari`: punctul de extensie după decizie (`inregistreaza_dupa_decizie`).

### F6.5 — Adaptorul pe platformă
- Adaptorul pe platformă (E10): din postarea validată, câte un livrabil nou pe canal (Instagram, LinkedIn, TikTok, Facebook), cu lungimi-țintă native verificate determinist împreună cu G1, o cerere de corectură, apoi validarea obișnuită. Tabelul `adaptari` (migrarea `0037`), prompt `continut.adapteaza@1`.

### F6.4 — Scripturi video
- Scenaristul video (E2): scriptul scurt pe bătăi (voce, text pe ecran, vizual, apel la acțiune) pe hook-ul ales de E1 cu limita video de 7 cuvinte; durata estimată determinist din cuvinte, încadrarea la ±15% din țintă, o singură cerere de scurtare / lungire, altfel coada de erori. Prompt `continut.script@1`.

### F6.3 — Hook-uri și postări
- Generatorul de hook-uri (E1, 3–5 variante pe tipare, alegere deterministă, tabelul `variante_hook`, migrarea `0036`), autorul de postări (E4) în lume închisă, editorul determinist (E8, `date/editor.toml`), lanțul `continut.pipeline` și fluxul durabil `continut.produ` (brief → scriere → validare cu ≤ 2 reparații → aprobare după nivelul de autonomie).
- `validare`: sursele de autori de reparații (`autor.inregistreaza_sursa`), punctul de extensie după validare (`ciclu.inregistreaza_dupa_validare`) și nucleele exportate (`probleme_hook`, `probleme_structura`, `extrage_afirmatii`, `corecteaza_sedila`, `propozitii`).

### F6.2 — Autorul de brief
- Autorul de brief (D5): pentru fiecare slot aprobat, pachetul de context la data publicării, faptele permise alese de model doar dintre cele din pachet (aliasuri F1, F2, … rezolvate la intrarea și versiunea din Creier), restul din slot. Tabelul `briefuri` (migrarea `0035`), prompt `continut.brief@1`, fluxul durabil `continut.briefuri`; livrabilul trece `planificat → briefat`.

### F6.1 — Strategul de conținut și calendarul
- Modulul nou `app/continut`: strategul de conținut (D3) propune piloni, formate pe canal și idei din strategia aprobată (prompt `continut.calendar@1`, profilul `strategie`, flux durabil `continut.calendar`); nucleul determinist `calendar.planifica` așază sloturile pe 30 de zile; aprobarea unui om transformă sloturile în livrabile `planificat`. Tabelele `calendare` și `calendar_intrari` (migrarea `0034`, RLS), ecranul `/calendar/{client}`.

### Poarta F5
- Testul de poartă `tests/integration/test_poarta_f5.py`: pe seturile înghețate, cu validatorii deterministe și fără niciun model, 107 / 107 materiale greșite blocate și 3 / 63 bune respinse pe nedrept; cifrele pe validator în `docs/specs/F5-poarta.md`.

### F5.9 — Biroul de aprobări
- Ecranul `/aprobari` complet, întâi pentru telefon: ordine după urgență, termen și prioritate; card cu previzualizarea pe canal, verdicte și dovezi, pachetul de context, istoricul versiunilor cu diferențe și întrebările către client; respingere cu motiv standard și frază opțională, statistica motivelor; editare pe loc (versiune nouă validată din nou, perechea `asteapta_aprobare → in_validare`, migrarea `0033`); nicio aprobare pe o versiune nevalidată.

### F5.10 — Carantina și contestațiile
- Ecranele `/validatoare/carantina` (listă, detaliu cu dovezi, eliberare cu motiv spre validare / reparație, respingere definitivă), `/validatoare/verdicte/{id}` (contestă orice verdict) și `/validatoare/exemple` (promovarea exemplelor propuse în setul de aur); statistica contestațiilor pe validator.

### F5.8 — Calibrarea judecătorilor (G14)
- Eșantion săptămânal programat de verdicte V3 / V4 la om, coada de etichetare `/validatoare/calibrare`, acordul pe judecător (procent, kappa, interval Wilson), alertă sub 85% și la derivă, etichetele „greșit” devin exemple propuse; tabelul `calibrare_etichete` (migrarea `0032`).

### F5.7 — Seturile de aur și bancul de evaluare (K4)
- Seturi de aur înghețate în `evaluare/aur/` (8 validatoare, 107 materiale greșite, 63 bune), bancul `python -m app.validare.banc` și butonul din ecranul „Validatoare” (job durabil `validare.banc`), scoruri pe validator (matrice, precizie, recall, respingeri pe nedrept) salvate în `banc_rulari`; exemple propuse pentru setul de aur (`exemple_propuse`), migrarea `0031`.
- `db.restrans_la_client` (îngustare într-un punct de salvare anulat) în locul comutării libere de context; validatorii îmbunătățiți (limbă străină, linkuri, etichete de ordine, tipare G3, registrul G4, „încearcă”, promisiuni negate). Workerul importă acum `app.validare.fluxuri`.

### F5.6 — G7 Originalitate și G9 Juridic
- G7: suprapunere de shingle-uri cu sursele colectate (concurența blochează, materialele clientului doar avertizează), parafraze prin vectori, active fără licență. G9: reducerea cere ofertă cu preț de referință egal cu cel mai mic preț din ultimele 30 de zile (din versiunile aprobate ale ofertei; lipsa istoricului se semnalează explicit), promisiuni de rezultat, mențiuni obligatorii (pachetul `juridic`), judecător puternic opțional (V4).

### F5.5 — G4 Ton și G8 Lizibilitate și conversie
- G4: vocabularul interzis / preferat al ghidului de brand APROBAT (V1), similaritatea cu exemplele aprobate prin vectori (V2, prag [I] dependent de model), rubrica de ton doar la semnal, cu dovadă literală (V3). Fără ghid aprobat nu trece tăcut.
- G8: un singur apel la acțiune (grupe de forme imperative în română; mai multe grupe → respins), hook (prima frază), lizibilitate (indice ILA documentat, praguri [I]), rubrica «hook clar» doar la semnal. Date în `date/ton.toml` și `date/conversie.toml`.

### F5.4 — Pachetele de reguli și G3 Politici
- `rulepacks/`: 25 de reguli de început în 10 pachete TOML (generale; Meta, TikTok, LinkedIn, email; nișe refuzate: jocuri de noroc, adulți, politică, scheme financiare; nișa sănătate), fiecare cu sursă, severitate, marcaj [I], data scrierii și exemple blocate / care trec, rulate automat; încărcare cu validare de schemă; garda interzice scrierea în `rulepacks/` din cod. Regulile pe client în bază (`reguli_client`, migrarea `0030`): autor uman obligatoriu, doar adăugare, aceleași exemple verificate la scriere.
- G3 (V1) aplică pachetele potrivite livrabilului (generale + canal + nișe + client) și păstrează în verdict versiunea și amprenta pachetelor; G3 (V3, opțional) pentru promisiuni formulate liber. Nișele refuzate merg în carantină. Dockerfile copiază `rulepacks/`.

### F5.3 — G2 Verificatorul de fapte
- Extragerea deterministă a afirmațiilor verificabile (prețuri cu monedă, procente, termene, date, ore, cifre, superlative, comparații, promisiuni) cu fragmentul exact, potrivirea EXACTĂ cu registrul (fapte aprobate și valabile la data publicării, oferte, reducere calculată din prețul de referință, citate din surse verificate literal), blocare la preț diferit sau afirmație neacoperită; V3 opțional pentru afirmațiile nestructurate, cu verificare deterministă a răspunsului.
- Fapt lipsă → livrabilul se oprește cu o ÎNTREBARE către client (`validari_intrebari`, migrarea `0029`, vizibilă în urma livrabilului), nu cu o presupunere.

### F5.2 — G1 Structură și G10 Limbă
- G1 (V0): câmpuri obligatorii pe cele 12 tipuri de livrabil, liste cu limite, lungimi pe canal [I], limba română (determinist, fără model), linkuri bine formate (fără rețea), toate într-un singur verdict. G10 (V1): diacritice lipsă (dicționar + raportul literelor), ș / ț cu sedilă, „î” / „â”, ghilimele, cratimă, repetiții; G10 (V3, opțional): acord și registru, prin judecător cu rubrică da / nu, dovadă literală și model diferit de autor.
- Date în `app/validare/date/*.toml`; infrastructura comună a judecătorilor (`judecator.py`) și a problemelor (`probleme.py`) pentru F5.3–F5.6; prompt versionat `validare.g10_limba`.

### F5.1 — Cadrul de validare
- Forma verdictului (validator + versiune, treaptă, trece / avertisment / eșec, severitate, scor, dovezi cu fragmentul exact și regula, instrucțiune, cost), cascada V0 → V5 (oprire după treapta cu eșec; la treptele cu cost, la primul eșec), agregarea (eșec critic → carantină, eșec major → reparație, avertismente în puncte, peste prag la om) și unirea instrucțiunilor într-un singur mesaj pentru autor. Registrul de validatori ca date (cod G, treaptă, tipuri și canale).
- Bucla `în validare` → `în reparație` → `în validare` peste mașina de stări (limita de 2 runde rămâne a `productie.muta`), fluxul durabil `validare.livrabil`, punctul de extensie pentru autorii reparațiilor (F6).
- Tabele `livrabile_continut` (versiuni de conținut ale livrabilului, provizoriu până la F6), `validari_rulari`, `validari_verdicte` (doar adăugare, RLS), migrarea `0028`; secțiunea „Validare” în urma livrabilului din ecranul Producție. DECIZII D-006.

### Poarta F4 — lanțul verificat local
- Test cap-coadă cu brandul fictiv (colectare → fapte → interviu → brief → ghid → citate și public → insight → strategie → aprobări → pachet de context) și comanda `python -m app.creier.pregatire --client <nume>` care creează clientul și sursele unui brand propriu. Poarta propriu-zisă (CariereAI și BigBrain) rămâne deschisă până la materialele și aprobarea proprietarului.

### F4.8 — Ecranul „Creierul de brand”
- Pe client: compartimentele cu intrările lor, versiunea aprobată și propunerile în așteptare, diferența între versiuni, editare (creează propunere nouă, nu suprascrie; trece prin schema și poarta compartimentului), aprobare / respingere / retragere cu motiv, sursele, concurenții și pașii de pregătire; faptele rămân pe `/creier/fapte` (legate, nu dublate). Întâi pentru telefon: carduri și formulare, fără tabele. `creier.rezumat_pe_compartimente`, `creier.propuneri_in_asteptare`.

### F4.11 — Strategia pe 90 de zile, prima formă
- Strategia (ipoteză, plan pe 30 și 90 de zile, indicator principal, prag minim, fereastră de măsurare, criteriu de oprire — toate obligatorii, schemă strictă și poartă) propusă prin gateway pe profilul `strategie` (se amână, nu se degradează) din pachetul de context al clientului (brief, ghid, fapte, public, insight aprobate), versionată și aprobată de un om. Ecranul „Campanii” (`/campanii`): lista pe client, detaliu, aprobă / respinge cu motiv.
- Constructorul de context: secțiuni la cerere `brief`, `public`, `insight`, `strategie` (`sectiuni_extra`); implicit pachetele nu se schimbă.

### F4.10 — Harta pieței și brieful de insight
- Concurenți ca surse (3–5 pe client, citire cu colectorul existent, text lipit altfel; textul lor nu se reutilizează), afirmațiile lor (ofertă, preț, mesaj) extrase pe pasaje cu citat verificat literal în `insight_piata`, brief de insight pe o pagină cu trimitere la sursă pe fiecare afirmație (profilul `strategie`, se amână), poarta care blochează afirmațiile fără trimitere, trimiterile fără sursă și sondajul de citate picat; sondaj cu eșantion determinist (`sondaj.esantion`).

### F4.9 — Profilul de public și vocea clientului
- Citate reale din recenzii, comentarii și întrebări (flux durabil pe pasaje, gateway cu schemă strictă): fiecare citat verificat LITERAL în pasaj, fără date personale (garda din F3.9) și fără numele autorului, cu sursă și poziție, în `insight_public` (aprobat de sistem). Profilul clientului ideal (segmente, nevoi, obiecții, declanșatori, canale, limbaj, dovezi) propus din brief și citate, cu poartă (≥ 20 de citate aprobate, dovezi reale) și aprobat doar de un om.
- `gateway.detecteaza_date_personale` (export). Mecanism comun de extragere pe pasaje (`onboarding.extractie`).

### F4.5 — Profilul de brand
- Trei variante de ton propuse prin gateway din brieful aprobat și din materiale (descriere, reguli da / nu, vocabular preferat / interzis, ≥ 3 exemple pe ≥ 3 canale, fără vocabular interzis în exemple — verificate determinist); omul alege, combină sau corectează (versiune nouă, nu suprascriere); ghidul aprobat intră în `profil_brand` și este preluat de constructorul de context. Migrarea `0027`, ecranul `/onboarding/{client}/ghid`.
- Creier: randare pe compartiment (`inregistreaza_randare`) și intrări aprobate doar de om într-un compartiment cu aprobare automată (`inregistreaza_cere_om`).

### F4.4 — Asistentul de onboarding
- Interviul din 19.3 ca date (5 secțiuni, 11 întrebări), sesiune persistentă și reluabilă (`onboarding_sesiuni`, `onboarding_intrebari`, migrarea `0026`), întrebări de clarificare generate prin gateway și limitate (2 pe întrebare, 6 pe sesiune), brief cu 11 câmpuri obligatorii (schemă Pydantic) compus ca flux durabil din răspunsuri + materialele colectate, cu sursă și citat verificat literal pe fiecare câmp.
- Poarta de aprobare a Creierului (`creier.inregistreaza_poarta`): un brief cu câmpuri goale nu poate deveni „propus” sau „aprobat” pe nicio cale. Compartimente noi `brief`, `insight_piata`, `strategie` (DECIZII D-005). Permisiunea `onboarding.completeaza` (operator, proprietar). Ecranul `/onboarding`.

### F4.7 — Constructorul de context
- Pachetul de context al unei sarcini (client, tip, canal, întrebare, livrabil): reguli și interdicții (obligatorii), fapte aprobate și valabile relevante (doar prin `fapte.pentru_context`), oferte valabile, ghidul de brand aprobat (lipsa lui e spusă explicit) și pasaje din materialele clientului prin căutarea hibridă (doar din surse reutilizabile; în prompt doar marcate ca externe). Fiecare element poartă identificatorul și versiunea sursei.
- Buget de tokeni cu priorități între secțiuni și trunchiere deterministă (un element intră întreg sau deloc; regulile intră mereu); aceleași intrări dau aceeași amprentă.
- Pachetul se salvează (`pachete_context`, migrarea `0025`, RLS, doar adăugări) și se leagă de livrabil: apare în secțiunea „Pachetul de context” de pe `/productie/{id}`.
- Corecție la F4.6: valoarea numerică a unui fapt nu se mai stochează în notație științifică (`50` devenea „5E+1”). `cautare.cauta` primește `surse=[…]`.

### F4.6 — Registrul de fapte și catalogul de oferte
- Fapte (tip, afirmație atomică, valoare structurată cu număr exact, sursă obligatorie: pasaj / document / URL / declarația clientului, stare propus / aprobat / respins / expirat, valabilitate, cine a aprobat) și catalog de oferte (preț, monedă, condiții, valabilitate, legate de fapte), peste depozitul versionat. Singura citire pentru context, `pentru_context`, întoarce doar ce a aprobat un om și e valabil la data cerută; o gardă statică o impune și constructorului de context.
- Extragere din materiale ca flux durabil: pasajele trec prin gateway cu schemă strictă (`prompts/creier.extrage_fapte.v1.md`), fiecare fapt păstrează citatul exact, iar un verificator determinist respinge propunerile al căror citat nu apare literal în pasaj sau ale căror cifre nu apar în citat. Expirare automată (job zilnic) cu anunț; punct minim în panou (`/creier/fapte`: aprobă / respinge cu CSRF, permisiune, audit).
- Migrarea `0024` (`creier_extrageri`, RLS). `Dockerfile`: `COPY prompts`.

### F4.3 — Vectori și căutare hibridă
- Materialele colectate se taie în pasaje (paragrafe întregi, suprapunere, legătură pasaj → document → sursă → URL / poziție), se vectorizează în loturi prin gateway (flux durabil `creier.indexeaza_sursa`, cu reprogramare la `Amanat`; pornește singur după fiecare colectare) și se caută hibrid: vectori (pgvector) + text fără diacritice + trigrame, combinate prin fuziune de ranguri, cu filtrare pe client (RLS) și opțional pe sursă / compartiment. Fiecare vector poartă modelul care l-a produs: la schimbarea modelului pasajele se re-vectorizează.
- Migrarea `0023` (`pasaje`, RLS). Gateway: `vectorizeaza_cu_model`, `model_vectori`. Setări: `AMA_VECTORI_PREFIX_PASAJ`, `AMA_VECTORI_PREFIX_INTREBARE`.

### F4.2 — Colectorul de surse
- `app/cercetare`: crawl politicos al site-urilor (robots.txt cu `Crawl-delay`, User-Agent propriu, o cerere odată pe gazdă cu pauză, doar același domeniu înregistrat, sitemap, fără formulare și fără autentificare), cu apărare SSRF (doar http / https, adrese private / loopback / link-local / metadate refuzate la fiecare redirecționare, limită de octeți în flux, tipuri permise) și limite de pagini, adâncime, octeți, timp, capcane de linkuri. Text extras cu parserul din biblioteca standard; originalul pe disc (`AMA_MEDIA_DIR`) cu hash; deduplicare; re-colectare incrementală; flux durabil pe coada `io` cu stare vizibilă (găsite / citite / sărite și de ce).
- Statutul surselor din 12.1 ca date; materiale manuale (text lipit, `.txt`, `.md`; PDF amânat); `ca_continut_extern` pentru prompturi.
- Migrarea `0022`: `surse`, `colectari`, `colectari_pagini`, `documente_colectate` (RLS). Setări noi: `AMA_MEDIA_DIR`, `AMA_COLECTOR_USER_AGENT`.

### F4.1 — Modelul Creierului
- `app/creier`: cele zece compartimente din 10.1 ca date, intrări cu versiuni (`ciornă → propus → aprobat → retras`), sursă obligatorie, valabilitate, cine și când a aprobat, nivelurile de cunoaștere din 10.2. API: `creeaza_intrare`, `propune_schimbare`, `aproba`, `retrage`, `citeste`, `la_data`, `istoric`, `diferenta_versiuni`.
- Migrarea `0021` (`creier_intrari`, `creier_versiuni`, RLS): conținutul unei versiuni nu se mai poate schimba (declanșator în bază), cel mult o versiune aprobată pe intrare.

### Poarta F3 — Gateway de modele
- Test cap-coadă cu furnizori falși (`tests/integration/test_poarta_f3.py`): testul comparativ rulat pe modelele de text din configurarea de probă, iar cu fiecare dintre cei cinci furnizori oprit pe rând un flux de probă pe fiecare profil se termină (degradare marcată la modelul local pe coada `greu`, trecere pe alt furnizor sau amânare curată, fără eșecuri). Testul comparativ pe modele reale rămâne deschis până la migrare.

### F3.11 — Planificatorul de capacitate (A4)
- Planificatorul zilnic (și la cerere) compară munca planificată (costuri pe tip de livrabil, ca date) cu cotele rămase pe profil și cu timpul de CPU al culoarelor grele; ce nu încape se amână, termenul cel mai îndepărtat întâi, iar P0 și termenele sub 48 de ore rămân neatinse. Decizia se scrie (`planificare_planuri`, `planificare_decizii`, migrarea `0020`) și o alertă spune ce nu a încăput.
- `productie.amana` / `productie.elibereaza` și câmpul `livrabile.nu_inainte_de`: `productie.muta` refuză pornirea unui livrabil amânat până la acel moment (cod `amanat`, în istoric).

### F3.10 — Ecranul „Modele și cote”
- `/gateway/registru` arată cota rămasă pe fiecare furnizor și model (minut și zi, cu resetare), starea întrerupătoarelor și blocajele, scorurile pe profil și rulările testului comparativ, viteza modelelor locale, consumul pe client față de buget. Proprietarul editează limitele, termenii și bugetele (implicite și pe client), pornește testul comparativ și importă note, cu CSRF, verificare de rol și audit.

### F3.6 — Testul comparativ pe română
- Set de 72 de sarcini în română (`evaluare/sarcini/`, 12 pe fiecare profil din 8.2) cu criterii automate (schemă, lungime, cuvinte obligatorii / interzise, răspuns exact, diacritice), hamul de rulare prin gateway (P3, un model pe rulare, cote și bugete respectate, continuare după amânare), scorul pe (model, profil) scris în `gateway_modele.scor` și folosit de rutare, nota umană importată din CSV, istoric de rulări (migrarea `0019`), flux și job lunar, comandă `python -m app.gateway.evaluare`.

### F3.5 — Modelul local și modelul de embeddings
- Adaptorul `local` (server compatibil OpenAI separat, fără cheie, ieșire structurată prin schemă); modelul local se apelează doar din joburi de pe coada `greu` (în afara ei: `ApelRefuzat("local_doar_pe_coada_greu")`); `motor.coada_curenta()`. Sămânța în registru (3 mărimi + model de vectori de 384 dimensiuni, inactive, neverificate; migrarea `0018`) și serviciile `local-llm` / `embeddings` în compose (profil, fără digest: NEVERIFICAT).
- `gateway.vectorizeaza(texte, tenant_id=…)` și `gateway.dimensiune_vectori`: vectori fără coada `greu`, dimensiunea ca dată în registru. `python -m app.gateway.masurare`: viteza (tokeni/s) a modelelor locale, scrisă în registru. `gateway.apeleaza(…, model=…)` pentru un singur model (evaluare).

### F3.9 — Garda de date personale și garda de injecții
- Mascare deterministă înainte de orice apel (email, IBAN, CNP cu cifră de control, card cu Luhn, telefon românesc, IP; CUI doar la cerere), cu marcaje stabile `[EMAIL_1]`, demascare opțională a răspunsului, jurnal și conținut păstrat în varianta mascată. `date_confidentiale` ajunge în rutare; fără model permis, apelul este refuzat.
- `gateway.marcheaza_extern(text, sursa=…)`: funcția unică pentru orice text venit din afară (delimitatori cu id aleator, delimitatori falși neutralizați, caractere invizibile eliminate) și instrucțiunea „date, nu instrucțiuni” în mesajul de sistem; detecție euristică de tentative de injecție ca semnal în jurnalul de apeluri (migrarea `0017`), fără blocare. Garda `check_gateway` interzice `eval`/`exec`/`subprocess` în gateway.

### F3.8 — Bugete și priorități
- Bugete pe client (apeluri, tokeni, preț-umbră; pe zi și pe lună; valori implicite + suprascrieri per client; migrarea `0016`), aplicate de interceptorul `buget_client`: la depășire, P2 și P3 primesc `Amanat` cu momentul resetării, P1 continuă până la 1,5 × buget, P0 nu este atins. Consumul se ține în contoare proprii, rezervate atomic (corect la concurență). Avertizare la 80%, o singură dată pe fereastră. Decizia D-004.

### F3.7 — Registrul de prompturi și jurnalul de apeluri
- `gateway.apeleaza(db, prompt=…, variabile=…, schema=…, tenant_id=…, componenta=…, prioritate=…)`: API-ul public unic. Prompturile sunt versionate (`gateway_prompturi`, migrarea `0015`; ciornă / activ / retras; versiunea activă nu se modifică, impus în bază; o singură versiune activă pe nume) și pot veni din fișiere `prompts/<nume>.v<N>.md`. Variabilele trebuie să se potrivească exact cu locurile din șablon; un secret al aplicației nu poate intra într-un prompt.
- Jurnalul de apeluri (`gateway_apeluri`, cu `tenant_id` și RLS): cine, prompt și versiune, model ales și de ce, tokeni, durată, reparații, preț-umbră, traseul încercărilor; scris și pentru apelurile amânate, refuzate sau eșuate. Conținutul (mesajele trimise, răspunsul) stă separat, cu RLS, 30 de zile (`gateway_apeluri_continut`, ștergere zilnică); nu intră în tabelele motorului sau în jurnalele aplicației. Fiecare apel se contorizează în bugetul livrabilului.
- Panoul: `/gateway/apeluri` (listă cu filtre pe client, model și rezultat) și detaliul unui apel, cu izolare pe client și urmă în audit la deschiderea conținutului.

### F3.4 — Rutarea și lanțurile de rezervă
- Profilurile de sarcină din 8.2 ca date (`gateway_profiluri`, migrarea `0014`): nivel minim, capabilități, lanț ordonat de modele, ce se întâmplă când lanțul s-a epuizat (`amana` / `degradeaza` / `amana_sau_provizoriu`), lanț de degradare. Alegerea modelului (nucleu pur): furnizor oprit, fără cheie, fără uz comercial, antrenare pe date, capabilități, nivel minim, întrerupător deschis, T4 pe calea critică (ADR-06), apeluri plătite oprite, „alt model decât autorul”; ordine după scor (gol până la F3.6) și lanț.
- Reacțiile din 7.5: 429 → alt furnizor; eroare de server → 3 reîncercări cu pauză crescătoare, apoi alt furnizor; ieșire în afara schemei → o reparație, apoi alt model; autentificare → furnizor pe pauză cu audit și alertă. Întrerupător pe furnizor (3 eșecuri la rând → scos 120 s, apoi cerere de probă). Strategia se amână, nu se degradează; clasificarea și rescrierea degradează la modelul local.
- Interceptori înainte și după apel (`gateway.adauga_interceptor`), punctul de extensie pentru bugete (F3.8) și gărzile de date (F3.9).

### F3.3 — Limitatoarele de cotă
- Contoare persistente în Postgres (`gateway_contoare`, `gateway_blocaje`, migrarea `0013`) pe (model sau cont de furnizor, minut / zi), cu rezervare atomică înainte de apel (o instrucțiune SQL sub plafon, corectă la concurență), regularizare cu tokenii reali, antetele furnizorului ca sursă de adevăr (`x-ratelimit-*`, `retry-after`), blocaj după 429 și rezerva de 10% din limita zilnică pentru P0.
- Cota epuizată devine `Amanat(pana_la)`; un flux durabil se reprogramează prin motor cu `gateway.reprogrameaza` pentru momentul resetării (fără `sleep`).

### F3.2 — Clientul unificat
- Un singur mod de a apela orice furnizor, cu `httpx` și transport injectabil (fără SDK-uri): adaptoare pe tip de API (compatibil OpenAI, Gemini, Anthropic), erori clasificate după 7.5, citirea antetelor de limită, ieșiri structurate (schemă JSON nativă sau instrucțiune, validare Pydantic, o singură reparație, apoi eroare tipizată). Cheia nu apare în erori sau jurnale (testat).
- Garda `scripts/check_gateway.py` în `make guards`: niciun import intern al gateway-ului și nicio adresă de furnizor în afara `app/gateway`; fără SDK-uri de furnizori. Furnizorul fals pentru teste (`tests/furnizor_fals.py`, SIMULAT).

### F3.1 — Registrul de furnizori și modele
- Tabelele `gateway_furnizori` și `gateway_modele` (migrarea `0012`), la nivel de agenție, cu RLS: furnizor (tip de API, adresă `https`, stare, termeni: uz comercial, antrenare pe date, regiuni; marcaj `V`/`S`/`I` și dată de verificare; limite pe minut și pe zi) și model (nivel T1–T4/local, context, capabilități, limite, preț-umbră, scor pe profil). Cheia de API nu stă în bază: doar numele variabilei de mediu `AMA_CHEIE_*` (baza refuză alt nume). Un furnizor fără uz comercial confirmat nu poate fi activat (impus și în bază).
- Sămânța din `app/gateway/inventar.py` (OpenRouter, Groq, Gemini, Cloudflare, Claude), totul `inactiv`. Ecranul `/gateway/registru` (limite, termeni, „cheie configurată / lipsește”), cu activare / dezactivare de către proprietar (CSRF, audit).

### Poarta F2 — Motorul
- Test cap-coadă cu procese reale (`tests/chaos/test_poarta_f2.py`): un livrabil de probă parcurge toate stările normale, supraviețuiește la două SIGKILL (la mijloc și în jurul publicării) și produce un singur efect la conectorul fals, fără tranziții dublate.

### F2.9 — Ecranele Producție și Operare
- Producție: lista livrabilelor (filtre pe client, stare și excepții, paginare) și „urma” fiecăruia: mutările inclusiv refuzurile, pașii fluxului durabil cu stare, durată și eroare, cererile de aprobare, efectele externe, contoarele de limite. Acțiuni cu CSRF, permisiune, motiv și audit: reia livrabilul din coada de erori (și efectul extern eșuat), reia un pas eșuat, anulează. Operare, motorul: workerii și cozile (adâncime, în lucru), joburile programate (pauză, reluare, „rulează acum”), efectele în așteptare sau oprite și canalele pe pauză, întrerupătorul și opririle. Un operator vede doar clientul la care are acces.

### F2.5 — Executorul de efecte externe
- Outbox tranzacțional (`efecte_de_trimis`): efectul se scrie în aceeași tranzacție cu mutarea care îl cere, cu cheie de idempotență unică (client, livrabil, canal, versiune, tip); a doua cerere întoarce primul rând. Fluxul durabil `efecte.executa` îl trimite pe coada canalului; o încercare notează `în trimitere` înainte de conector și rezultatul după, iar după orice eroare sau rezultat necunoscut începe cu `verifica` (7.3). Erori clasificate (7.5): temporare cu pauză crescătoare, autentificare cu pauză pe conector și alertă de reautorizare, definitive în coada de erori. Oprirea globală a publicării și oprirea pe client se verifică chiar înainte de trimitere; efectul rămâne în așteptare și pleacă după repornire doar dacă mai e valabil. Contractul și registrul conectorilor (`app/connectors`), conector fals în teste, garda `scripts/check_efecte.py`. Migrarea `0011`.

### F2.10 — Nivelurile de autonomie
- Matricea pe client × cinci clase de acțiuni, niveluri L0–L4, implicit L1; funcția pură de decizie „cere aprobare?” (umbră / aprobare / automat) cu eșantion determinist la L2 și L3; canalele cu consimțământ per postare (TikTok) rămân la L1, ca date; schimbarea nivelului doar de proprietar (permisiunea `autonomie.seteaza`, motiv, audit); retrogradare cu un nivel la incident critic; poarta din `productie.muta` recalculează decizia (L0 produce, nu publică). Migrarea `0010`.

### F2.8 — Cererile de aprobare
- Obiectul de aprobare (client, livrabil și versiunea lui, clasa de acțiune, decident operator/client, termen de 48 h, reamintire la 24 h, stare, decident, moment); decizia se leagă de versiune (o aprobare pe o versiune veche nu aprobă versiunea nouă); poarta „fără aprobare automată” în `productie.muta`; expirare prin jobul programat (o cerere neprimită la timp devine `expirat`, nu se publică); notificări la creare și înainte de termen; punctul minim din panou (listă, „Aprobă”, „Respinge” cu motiv, CSRF, permisiune, audit). Migrarea `0009`.

### F2.4 — Limite anti-buclă
- Cel mult 2 runde de reparație (a treia merge la om), cel mult 12 predări, buget per livrabil (apeluri la modele și timp), toate în `productie.muta`/`inregistreaza_consum`; la depășire livrabilul trece în coada de erori cu diagnostic și anunț, iar un om îl reia (`reia_de_om`). Întrerupătorul global (rata de eșec peste 30% pe oră, minim 10 rezultate) oprește producția nouă (`Oprire.PRODUCTIE`, buton în panou și comandă în Telegram); repornirea e doar a omului, auditată. Pragurile se configurează. Migrarea `0008`.

### F2.3 — Mașina de stări a livrabilului
- Cele 22 de stări din 7.2 (16 normale + 6 de excepție) și tabelul de tranziții ca date; tabelele `livrabile` și `livrabile_tranzitii` (istoric doar-adăugare); o singură funcție, `productie.muta`, schimbă starea (blocare pe rând, stare așteptată, versiune opțională), cu declanșator în bază care refuză orice altă cale. Tranziția nepermisă este refuzată și înregistrată într-o tranzacție separată, deci rămâne după rollback-ul apelantului. Migrarea `0007`.

### F2.7 — Watchdog și coada de erori
- Workerul bate în `worker_semnale`; căderile și repornirile se văd (a treia într-o oră anunță); un job blocat se oprește și se reîncearcă o dată; joburile eșuate, epuizate sau blocate intră în coada de erori cu context complet, grupate pe cauză și triate (minor / major). Ecranul Alerte din panou: listă, detaliu, „Reia” (de la pasul eșuat sau ales) și „Închide” (cu motiv), cu CSRF și audit; numărul alertelor și starea workerului pe Acasă. Migrarea `0006`, permisiunea `alerte.gestioneaza`, healthcheck pe serviciul `worker`.

### F2.6 — Planificatorul de timp
- Joburi recurente (cron cu 5 câmpuri = la minut, fus orar `Europe/Bucharest`, recuperarea ticurilor ratate) și sloturi (un job la un moment dat, idempotent, supraviețuiește repornirilor), peste planificatorul bibliotecii. Programările se declară în cod și se aplică la pornirea workerului.

### F2.2 — Cozile
- Cozile din 7.5: `urgent`, `greu` (câte un job pe culoar, `AMA_CULOARE_GREU`, implicit 2), `io` (24), `invatare` (1); fabrica de cozi pe furnizor și pe platformă cu limită de rată; priorități P0–P3 cu termenul codificat în prioritatea bibliotecii (nu are termene). Configurarea cozilor se scrie în bază înainte de lansare.

### F2.1 — Execuția durabilă
- Biblioteca de workflow-uri DBOS Transact (`dbos==3.5.0`) în aceeași bază, schema `dbos`, ascunsă în `app/operare/motor/` (garda `scripts/check_motor.py`); decoratorii `flux` și `pas`, `trimite` din procesul web, procesul `worker` cu oprire curată, schema creată de `ama_owner` (`python -m app.operare.motor.migrare`), drepturi minime pentru `ama_app`, serviciul `worker` în compose, mutat de deployer odată cu aplicația. Un flux oprit forțat reia de la ultimul pas.

### F1.10 — Botul Telegram și butoanele de oprire
- Webhook păzit de secret și de lista conversațiilor permise; comenzile `/stare`, `/opreste…`, `/porneste…` (repornirea cere cod de confirmare, o singură încercare), alerte critice. Steagurile de oprire există, dar modulele care le citesc apar din F2.

### F1.7 — Coaja panoului
- Panou instalabil (PWA) cu bara de jos, ecranul Acasă, temă luminoasă/întunecată, service worker și notificări push; HTMX și Alpine (build CSP) vendorizate.
- Pagina Operare: promovare în producție și revenire cu confirmare, starea backupului.

### F1.8–F1.9 — Livrare și backup (infrastructură)
- Imagine Docker, compose pentru staging și producție, proxy Caddy, instalarea VPS-ului, deployer cu revenire, backup criptat cu test de restaurare.

### F1.6 — Jurnalul de audit și de evenimente
- Două jurnale doar cu adăugare, impuse în bază; fiecare acțiune sensibilă este înregistrată cu utilizator, moment și identificator de corelare.

### F1.5 — Autentificare
- Parolă (argon2id), al doilea factor TOTP obligatoriu pentru agenție, coduri de recuperare, sesiuni pe server, CSRF, limitarea încercărilor, antete de securitate.

### F1.4 — Clienți, utilizatori, roluri
- Modelul de conturi, cele șase roluri, izolare la nivel de rând forțată pe toate tabelele cu date de client.

### F1.3 — Baza de date și migrările
- Postgres cu `pg_trgm`, `citext`, `vector`; Alembic; roluri separate pentru migrări și pentru aplicație.

### F1.1 — Aplicația de bază
- Aplicație FastAPI modulară, `/healthz`, configurare din variabile de mediu, jurnale JSON cu identificator de corelare.

### F0.2 — Repo și reguli
- `AGENTS.md`, `DECIZII.md`, structura de directoare, documentul de arhitectură împărțit pe secțiuni în `docs/`, cele 16 ADR-uri, șablonul de cerere de integrare, CI.
