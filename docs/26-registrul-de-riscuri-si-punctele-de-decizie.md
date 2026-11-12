## 26. Registrul de riscuri și punctele de decizie

Registrul are 59 de riscuri în șase grupe, fiecare cu semnal timpuriu, control existent și reacție. Opt puncte de decizie spun dinainte când continui, când schimbi direcția și când te oprești.

### 26.1 Cum se citește și cum se ține la zi

- **Note.** P este probabilitatea, I este impactul, fiecare de la 1 la 3. Scorul este P × I. Toate notele sunt estimări \[I\].
- **Cadență.** Scor 6–9: îl urmărești săptămânal. Scor 3–4: lunar. Scor 1–2: trimestrial.
- **Proprietar.** Tu, până apare un operator. Un risc fără proprietar nu este urmărit de nimeni.
- **Unde stă.** În repo, în docs/registre. Se revede lunar, în rutina din secțiunea 22.10.
- **După un incident.** Riscul produs urcă la P 3 până se închide analiza de după incident.
- **Trimiteri.** Coloana „Control existent” arată secțiunea în care controlul este descris. Un risc fără control tehnic este marcat ca atare.

### 26.2 Platforme și furnizori

| Cod | Risc | P | I | Semnal timpuriu | Control existent | Reacție |
| --- | --- | --- | --- | --- | --- | --- |
| RP1 | Un nivel gratuit de modele este retras sau restrâns | 3 | 2 | Erori de cotă noi; anunț al furnizorului | Registru de furnizori, lanțuri de rezervă, model local încărcat permanent (8.1–8.4) | Procedura „furnizor retras” (22.9); testul comparativ se reia; se activează bugetul de inferență plătită (4.12) |
| RP2 | Modelele gratuite scriu slab în română | 2 | 3 | Scor sub prag la F3.6; aprobare din prima sub 70% | Lume închisă, exemple aprobate, pași mici (13.1); cascada de validare | Punctul de decizie PD2 |
| RP3 | O cerere de aprobare API este respinsă sau întârzie luni | 3 | 2 | Trei săptămâni fără schimbare de stare în tabelul de urmărire | Mod asistat pe fiecare canal (15.2); cereri în două valuri (15.3) | Refaci cererea cu observațiile primite; canalul rămâne asistat; clientul află cinstit starea |
| RP4 | O platformă își schimbă API-ul, limitele sau regulile de etichetare | 2 | 2 | Erori noi la conector; anunțuri pentru dezvoltatori | Teste de contract, limite citite din API, registru de conformitate verificat trimestrial (21.10) | Pas de reparație pe conector; canalul trece pe asistat până la remediere |
| RP5 | Contul unui client este restricționat | 1 | 3 | Avertisment de politică; scădere bruscă de reach | Doar API-uri oficiale, H2, G3; conturile clienților nu se folosesc la teste | Procedura „cont restricționat”; pauză pe client; analiză și regulă nouă |
| RP6 | Regulile abonamentului Claude se schimbă | 2 | 1 | Anunț; sesiuni fără interfață refuzate | Claude în afara căii critice (ADR-06); modul manual asistat (7.6) | Consiliul trece pe manual sau pe T3, cu eticheta „provizoriu” |
| RP7 | Domeniul de email capătă reputație proastă | 2 | 2 | Respingeri peste 2%; plângeri peste 0,1% | Subdomeniu dedicat, creștere treptată, listă de suprimare, praguri de oprire (17.3) | Oprire automată; curățarea listei; reluare la volum mic |
| RP8 | Procesatorul de plăți își schimbă API-ul sau blochează contul | 1 | 3 | Webhook-uri eșuate; mesaj al procesatorului | Facturarea trece printr-un adaptor; starea abonamentului stă și în platformă (19.5) | Încasare manuală, prin factură și transfer, până la remediere |
| RP9 | Licența unui activ de stock sau a unei piese muzicale este contestată | 1 | 2 | Reclamație de drepturi pe o postare | Copia licenței la data descărcării; pașaportul activului (14.3, 14.8) | Retragi activul din bibliotecă; re-randezi materialele afectate |

