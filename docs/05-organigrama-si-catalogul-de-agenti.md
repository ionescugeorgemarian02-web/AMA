## 5. Organigrama și catalogul de agenți

Agenția are 12 departamente și 87 de componente. Fiecare are un tip, un contract de intrare și ieșire și un controlor diferit de autor. 40 dintre ele nu folosesc deloc LLM.

### 5.1 Cum se citește catalogul

- **Tip.** D = serviciu determinist, fără LLM. L = un singur apel LLM cu schemă fixă de ieșire. A = agent cu buclă de unelte. M = model ML clasic. H = om.
- **Nivel de model.** T1 = mic sau local. T2 = mediu, gratuit. T3 = cel mai bun gratuit disponibil. T4 = Claude.
- **Regula de bază.** Tipul implicit este D. O componentă primește LLM doar dacă sarcina cere limbaj sau judecată.
- **Separarea puterilor.** Cine scrie nu validează. Validatorii din departamentul G folosesc, unde se poate, alt model decât autorul.
- **Contract comun.** Fiecare componentă primește un „pachet de context” și întoarce un obiect cu schemă validată, cu dovezi și un scor de încredere.
- **Ordinea de construcție.** Versiunea 1 nu construiește toate cele 87 de componente deodată. Secțiunea 27.4 arată în ce pas se construiește fiecare.
- **Coduri care seamănă.** F1–F8 sunt și componente ale departamentului F, și faze de construcție. L1–L4 sunt și componente ale departamentului L, și niveluri de autonomie. Regula de citire este în secțiunea 27.1.

### 5.2 A. Conducere și strategie

| Componentă | Tip · model | Rol și ieșire | Controlat de |
| --- | --- | --- | --- |
| A1 Consiliul | A + H · T4 | Revizuiește lunar și la escaladare strategiile, pivotările și schimbările de prompturi propuse. Ieșire: decizie de Consiliu. | Tu, pentru orice atinge bani sau contract |
| A2 Strategul de campanie | A · T3 | Transformă obiectivul clientului în ipoteze, plan pe 30 și 90 de zile, arbore de indicatori și criterii de oprire. | A1 pe eșantion; clientul aprobă |
| A3 Managerul de experimente | D + L · T2 | Ține registrul de ipoteze, alocă variantele și închide testele după reguli stabilite dinainte. | K7 |
| A4 Planificatorul de capacitate | D | Compară zilnic munca planificată cu cotele și timpul de CPU. Amână ce nu încape, după termen și prioritate. | B2, cu alerte către tine |

### 5.3 B. Platformă și operațiuni

| Componentă | Tip · model | Rol și ieșire | Controlat de |
| --- | --- | --- | --- |
| B1 Orchestratorul | D | Mașina de stări: mută fiecare livrabil prin etape, aplică limitele de reîncercare și previne buclele. | Jurnalul de tranziții, B3 |
| B2 Gateway de modele și FinOps | D | Rutează fiecare apel după capacitate și cotă rămasă. Ține bugetele și jurnalul apelurilor. | Ecranul „Modele și cote” |
| B3 Watchdog și recuperare | D | Detectează joburi blocate, reîncearcă, mută în coada de erori, repornește workeri. Te anunță doar la avarii. | Matricea de severitate |
| B4 Planificatorul de timp | D | Declanșează joburile recurente și sloturile de publicare. | B1 |
| B5 Notificatorul | D | Trimite alerte și cereri de aprobare prin push, Telegram și email. | Preferințele tale |
| B6 Sănătatea conectorilor | D | Urmărește tokenurile, permisiunile și starea aprobărilor API. Cere reautorizare înainte de expirare. | B3 |
| B7 Executorul de efecte externe | D | Singura ușă spre exterior: publică, trimite email, schimbă reclame. Fiecare acțiune are cheie de idempotență. | Jurnalul de audit |

### 5.4 C. Cercetare și insight

