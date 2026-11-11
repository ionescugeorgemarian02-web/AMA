## 3. Ce am schimbat față de cererea ta și de ce

Din cele 33 de piese, 18 rămân sau se extind, 5 se împart în componente mai mici, 7 se modifică și 3 se înlocuiesc. Am adăugat 34 de componente pe care lista nu le avea.

### 3.1 Cele trei înlocuiri

**#24 Metadata Scrubber & Hash Modifier devine G11 Proveniență și dezvăluire AI.**

- **Ce cerea:** ștergerea urmelor AI din fișiere și modificarea hash-ului, ca să evite penalizarea de conținut duplicat.
- **De ce nu:** platformele cer etichetarea conținutului AI realist și citesc metadatele de proveniență. AI Act, art. 50, cere marcare și dezvăluire. O unealtă făcută să ascundă originea AI pune în pericol conturile clienților și firma ta. Nici tehnic nu ajută: detecția de duplicate este perceptuală, nu pe hash de fișier.
- **Ce construim:** componenta păstrează metadatele de proveniență, setează eticheta AI pe fiecare platformă și ține un „pașaport” al fiecărui activ (modele, surse, licențe). Elimină doar date personale (GPS, serie de dispozitiv) din fișierele încărcate de client. Variația între platforme vine din adaptare nativă reală: alt hook, altă lungime, alt format.

**#26 Anti-Detect & Warmup devine H2 Gardianul limitelor și al sănătății conturilor.**

- **Ce cerea:** proxy-uri și întârzieri aleatorii care simulează comportament uman.
- **De ce nu:** prin API-urile oficiale, automatizarea este permisă și nu are nevoie de mascare. Mascarea servește doar automatizării neoficiale, care duce la conturi blocate. Conturile sunt ale clienților. Proxy-urile rezidențiale costă, deci încalcă și constrângerea de buget.
- **Ce construim:** componenta respectă limitele citite din API, urmărește expirarea tokenurilor, erorile și scăderile bruște de reach, apoi încetinește sau oprește singură. La email, încălzirea este reală: creștere treptată a volumului pe un subdomeniu dedicat, fără rețele de „warmup” simulate.

**#28 Lead Scraper & Email Verifier (și partea „cold” din #9) devine J1 Captare și îmbogățire conformă.**

- **Ce cerea:** extragerea de baze de date B2B și campanii de cold outreach.
- **De ce nu:** în România, emailul comercial nesolicitat cere consimțământ prealabil, inclusiv către firme (Legea 506/2004, art. 12). Extragerea în masă de date personale ridică și probleme de GDPR. Plângerile și amenzile ar lovi SRL-ul tău.
- **Ce construim:** captare prin formulare cu opt-in (audit gratuit, resurse), îmbogățire doar din date publice de firmă, liste de conturi-țintă pentru contact făcut de om. Modulul de email trimite doar către abonați. Cold email rămâne dezactivat implicit și se poate activa per țară numai după o matrice de conformitate validată de avocat.

### 3.2 Alte nouă corecții

| Ce ai cerut | Problema | Ce construim |
| --- | --- | --- |
| Claude orchestrează toți agenții | Abonamentul are limite pe ferestre de 5 ore și săptămânale, iar modul headless consumă din ele. Un orchestrator care depinde de ele se oprește des. | Orchestratorul este cod determinist. Claude este Consiliu și Strateg, pe cadență (secțiunea 7.6). |
| 33 de agenți, toți „inteligenți” | Fiecare apel LLM consumă cotă și poate greși. Montajul, publicarea, bugetele și monitorizarea nu au nevoie de LLM. | Fiecare componentă are tip declarat. LLM doar unde aduce valoare. |
| Avatar digital cu lip-sync | Cere GPU. Nivelurile gratuite ale serviciilor comerciale au de regulă filigran sau interzic uzul comercial. | Cinci formate fără avatar (secțiunea 14). Adaptor pregătit pentru GPU la cerere, mai târziu. |
| Machine learning la toți agenții | ML cere date. La lansare nu există. Un model antrenat pe 30 de exemple învață zgomot. | Învățare în trepte, fiecare pornită la un prag de date (secțiunea 11). |
| Autonomie totală | Un model gratuit care publică singur pe contul unui client plătitor este un risc de reputație. | Niveluri L0–L4, câștigate prin rezultate măsurate (secțiunea 7.4). |
| Scanare zilnică TikTok, Reels, Reddit | TikTok și Instagram nu au API oficial de tendințe, iar scraping-ul le încalcă termenii. Reddit gratuit este doar necomercial. | Surse oficiale plus un „inbox de tendințe” în care tu sau clientul lipiți linkuri (secțiunea 12). |
| Retenție la secundă pe toate platformele | Doar YouTube expune curba de retenție prin API. | YouTube: curbă completă. Restul: durată medie de vizionare și praguri de 3 secunde, 25%, 50%, 75%, 100%, unde există. |
| Comment Closer care șterge comentarii | Ștergerea criticilor este risc de reputație și de practică comercială incorectă. | Spamul și înșelătoriile se ascund. Negativul merge la om. Fiecare acțiune rămâne în jurnal. |
| Fallback automat pe modele mai ieftine | Corect pentru sarcini simple. Greșit pentru strategie: un model slab produce o strategie slabă, în tăcere. | Sarcinile strategice se amână până revine cota, nu se degradează. |