### 26.3 Tehnice și de operare

| Cod | Risc | P | I | Semnal timpuriu | Control existent | Reacție |
| --- | --- | --- | --- | --- | --- | --- |
| RT1 | VPS-ul dedicat cade sau pierde date | 2 | 3 | Alerte de disc; reporniri neașteptate | Backup extern zilnic, testat prin restaurare; documentație de reinstalare (22.6, 22.7) | Procedura „restaurare completă pe un server nou” |
| RT2 | Procesorul, nu memoria, limitează paralelismul | 2 | 2 | Așteptare peste 15 minute la culoarele grele; nuclee partajate cu alți chiriași ai furnizorului | Semafor pe culoare, prioritate pentru producție, loturi randate dinainte (6.4, 14.11) | Punctele de decizie PD1 și PD5 |
| RT3 | Serviciile permanente își iau memorie unul altuia la vârf | 2 | 2 | Un serviciu își atinge limita; procese oprite de sistem | Limită pe fiecare serviciu și rezervă de 3 GB (6.4) | Scazi mărimea modelului local sau renunți la un culoar |
| RT4 | Discul se umple cu fișiere media | 2 | 2 | Alerta de 70% | Păstrare de 90 și de 7 zile, curățare automată, oprirea randărilor la 85% (6.5, 22.3) | Arhivare externă mai devreme; calitate mai mică la ciorne |
| RT5 | Un efect extern se execută de două ori | 2 | 3 | Două identificatoare de platformă pentru aceeași cheie | Chei de idempotență; verificare la platformă înainte de reîncercare (7.3) | Ștergi dublura; analiză; test de avarie nou |
| RT6 | Un material ajunge pe contul altui client | 1 | 3 | Test de izolare picat; nepotrivire între client și conector | Izolare la nivel de rând, client în cheia de idempotență, previzualizare cu numele contului (21.1) | Procedura „publicare greșită”; oprire globală până la aflarea cauzei |
| RT7 | O buclă între agenți consumă cotele | 2 | 2 | Consum neobișnuit pe un livrabil | Bugete per livrabil, limită de predări, întrerupător global (7.3) | Livrabilul merge la om; limita se strânge |
| RT8 | O dependență sau o imagine este compromisă | 1 | 3 | Alertă de vulnerabilitate; trafic de ieșire neobișnuit | Versiuni fixate cu hash, imagini pe amprentă, scanare în CI, gateway propriu (21.5) | Procedura „token compromis”: rotești toate cheile și revii la versiunea anterioară |
| RT9 | Serviciul intern de livrare este folosit abuziv | 1 | 3 | Livrare pornită fără cerere de integrare aprobată | Listă fixă de acțiuni, autentificare, fără expunere publică, urmă în audit (22.8) | Oprești serviciul; livrezi manual; revizuire de securitate |
| RT10 | Un secret ajunge în repo, în jurnale sau într-un prompt | 1 | 3 | Scanarea de secrete; cheie folosită din alt loc | Secrete în afara repo-ului, tokenuri criptate, mascare înainte de jurnal (21.2) | Secretul se consideră compromis și se schimbă imediat |
| RT11 | Un text extern manipulează un agent | 2 | 2 | G13 înregistrează tentative | Conținut extern marcat ca dată; agenți de cercetare fără unelte cu efecte (12.8, 21.6) | Sursa intră pe lista interzisă; cazul intră în colecția de atacuri |
| RT12 | Modelul local este prea lent ca să ajute | 2 | 1 | Sub câțiva tokeni pe secundă la F3.5 | Model ținut încărcat; folosit întâi la clasificări și extrageri scurte (6.4, 8.2) | Model mai mic; modelul local rămâne doar rezervă și embeddings |
| RT13 | Backupul există, dar nu se poate restaura | 2 | 3 | Restaurarea de test eșuează sau nu rulează | Restaurare automată săptămânală; exercițiu complet trimestrial (22.6) | Lansarea se blochează până trece o restaurare |
| RT14 | Instalarea inițială a VPS-ului nu se poate face fără administrator | 1 | 2 | Pasul F0.4 se blochează | După instalare, totul rulează în Docker, ca utilizator obișnuit | Furnizorul sau un administrator face instalarea o singură dată, după lista din Ș3 |