| Componentă | Tip · model | Rol și ieșire | Controlat de |
| --- | --- | --- | --- |
| C1 Colectorul de surse | D | Descarcă politicos pagini, fluxuri și date din API-uri oficiale. Păstrează originalul, textul curățat și sursa. | Reguli de crawl, G13 |
| C2 Cercetătorul de tendințe | D + L · T2 | Găsește subiecte în creștere din YouTube, fluxuri de tendințe, știri de nișă și inboxul de tendințe. Ieșire: fișe de tendință cu dovezi. | G2 pe citări |
| C3 Analistul de reclame ale concurenței | D + L · T2 | Citește bibliotecile oficiale de reclame și grupează unghiurile, ofertele și formatele folosite. | G7: se analizează, nu se copiază |
| C4 Profilerul de public | L · T3 | Construiește profilul clientului ideal: dureri, obiecții, declanșatori, vocabular. | Clientul aprobă |
| C5 Vocea clientului | D + L · T2 | Extrage citate și teme din recenzii, comentarii și întrebări frecvente. | G12 elimină datele personale |
| C6 Cercetătorul SEO | D + L · T2 | Grupează cuvintele-cheie pe intenție, analizează paginile din top și propune subiecte. | E7 |
| C7 Analistul de piață și ofertă | L · T3 | Compară ofertele, prețurile și garanțiile din nișă. Ieșire: harta pieței. | G2 |
| C8 Sintetizatorul de cercetare | L · T3 | Unește cercetarea într-un brief de insight de o pagină, cu citări. | A2 |

### 5.5 D. Brand și strategie de conținut

| Componentă | Tip · model | Rol și ieșire | Controlat de |
| --- | --- | --- | --- |
| D1 Strategul de brand | L · T3 + H | Formulează poziționarea, tonul, vocabularul permis și cel interzis. Ieșire: profilul de brand. | Clientul aprobă |
| D2 Arhitectul de ofertă și pâlnie | L · T3 | Proiectează oferta, magnetul de lead-uri și traseul de la reclamă la vânzare și retenție. | A2, clientul |
| D3 Strategul de conținut | L · T3 | Definește pilonii, formatele, frecvența și calendarul lunar. | A2 |
| D4 Planificatorul de canale | D + L · T2 | Alege canalele și sloturile, după aprobările API și după rezultate. | K6 |
| D5 Autorul de brief | L · T2 | Scrie brieful fiecărui livrabil: scop, public, mesaj unic, fapte permise, format. | G1 |

### 5.6 E. Creație text

| Componentă | Tip · model | Rol și ieșire | Controlat de |
| --- | --- | --- | --- |
| E1 Generatorul de hook-uri | L · T2 | Produce 3–5 deschideri pe tipare diferite. Cea mai bună este aleasă de G8 și K6. | G8 |
| E2 Scenaristul video | L · T2–T3 | Scrie scripturi pe bătăi, cu durată țintă, text pe ecran și indicații vizuale. | G2, G3, G8 |
| E3 Copywriterul de conversie | L · T3 | Scrie pagini de vânzare, reclame și studii de caz. | G2, G3, G9 |
| E4 Autorul de postări | L · T2 | Scrie postări, carusele și descrieri pentru fiecare canal. | G4, G8 |
| E5 Autorul de articole SEO | L · T3 | Scrie articole în trei pași: schiță, secțiuni, asamblare. | E7, G2, G7 |
| E6 Autorul de secvențe email | L · T2–T3 | Scrie newslettere și secvențe pentru abonați. | G3, G9 |
| E7 Agentul SEO on-page | D + L · T1 | Verifică și corectează titluri, meta, structura de titluri, linkuri interne și date structurate. | Listă de verificare deterministă |
| E8 Editorul | D + L · T2 | Corectează gramatica și diacriticele. Elimină formulările șablon și repetițiile. | G10 |
| E9 Localizatorul | L · T3 | Adaptează cultural textul pentru altă piață și verifică prin retroversiune. | Vorbitor nativ, la reclame |
| E10 Adaptorul pe platformă | L · T1–T2 | Rescrie nativ pentru fiecare canal: lungime, hashtag-uri, apel la acțiune. | G1, G3 |

### 5.7 F. Design și media

| Componentă | Tip · model | Rol și ieșire | Controlat de |
| --- | --- | --- | --- |
| F1 Designerul de identitate | L · T3 + D + H | Propune paletă, fonturi și reguli de folosire a logoului. Generează șabloanele de brand. | G5, clientul aprobă |
| F2 Inginerul de prompturi vizuale | L · T2 | Transformă scenele în cereri pentru căutarea de stock și pentru generatorul de imagini. | G5 |
| F3 Furnizorul de imagini | D | Alege în ordine: materialele clientului, stock cu licență, imagine generată. Salvează licența fiecărui fișier. | G7 |
| F4 Compozitorul de creativuri și miniaturi | D | Randează bannere, carusele și miniaturi din șabloane, cu text exact și diacritice corecte. | G5 |
| F5 Vocea | D | Normalizează textul și sintetizează narațiunea în română, cu profilul de voce al clientului. | G6, prin transcriere inversă |
| F6 Regizorul video | L · T2 + D | Împarte scriptul în scene și produce lista de decizii de montaj. Nu scrie comenzi, doar un plan validat. | G1 |
| F7 Montajul și post-producția | D | Compune video din lista de decizii: cadre, subtitrări cuvânt cu cuvânt, muzică, export pe formate. | G6 |
| F8 Bibliotecarul de active | D | Ține versiunile, licențele, pașaportul de proveniență și regulile de păstrare. | G7, G11 |