### 3.3 Fiecare dintre cele 33 de piese, la zi

| # | Piesa ta | Statut | Componente în noua arhitectură |
| --- | --- | --- | --- |
| 1 | Master Orchestrator | Păstrat, determinist | B1, B4, B7 |
| 2 | FinOps & Rate-Limit Filter | Extins | B2 |
| 3 | Trend & Viral Researcher | Modificat: surse oficiale | C2 |
| 4 | Competitor Ad Spy | Păstrat: biblioteci oficiale de reclame | C3 |
| 5 | ICP & Audience Profiler | Extins | C4, C5 |
| 6 | Offer & Funnel Architect | Păstrat | D2 |
| 7 | Hook & Video Scriptwriter | Împărțit | E1, E2 |
| 8 | Conversion Copywriter | Împărțit | E3, E4, E5 |
| 9 | Outbound & Email Sequence Writer | Modificat: doar opt-in | E6 |
| 10 | Technical & On-Page SEO | Împărțit | C6, E7 |
| 11 | Proofreader & Anti-AI Editor | Modificat: scopul este limbajul natural, nu păcălirea detectoarelor | E8, G10 |
| 12 | Native Localization & Translator | Păstrat, activat la nevoie | E9 |
| 13 | Visual Prompt Engineer | Păstrat | F2 |
| 14 | Ad Creative & Thumbnail Generator | Modificat: șabloane cu text exact, AI ca fundal | F3, F4 |
| 15 | Voiceover & Audio Synthesis | Păstrat, voce cu licență clară | F5 |
| 16 | Video & Avatar Generator | Modificat: fără avatar în v1 | F6 |
| 17 | FFmpeg Post-Production Assembler | Păstrat | F7 |
| 18 | Fact-Checker & Hallucination Filter | Extins: registru de fapte | G2 |
| 19 | Platform Policy & Ad-Ban Validator | Extins | G3, I5 |
| 20 | Brand Voice & Visual Auditor | Împărțit | G4, G5 |
| 21 | Technical Media QA Filter | Păstrat | G6 |
| 22 | Copyright & Plagiarism Scanner | Extins: registru de licențe | G7 |
| 23 | Readability & Conversion Scorer | Păstrat | G8 |
| 24 | Metadata Scrubber & Hash Modifier | Înlocuit | G11 |
| 25 | Multi-Channel Auto-Publisher | Păstrat, depinde de aprobări | H1, B7 |
| 26 | Anti-Detect & Warmup Filter | Înlocuit | H2 |
| 27 | Autonomous Media Buyer | Împărțit: LLM propune, regulile execută | I1, I2, I3, I4, I6 |
| 28 | Lead Scraper & Email Verifier | Înlocuit | J1 |
| 29 | Social Inbox & Comment Closer | Modificat | H3, H4 |
| 30 | CRM & Lead Qualification | Extins | J2, J3, J4 |
| 31 | Attribution & Retention Analyst | Modificat: retenție la secundă doar pe YouTube | K1, K2 |
| 32 | Self-Healing Prompt Optimizer | Extins, cu garduri | K5, K8 |
| 33 | Dead-Letter Queue & Watchdog | Păstrat | B3 |

Componentele noi acoperă ce lipsea pentru o companie întreagă: Consiliul și Strategul, managerul de experimente, strategul de brand, designerul de identitate, biroul de aprobări, verificările juridice și de confidențialitate, facturarea, onboardingul și raportarea către client.