### 26.4 Calitate și reputație

| Cod | Risc | P | I | Semnal timpuriu | Control existent | Reacție |
| --- | --- | --- | --- | --- | --- | --- |
| RC1 | Un fapt greșit este publicat | 2 | 3 | Contestații pe G2; corecturi ale clientului | Registru de fapte, comparație exactă a cifrelor, aprobare umană la L1 (9.3) | Corectezi sau ștergi postarea; faptul se repară în registru; exemplul intră în setul de aur |
| RC2 | Conținutul iese generic și clientul nu vede valoare | 3 | 2 | Aprobare din prima sub 70%; multe editări; portal nedeschis | Exemple de aur, exemple negative, formatul E, playbook pe nișă | Recalibrezi Creierul împreună cu clientul; ceri mai mult material real |
| RC3 | Vocea sintetică sună nenatural | 2 | 2 | Respingeri repetate la video, cu motivul „altceva” | Normalizare, transcriere inversă, dicționar de pronunție (14.4) | Voce proprie antrenată; mai mult format E; video fără voce |
| RC4 | Un judecător automat derivă și aprobă prea ușor | 2 | 2 | Rata de trecere se schimbă fără schimbare de prompt | Calibrare săptămânală, seturi de aur, alt model decât autorul (9.6) | Judecătorul revine la versiunea anterioară; eșantionul uman crește |
| RC5 | Învățarea optimizează indicatorul greșit | 2 | 2 | Indicatorii de gardă urcă | Constituția: obiectiv compus, grup de control, o schimbare pe săptămână (11.6) | Revenire dintr-o atingere; înghețarea învățării |
| RC6 | Un răspuns nepotrivit pleacă din inbox | 2 | 3 | Reclamație; conversație escaladată târziu | Răspunsuri doar din registrul de fapte; escaladare pentru critică și subiecte sensibile (17.8) | Inboxul clientului coboară la L1; regula de escaladare se completează |
| RC7 | O reclamă este respinsă sau contul de reclame este restricționat | 2 | 3 | Respingeri repetate; avertisment pe cont | I5, G3, G9; campanii pornite în pauză (16.8) | Oprire pe cont; contestație făcută de om; regulă nouă în pachet |
| RC8 | Cheltuiala de reclame scapă de sub control | 1 | 3 | Ritm orar peste plan | Plafoane în contract și în platformă, I3, I6, bani pe cardul clientului (16.4, 16.5) | Oprirea de urgență; repornire doar manuală |
| RC9 | Agenția își strică imaginea cu propriul conținut | 2 | 2 | Comentarii despre „conținut făcut de AI” | Pagina publică de transparență AI; formatul E pentru vocea fondatorului | Mai puțin volum, mai mult material real |

### 26.5 Juridice și de conformitate