### 5.8 G. Calitate și conformitate

| Componentă | Tip · model | Rol și ieșire | Controlat de |
| --- | --- | --- | --- |
| G1 Validatorul de structură | D | Verifică schema, lungimile, câmpurile obligatorii, limba și linkurile. | Teste automate |
| G2 Verificatorul de fapte | D + L · T2 | Extrage afirmațiile și le leagă de registrul de fapte sau de o sursă citată. Blochează orice afirmație neacoperită. | Set de aur, G14 |
| G3 Validatorul de politici | D + L · T2 | Aplică pachetele de reguli pe platformă: termeni interziși, promisiuni, categorii restricționate. | Reguli versionate |
| G4 Auditorul de ton | M + L · T2 | Compară textul cu exemplele aprobate ale brandului, prin similaritate și rubrică. | G14 |
| G5 Auditorul vizual | D | Verifică logoul, culorile, fonturile, zonele sigure și contrastul. | Teste pe șabloane |
| G6 Controlul tehnic media | D | Respinge cadre negre sau înghețate, sunet lipsă sau distorsionat, desincronizare, subtitrări tăiate, format greșit. | Colecție de clipuri defecte |
| G7 Originalitate și drepturi | D + M | Caută aproape-duplicate față de surse și de istoricul propriu. Verifică licența fiecărui activ. | F8 |
| G8 Lizibilitate și conversie | D + L · T2 | Măsoară lizibilitatea, forța hook-ului și existența unui singur apel la acțiune. | K6, G14 |
| G9 Garda juridică | D + L · T3 | Verifică promisiuni comerciale, reduceri, mențiuni obligatorii și reguli pe nișe sensibile. | Om, pe nișele sensibile |
| G10 Calitatea limbii | D + L · T1 | Verifică diacritice, acorduri, registru și cuvinte străine inutile. | Set de aur |
| G11 Proveniență și dezvăluire AI | D | Decide eticheta AI pe fiecare platformă, păstrează metadatele și completează pașaportul activului. | Reguli pe platformă |
| G12 Garda de date personale | D | Detectează și maschează date personale înainte de apeluri externe și înainte de publicare. | Teste cu date sintetice |
| G13 Garda de injecții | D | Tratează orice text adus din exterior ca date, nu ca instrucțiuni. Limitează uneltele fiecărui agent. | Colecție de atacuri |
| G14 Calibrarea judecătorilor | D + H | Compară verdictele automate cu etichete umane pe eșantion și semnalează deriva. | Tu, săptămânal |

### 5.9 H. Distribuție și comunitate

| Componentă | Tip · model | Rol și ieșire | Controlat de |
| --- | --- | --- | --- |
| H1 Editorul multi-canal | D | Pregătește pachetul pentru fiecare canal și îl trimite prin B7. Are mod asistat pentru canalele fără aprobare. | G11, nivelul de autonomie |
| H2 Gardianul limitelor și al sănătății conturilor | D | Respectă limitele API, urmărește erorile și semnalele de restricție, încetinește sau oprește. | B3 |
| H3 Răspunsuri în inbox | L · T2 + H | Propune sau trimite răspunsuri la mesaje, doar din registrul de fapte, cu dezvăluirea că este asistent AI. | Reguli de escaladare |
| H4 Moderatorul de comentarii | D + L · T1 | Clasifică: întrebare, laudă, critică, spam. Ascunde spamul, escaladează critica. | Jurnal, eșantion uman |
| H5 Expeditorul de email | D | Trimite către abonați printr-un furnizor de email, cu dezabonare dintr-un clic și listă de suprimare. | Rata de plângeri |
| H6 Editorul web | D | Publică articole și pagini în CMS-ul clientului sau în paginile găzduite de platformă. | E7 |

### 5.10 I. Reclame plătite

| Componentă | Tip · model | Rol și ieșire | Controlat de |
| --- | --- | --- | --- |
| I1 Planificatorul media | L · T3 | Propune obiectiv, public, împărțirea bugetului, matricea de creativuri și criteriile de oprire. | Clientul aprobă plafoanele |
| I2 Constructorul de campanii | D | Creează campaniile în stare de pauză, din planul aprobat. | I5, apoi activare |
| I3 Gardianul de buget | D | Aplică plafoane zilnice și lunare, limite de schimbare și perioade de așteptare. | Reguli fixe, fără LLM |
| I4 Managerul de teste creative | M | Împarte bugetul de test între variante și promovează câștigătoarele după praguri statistice. | K7 |
| I5 Verificarea înainte de lansare | D + L · T2 | Verifică textul, creativul și pagina de destinație față de regulile de reclame. | G3, G9 |
| I6 Anomalii și oprire de urgență | D | Oprește la vârf de cheltuială, urmărire stricată sau cost peste prag și te anunță. | Tu |