| Cod | Risc | P | I | Semnal timpuriu | Control existent | Reacție |
| --- | --- | --- | --- | --- | --- | --- |
| RJ1 | Încadrarea sub AI Act, art. 50, este alta decât cea presupusă | 2 | 2 | Răspunsul avocatului; ghiduri noi | Marcare și etichetare construite din prima versiune (21.9) | Se aplică încadrarea avocatului; pachetul de reguli se actualizează |
| RJ2 | Incident de date personale | 1 | 3 | Acces neobișnuit; test de izolare picat | Izolare, mascare, minimizare, acord de prelucrare (21.1, 21.7) | Procedura „suspiciune de scurgere”; notificare în 72 de ore, când legea o cere |
| RJ3 | O comunicare comercială pleacă fără temei | 1 | 3 | Plângere; adresă fără dovadă de consimțământ | Opt-in dublu, listă de suprimare, matricea pe țări verificată la fiecare trimitere (17.3, 17.4) | Oprești campania; răspunzi plângerii; verifici sursa contactului |
| RJ4 | Un client dintr-o nișă reglementată cere promisiuni nepermise | 2 | 2 | G9 blochează des același tip de afirmație | Lista de nișe refuzate, reguli pe nișă, om pe nișele sensibile (21.12) | Refuzi cererea; dacă insistă, închizi contractul |
| RJ5 | Un text sau un activ încalcă drepturile altcuiva | 2 | 2 | G7 aproape de prag; reclamație | Registru de licențe, verificare de aproape-duplicate, „se analizează, nu se copiază” (12.6) | Retragere, înlocuire, exemplu nou în setul de aur |
| RJ6 | Vocea de pornire nu are drept comercial clar | 2 | 2 | Răspunsul avocatului, la F8.1 | Statutul licenței scris în registrul de active (14.4) | Voce proprie, cu acord scris; până atunci, video fără voce sau format E |
| RJ7 | Un client cere despăgubiri pentru lipsa rezultatelor | 2 | 2 | Nemulțumire în întâlnirile lunare | Contract fără promisiune de rezultat, răspundere limitată, aprobare obligatorie (4.11) | Discuție, plan de corecție, reziliere cu preaviz |
| RJ8 | Date confidențiale ajung la un furnizor fără garanții contractuale | 2 | 2 | Apel extern cu date nemascate, găsit la audit | G12 înainte de orice apel; model local pentru date confidențiale; termenii furnizorilor în registru (8.1, 8.9) | Furnizorul iese din rutarea acelui client; clientul este informat, dacă e cazul |
| RJ9 | Facturarea, e-Factura sau TVA-ul sunt tratate greșit | 2 | 2 | Întrebări ale contabilului rămase deschise | Confirmare cu contabilul înainte de F7.6 (4.11) | Facturare manuală până la confirmare |

### 26.6 Comerciale și financiare

| Cod | Risc | P | I | Semnal timpuriu | Control existent | Reacție |
| --- | --- | --- | --- | --- | --- | --- |
| RB1 | Nișa aleasă nu cumpără la prețul propus | 2 | 3 | Sub 3 din 10 discuții ajung la cerere de ofertă | Zece discuții de vânzare înainte de publicarea prețurilor (4.5) | Punctul de decizie PD6 |
| RB2 | Timpul tău per client rămâne peste două ore pe lună | 3 | 3 | Minutele măsurate pe ecranul Aprobări, în pilot | Aprobare în grup, motive standard, promovare la L2 (18.3, 7.4) | Punctul de decizie PD7 |
| RB3 | Modul asistat cere timp nebugetat | 3 | 2 | Minute de publicare manuală per client | Pachet gata de partajat din două atingeri (15.2). Calculul din 4.6 nu include acest timp | Clientul postează el, din portal; mai puține canale până la aprobări |
| RB4 | Cotele gratuite opresc creșterea la circa 10 clienți | 3 | 2 | Cotă folosită peste 60% | Prețul-umbră arată costul real per livrabil (8.5); modelul local preia sarcinile simple | Treapta 2: 3–5% din venit în inferență plătită |
| RB5 | Totul depinde de tine | 3 | 3 | Aprobări expirate când lipsești | Proceduri scrise și roluri. Fără control tehnic: nimic nu se publică fără aprobare, deci o absență oprește livrarea | Un operator de rezervă, cu rolul Operator, instruit pe rutina zilnică |
| RB6 | Clienții nu aprobă la timp | 3 | 2 | Livrabile expirate; reamintiri ignorate | Termen de 48 de ore, reamintire, aprobare în grup, clauză în contract (19.4) | Apel scurt; lot săptămânal aprobat într-o singură ședință; L2 când criteriul este atins |
| RB7 | Venitul stă în doi-trei clienți | 2 | 2 | Un client trece de 40% din venit | Pâlnia de audit pornită permanent (4.8) | Prioritate pe vânzări, până la cinci clienți |
| RB8 | Clientul crede că poate face singur, cu un asistent AI | 3 | 2 | Obiecția apare în discuțiile de vânzare | Livrabile numărabile, playbook pe nișă, publicare, măsurare și raport incluse (4.1) | Demonstrația de pe feed-ul agenției; studii de caz |
| RB9 | Facturi neplătite | 2 | 1 | Plată eșuată | Perioadă de grație de 7 zile, apoi suspendare (19.5) | Reamintire, apoi suspendare; datele rămân |
| RB10 | O cheltuială nouă nu se întoarce | 2 | 1 | Minutele per client nu scad după cheltuială | Regula din 4.12: se aprobă doar ce scade minutele sau crește retenția, măsurat | Cheltuiala se oprește la următoarea reînnoire |
| RB11 | VPS-ul dedicat costă lunar înainte de primul client | 3 | 1 | Luni de construcție fără venit | Clienții zero și discuțiile de vânzare pornesc la poarta F6 (23.9) | Punctul de decizie PD8; pilot pe pachetul Start, ca venitul să apară mai devreme |

### 26.7 De construcție

| Cod | Risc | P | I | Semnal timpuriu | Control existent | Reacție |
| --- | --- | --- | --- | --- | --- | --- |
| RX1 | Agentul de cod declară „gata” fără dovezi | 3 | 2 | Raport fără ieșirea testelor; „Gata când” nu se vede pe staging | Regulile de sesiune, revizor cu alt model, verificare făcută de tine (24.3, 24.4) | Pasul se redeschide; pasul următor nu pornește |
| RX2 | Arhitectura se abate treptat de la decizii | 2 | 2 | Dependențe noi; apeluri la modele în afara gateway-ului | Fișierul de reguli, lista lucrurilor interzise, revizuire obligatorie pe modulele sensibile (24.2) | Pas de curățare înaintea fazei următoare |
| RX3 | Construcția durează dublu | 3 | 2 | Sub 8 pași închiși pe săptămână | Porți după fiecare fază; drumul critic din 23.21 | Fazele F11–F14 se mută după lansare; pilotul pornește pe pachetul Start |
| RX4 | Specificația unui pas este ambiguă | 2 | 2 | Agentul pune multe întrebări sau face multe presupuneri | Șablonul Ș5, cu „ce nu se construiește” și teste de acceptare | Specificația se rescrie înainte de cod, nu în timpul lui |
| RX5 | Nu poți judeca singur dacă un pas este corect | 2 | 2 | Aprobi fără să fi văzut criteriul | Criterii observabile din panou, raport de sesiune, revizor independent, lista Ș10 | Ceri revizorului o demonstrație pe staging, pas cu pas |
| RX6 | Platforma devine prea mare pentru un singur om | 3 | 2 | Faze începute și neterminate; funcții nefolosite | Comutatoare de funcții; se construiește doar ce cere pachetul vândut (23.21) | Îngheți extensiile; o lună doar de stabilitate (25.7) |
| RX7 | Limitele abonamentelor pentru agenții de cod încetinesc lucrul | 2 | 1 | Sesiuni întrerupte | Pași mici; tot contextul stă în repo (24.10) | Alternezi modelele; muți revizuirea pe celălalt model |

### 26.8 Primele zece, în ordinea atenției

Ordinea este o judecată, nu un calcul: scorurile egale sunt departajate după cât de devreme pot lovi.