### 5.11 J. Vânzări și CRM

| Componentă | Tip · model | Rol și ieșire | Controlat de |
| --- | --- | --- | --- |
| J1 Captare și îmbogățire conformă | D | Primește lead-uri din formulare cu opt-in și le completează din date publice de firmă. | G12 |
| J2 Scorarea și calificarea lead-urilor | M + L · T2 | Pune întrebări de calificare și dă un scor. Reguli la început, model când există date. | Om, la lead-urile mari |
| J3 Agentul de programări | D | Oferă sloturi, confirmă, trimite invitația și reamintirile. | – |
| J4 Igiena CRM | D | Unește duplicatele, actualizează etapele, creează sarcini de urmărire. | – |
| J5 Generatorul de oferte | L · T2 | Scrie oferta personalizată din pachete și din auditul lead-ului. | Tu aprobi |
| J6 Asistentul de onboarding | A · T3 | Conduce interviul de început și cere ce lipsește, până când brieful este complet. | D1, clientul |

### 5.12 K. Analiză și învățare

| Componentă | Tip · model | Rol și ieșire | Controlat de |
| --- | --- | --- | --- |
| K1 Colectorul de metrici | D | Citește rezultatele din API-urile platformelor la 1 oră, 24 de ore, 72 de ore, 7 și 28 de zile. | Verificări de completitudine |
| K2 Analistul de atribuire și retenție | D + L · T2 | Leagă rezultatele de hook, format, slot și canal. Citește curba de retenție unde există. | K7 |
| K3 Autorul de insight | L · T2 | Explică în cuvinte ce a mers, ce nu și de ce, cu cifre. | G2 pe cifre |
| K4 Bancul de evaluare | D | Rulează seturile de aur pentru fiecare prompt și fiecare model. Păstrează scorurile. | – |
| K5 Optimizatorul de prompturi și playbook-uri | A · T3–T4, offline | Propune variante mai bune din urme și feedback. Nu promovează singur. | K4, validatorii, A1 |
| K6 Predictorul de performanță | M | Estimează, înainte de publicare, șansa ca un material să ajungă în sfertul de sus. | Testare pe date trecute |
| K7 Analistul de experimente | D | Calculează rezultatele testelor după regulile declarate dinainte. | Reguli statistice |
| K8 Curatorul de cunoștințe | L · T2 + H | Transformă lecțiile în intrări de playbook. Elimină duplicatele și contradicțiile. | Tu, pe schimbările mari |

### 5.13 L. Clienți și finanțe

| Componentă | Tip · model | Rol și ieșire | Controlat de |
| --- | --- | --- | --- |
| L1 Generatorul de rapoarte | D + L · T2 | Asamblează raportul lunar: livrabile, cifre, lecții, plan. | G2 pe cifre |
| L2 Biroul de aprobări | D + H | Pune în fața omului potrivit ce trebuie aprobat. Înregistrează motivul fiecărei respingeri. | Termene de aprobare |
| L3 Facturarea și abonamentele | D | Sincronizează planul, plata și accesul. Suspendă producția la neplată, după perioada de grație. | Webhook-uri verificate |
| L4 Monitorul de risc de plecare | D, apoi M | Urmărește semnalele de dezangajare și propune acțiuni. | Tu |
| L5 Asistentul de suport | L · T2 + H | Răspunde la întrebările clientului despre cont și livrabile. Escaladează restul. | Reguli de escaladare |

### 5.14 Numărătoarea

| Departament | Componente | Dintre care fără LLM |
| --- | --- | --- |
| A Conducere și strategie | 4 | 1 |
| B Platformă și operațiuni | 7 | 7 |
| C Cercetare și insight | 8 | 1 |
| D Brand și strategie de conținut | 5 | 0 |
| E Creație text | 10 | 0 |
| F Design și media | 8 | 5 |
| G Calitate și conformitate | 14 | 8 |
| H Distribuție și comunitate | 6 | 4 |
| I Reclame plătite | 6 | 4 |
| J Vânzări și CRM | 6 | 3 |
| K Analiză și învățare | 8 | 4 |
| L Clienți și finanțe | 5 | 3 |
| Total | 87 | 40 |