| Loc | Risc | De ce este sus | Când îl măsori prima dată |
| --- | --- | --- | --- |
| 1 | RB2 Timpul tău per client | Decide dacă afacerea are profit | F6.8, apoi în pilot |
| 2 | RB5 Totul depinde de tine | O absență de o săptămână oprește livrarea | Înainte de pilot |
| 3 | RP2 Calitatea în română | Dacă textul este slab, restul nu contează | F3.6 |
| 4 | RC1 Fapt greșit publicat | Un singur caz poate costa un client | Poarta F5 |
| 5 | RB1 Nișa nu cumpără | Fără cumpărători, platforma nu are rost | De la poarta F6 |
| 6 | RP3 Aprobările API | Hotărăsc cât timp publici manual | F0.6, apoi la fiecare conector |
| 7 | RT1 VPS-ul unic | Totul stă pe un singur server | F1.9 |
| 8 | RX1 „Gata” fără dovezi | Greșelile ascunse se adună de la un pas la altul | De la F1.1 |
| 9 | RC2 Conținut generic | Duce la plecarea clienților | F6.8 |
| 10 | RP1 Niveluri gratuite retrase | S-a întâmplat de mai multe ori în 2026 | Lunar |

### 26.9 Puncte de decizie

Pragurile sunt valori de pornire \[I\]. Le poți schimba, dar înainte de măsurătoare, nu după.

| Cod | Moment | Ce măsori | Continui dacă | Altfel |
| --- | --- | --- | --- | --- |
| PD1 | După F0.4 | Nucleele, memoria, discul, viteza procesorului | Cel puțin 8 nuclee și 24 GB | 4–7 nuclee: un singur culoar greu și model local mai mic. Sub 4 nuclee sau sub 16 GB: alt VPS, înainte de F1.8 |
| PD2 | După F3.6 | Scorul în română pe profilurile de creație și de judecată | Cel puțin două modele cu uz comercial permis trec pragul pe fiecare profil | Buget lunar mic de inferență plătită pe acele profiluri, de la început. Dacă nu accepți cheltuiala, proiectul se oprește aici |
| PD3 | Poarta F5 | Blocarea materialelor intenționat greșite | 95% blocate; cel mult 10% respinse pe nedrept | Nu treci la F6. Repari validatorii |
| PD4 | Poarta F6 | Aprobarea din prima, după 14 zile | Peste 70% și în creștere | O săptămână de lucru pe prompturi, exemple și Creier, înainte de F7 |
| PD5 | După F8.9 | Minute per video, cu toate culoarele ocupate | Sub 10 minute per video | Formatul B ca implicit, loturi randate dinainte, mai puține video pe pachet sau VPS cu mai multe nuclee |
| PD6 | Înainte de pilot | Zece discuții de vânzare | Cel puțin 3 firme cer ofertă la prețul propus | Schimbi oferta sau nișa și repeți |
| PD7 | Sfârșitul pilotului | Minute de om per client; aprobarea din prima; incidente critice | Sub 120 de minute, fără publicarea asistată; peste 85%; zero | Nu lansezi. Repari cauza cea mai mare și prelungești pilotul cu patru săptămâni |
| PD8 | La trei luni după lansare | Churn lunar, venit pe ora ta, cotă folosită | Churn sub 5%; venitul acoperă costurile fixe și timpul tău | Îngheți achiziția. Lucrezi pe retenție sau pe preț |

### 26.10 Ce rămâne deschis

Aceste puncte se adaugă necunoscutelor din secțiunea 2.3. Fiecare are un pas în care se închide.

| Întrebare | Cine răspunde | Pas |
| --- | --- | --- |
| Numele agenției și domeniul | Tu | F0.1 |
| Nucleele, discul și drepturile de pe VPS-ul dedicat | Tu, din panoul furnizorului | F0.4 |
| Ce platforme cer demonstrația fluxului încă de la prima cerere | Tu, din pagina fiecărei cereri | F0.6 |
| Unde stă backupul extern și cât încape | Tu și agentul de cod | F1.9 |
| Ce mărime de model local merită, pe procesorul real | Agentul de cod, prin test | F3.5 |
| Cu ce instrument se emit facturile și cum intră e-Factura | Tu și contabilul | F7.6 |
| Cine postează în modul asistat pe conturile clienților: tu sau clientul | Tu, cu fiecare client | F15.5 |
| Furnizorul de email și limitele nivelului lui gratuit | Tu și agentul de cod | F12.2 |
| Bugetul campaniei de probă a agenției | Tu | F13.10 |
