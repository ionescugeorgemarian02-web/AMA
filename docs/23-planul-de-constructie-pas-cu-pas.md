## 23. Planul de construcție pas cu pas

Construcția are 17 faze și 146 de pași. Fiecare pas este o sesiune cu agentul de cod, are un rezultat pe care îl poți verifica fără să citești cod și nu începe până când pasul anterior nu și-a trecut criteriul.

### 23.1 Cum se folosește planul

- **Un pas = o sesiune = o ramură = o cerere de integrare.**
- **„Gata când”** este testul pasului. Îl verifici din panou, de pe staging sau din raportul CI.
- **Ce primește agentul de cod:** acest document, specificația pasului (șablonul Ș5 din secțiunea 27.2) și starea repo-ului.
- **Detalii pe pas:** secțiunea 27.3 arată pentru fiecare pas cine îl face, de ce depinde, ce secțiuni se citesc și ce pregătești tu înainte.
- **Cine face ce:** pașii din F0 sunt ai tăi. Restul sunt ai agentului de cod, dacă nu scrie altfel. Verificarea criteriului este întotdeauna a ta.
- **Ordinea:** pașii F0.1–F0.4 se încheie înainte de faza F1. Restul fazei F0 curge în fundal. Fazele F1–F6 merg strict în serie. De la faza F7 încolo, unele pot alterna (secțiunea 23.20).
- **Porți:** după fiecare fază există o poartă. Dacă nu trece, nu se merge mai departe.

### 23.2 Privire de ansamblu

| Fază | Rezultat | Pași | Durată estimată \[I\] | Poarta de ieșire |
| --- | --- | --- | --- | --- |
| F0 Fundație | Decizii, conturi, cereri de aprobare, juridic pornit | 8 | 3–5 zile; de la F0.5, în paralel cu F1 | Cererile din primul val sunt trimise și VPS-ul dedicat este pregătit și măsurat |
| F1 Schelet | Aplicație goală, sigură, livrată pe staging | 10 | 4–5 zile | Autentificare, izolare pe client și backup testate |
| F2 Motor | Mașina de stări și execuția durabilă | 10 | 4–5 zile | Un livrabil de probă supraviețuiește unei reporniri |
| F3 Gateway | Modelele gratuite sub control | 11 | 4–6 zile | Testul comparativ pe română este rulat |
| F4 Creierul de brand | Onboarding, memorie, insight și prima strategie | 11 | 4–5 zile | Brandurile proprii au Creier și strategie pe 90 de zile, aprobate |
| F5 Validare | Cascada și biroul de aprobări | 10 | 4–5 zile | 95% din materialele intenționat greșite sunt blocate |
| F6 Text | Postări și scripturi, publicare asistată | 8 | 3–4 zile, apoi 14 zile de probă | Două săptămâni de conținut real pentru brandurile proprii |
| F7 Site și portal | Site complet, portal, facturare, pagini de captare, articole | 10 | 4–5 zile | Un client de test parcurge onboardingul și plătește în mediul de probă |
| F8 Media | Voce, video, creativuri | 12 | 5–6 zile | Zece video trec controlul media fără intervenție |
| F9 Publicare | Conectori API, pe măsura aprobărilor | 10 | 1–2 sesiuni per canal | O postare publică prin API pe fiecare canal aprobat |
| F10 Analiză și cercetare | Metrici, rapoarte, tendințe, concurență | 8 | 3–4 zile | Raport lunar generat din date reale |
| F11 Învățare 1 | Playbook și alegere adaptivă | 6 | 2–3 zile | O lecție promovată și una retrasă |
| F12 CRM și inbox | Pâlnia de audit, email, conversații, suport | 10 | 4–5 zile | Un lead real parcurge pâlnia cap-coadă |
| F13 Reclame și Strateg | Reclame cu plafoane, Consiliu | 10 | 4–5 zile, apoi 14 zile de campanie | Oprirea de urgență testată pe o campanie reală |
| F14 Învățare 2 | Optimizare, predicție, teste formale | 6 | 2–3 zile, când există date | Un prompt optimizat bate campionul |
| F15 Lansare | Întărire, pilot, lansare comercială | 6 | 4–6 săptămâni | Trei clienți-pilot activi, zero incidente critice |
| F16 Extensii | Formate și piețe noi | – | După nevoie | – |

În total sunt 146 de sesiuni de cod. Fiecare mai cere o sesiune scurtă de specificație și una de revizuire (secțiunea 24). La 2–3 pași închiși pe zi, înseamnă 2–3 luni de lucru, plus așteptarea aprobărilor, a probelor și a pilotului. O lansare comercială realistă: 3–4 luni \[I\]. Publicarea automată pe conturile clienților poate veni după lansare, pe măsura aprobărilor.

### 23.3 F0 – Fundația fără cod

- **F0.1 Decizii de pornire.** Alegi nișa-pilot, pachetul-pilot și numele agenției. *Gata când:* cele trei decizii sunt scrise în fișierul de decizii din repo.
- **F0.2 Repo și reguli.** Creezi repo-ul privat. Agentul de cod adaugă fișierul de reguli pentru agenți, șablonul de cerere de integrare, structura de directoare și acest document. *Gata când:* ramura principală este protejată și CI rulează un prim test.
- **F0.3 Inventarul modelelor.** Listezi fiecare furnizor și cheie pe care le ai: modele, limite, termeni de uz comercial. Decizi dacă plătești cei 10 USD la OpenRouter. *Gata când:* inventarul (șablonul Ș2 din secțiunea 27.2) este completat.
- **F0.4 Pregătirea și măsurarea VPS-ului dedicat.** Notezi nucleele, memoria și discul. Agentul de cod scrie instalarea inițială (Docker, firewall, utilizator fără drepturi de administrator, proxy cu certificate), iar tu o rulezi o singură dată ca administrator. Rulezi un test scurt de viteză pe procesor. *Gata când:* fișa de măsurare (șablonul Ș3) este în repo, tabelul din secțiunea 6.4 este refăcut pentru nucleele reale și punctul de decizie PD1 este închis.
- **F0.5 Site minim.** Agentul de cod publică pagini statice: Acasă, Contact, Termeni, Confidențialitate, Cookie-uri, Transparență AI, Ștergerea datelor. *Gata când:* sunt publice pe domeniu, pe HTTPS.
- **F0.6 Cereri de aprobare.** Parcurgi primul val din secțiunea 15.3. *Gata când:* fiecare cerere are stare și dată în tabelul de urmărire (șablonul Ș4).
- **F0.7 Juridic.** Trimiți avocatului lista din secțiunea 21.13. *Gata când:* ai un termen de la avocat și șabloane de lucru.
- **F0.8 Conturile agenției.** Creezi paginile sociale ale agenției și le folosești normal, manual, câteva săptămâni. *Gata când:* există și au activitate reală.

### 23.4 F1 – Scheletul platformei

- **F1.1 Aplicația de bază.** Structură modulară, pagină de sănătate, configurare din fișiere de mediu, jurnale structurate. *Gata când:* pornește în CI și răspunde la verificarea de sănătate.
- **F1.2 Dependențe fixate.** Fișier de blocare cu hash-uri, imagini fixate, scanare de secrete și de vulnerabilități în CI. *Gata când:* CI pică la o dependență nefixată și la un secret de probă.
- **F1.3 Baza de date și migrările.** Postgres dedicat, cu extensiile necesare, și prima migrare. *Gata când:* migrarea rulează înainte și înapoi în CI.
- **F1.4 Clienți, utilizatori, roluri.** Modelul de conturi și izolarea la nivel de rând. *Gata când:* testul care încearcă să citească datele altui client eșuează corect.
- **F1.5 Autentificare.** Parolă, al doilea factor, sesiuni, limită de încercări. *Gata când:* te autentifici pe staging de pe telefon, cu al doilea factor.
- **F1.6 Jurnalul de audit și de evenimente.** *Gata când:* fiecare acțiune de test apare în jurnal, cu utilizator și moment.
- **F1.7 Coaja panoului.** Aplicație instalabilă, bara de jos, ecranul Acasă gol, tema vizuală. *Gata când:* o instalezi pe telefon și primești o notificare de test.
- **F1.8 Livrarea.** Compose pentru staging și producție, limitele de memorie din secțiunea 6.4, staging pornit permanent, livrare din CI, promovare din panou. *Gata când:* o schimbare ajunge pe staging fără comenzi scrise de tine.
- **F1.9 Backup.** Copie zilnică criptată spre stocare externă și restaurare de test săptămânală. *Gata când:* o restaurare automată trece și apare în panou.
- **F1.10 Botul Telegram.** Alerte și comenzile de oprire. *Gata când:* primești o alertă de test și comanda de stare răspunde.

**Poarta F1:** autentificarea, izolarea, livrarea și backupul funcționează pe staging.

### 23.5 F2 – Motorul

- **F2.1 Execuția durabilă.** Integrarea bibliotecii de workflow-uri peste Postgres. *Gata când:* un workflow de probă oprit la mijloc reia de la ultimul pas după repornire.
- **F2.2 Cozile.** Cozile din secțiunea 7.5, cu limite de rată, priorități și culoarele grele. *Gata când:* cu două culoare configurate, din trei joburi grele trimise simultan două rulează în paralel, iar al treilea așteaptă.
- **F2.3 Mașina de stări a livrabilului.** Stările și tabelul de tranziții din secțiunea 7.2. *Gata când:* o tranziție nepermisă este refuzată și înregistrată.
- **F2.4 Limite anti-buclă.** Bugete per livrabil, limita de reparații și de predări, întrerupătorul global. *Gata când:* un livrabil de probă care eșuează mereu se oprește la limită și ajunge la om.
- **F2.5 Executorul de efecte externe.** Tabelul „de trimis”, chei de idempotență, un conector fals pentru teste, oprirea publicării (global și pe client). *Gata când:* același efect trimis de două ori se execută o singură dată, iar cu oprirea globală activă nu pleacă niciun efect nou.
- **F2.6 Planificatorul de timp.** Joburi recurente și sloturi. *Gata când:* un job programat rulează la minut pe staging.
- **F2.7 Watchdog și coada de erori.** Semnale de viață, joburi blocate, reîncercări, triere, ecranul Alerte. *Gata când:* un worker oprit forțat este repornit și jobul lui se reia.
- **F2.8 Cererile de aprobare.** Obiectul de aprobare, termene, expirare, notificări. *Gata când:* o aprobare neprimită la timp duce la „expirat”, nu la publicare.
- **F2.9 Ecranele Producție și Operare.** *Gata când:* vezi fiecare pas al unui livrabil de probă și poți relua din panou un pas eșuat.
- **F2.10 Nivelurile de autonomie.** Matricea pe client și pe clasă de acțiune. *Gata când:* același livrabil de probă cere aprobare la L1 și trece singur la L2.

**Poarta F2:** un livrabil de probă parcurge toate stările, supraviețuiește unei reporniri și nu produce efecte duble.

### 23.6 F3 – Gateway de modele

- **F3.1 Registrul de furnizori și modele.** *Gata când:* furnizorii din inventar apar în panou, cu limite și termeni.
- **F3.2 Clientul unificat.** Un singur mod de a apela orice furnizor compatibil, cu ieșiri structurate și o reparație. *Gata când:* același apel de probă reușește pe trei furnizori diferiți.
- **F3.3 Limitatoarele de cotă.** Contoare persistente, citirea antetelor, rezerva de 10%. *Gata când:* la atingerea unei limite simulate, apelurile se amână în loc să eșueze.
- **F3.4 Rutarea și lanțurile de rezervă.** Profilurile din secțiunea 8.2. *Gata când:* cu un furnizor oprit, munca trece pe următorul, iar o sarcină de strategie se amână, nu se degradează.
- **F3.5 Modelul local și modelul de embeddings.** Model local de text ținut încărcat permanent; generarea ocupă un culoar greu. Modelul de embeddings, separat, în worker-light. Test de viteză pe procesorul real, cu două-trei mărimi de model. *Gata când:* o clasificare de probă rulează local, în limitele de memorie, viteza fiecărui model este notată în registru, iar un vector se calculează în timp ce toate culoarele grele sunt ocupate.
- **F3.6 Testul comparativ pe română.** Set de 60–100 de sarcini, rulat pe fiecare model, cu evaluare automată și umană. *Gata când:* fiecare model are scor pe fiecare profil și rutarea folosește scorurile.
- **F3.7 Registrul de prompturi și jurnalul de apeluri.** *Gata când:* orice apel se vede în panou, cu prompt, model, tokeni, durată și preț-umbră.
- **F3.8 Bugete și priorități.** *Gata când:* un client de test care își depășește bugetul are P2 amânat și P0 neatins.
- **F3.9 Garda de date personale și garda de injecții.** Mascare înainte de apel și marcarea conținutului extern. *Gata când:* colecția de date de probă este mascată integral și colecția de atacuri nu schimbă comportamentul.
- **F3.10 Ecranul „Modele și cote”.** *Gata când:* vezi cota rămasă pe fiecare furnizor și consumul pe client.
- **F3.11 Planificatorul de capacitate (A4).** Compară zilnic munca planificată cu cotele și cu timpul de CPU. Amână ce nu încape, după termen și prioritate. *Gata când:* la un calendar de probă care depășește cota zilei, livrabilele cu termen îndepărtat sunt amânate, cele cu termen apropiat rămân neatinse și o alertă spune ce nu a încăput.

**Poarta F3:** testul comparativ este rulat, iar pierderea oricărui furnizor nu oprește platforma.

### 23.7 F4 – Creierul de brand și onboarding

- **F4.1 Modelul Creierului.** Compartimentele din secțiunea 10.1, cu versiuni. *Gata când:* o schimbare creează o versiune nouă și cea veche rămâne citibilă.
- **F4.2 Colectorul de surse.** Crawl politicos, extragere de text, păstrarea originalului. *Gata când:* site-ul unui brand propriu este citit integral, cu respectarea robots.txt.
- **F4.3 Vectori și căutare hibridă.** *Gata când:* o întrebare de probă găsește pasajul corect din materialele clientului.
- **F4.4 Asistentul de onboarding.** Interviul din secțiunea 19.3, cu întrebări de clarificare. *Gata când:* un interviu de probă produce un brief complet, fără câmpuri goale.
- **F4.5 Profilul de brand.** Trei variante de ton cu exemple, apoi aprobare. *Gata când:* profilul unui brand propriu este aprobat de tine.
- **F4.6 Registrul de fapte și catalogul de oferte.** Extragere din materiale, aprobare, valabilitate. *Gata când:* fiecare fapt are sursă și niciun fapt neaprobat nu intră în context.
- **F4.7 Constructorul de context.** Pachetul din secțiunea 10.3, cu buget de tokeni. *Gata când:* pentru o sarcină de probă, pachetul conține faptele potrivite și se vede în urma livrabilului.
- **F4.8 Ecranul „Creierul de brand”.** *Gata când:* editezi și aprobi de pe telefon.
- **F4.9 Profilul de public și vocea clientului (C4, C5).** Profilul clientului ideal și citate reale din recenzii, comentarii și întrebări frecvente, fără date personale. *Gata când:* fiecare brand propriu are profilul de public aprobat și cel puțin 20 de citate cu sursă în compartimentul „Insight de public”.
- **F4.10 Harta pieței și brieful de insight (C7, C8).** Ofertele, prețurile și mesajele a 3–5 concurenți, apoi sinteza de o pagină, cu citări. *Gata când:* în brieful unui brand propriu fiecare afirmație este legată de o sursă, iar verificarea prin sondaj a citatelor trece.
- **F4.11 Strategia pe 90 de zile, prima formă (A2).** Ipoteză, plan pe 30 și 90 de zile, indicator principal, prag minim, fereastră de măsurare și criteriu de oprire. Revizuirile și pivotul vin în F13.6. *Gata când:* fiecare brand propriu are o strategie aprobată de tine, cu toate elementele completate, vizibilă pe ecranul Campanii.

**Poarta F4:** CariereAI și BigBrain au fiecare un Creier de brand și o strategie pe 90 de zile, aprobate.

### 23.8 F5 – Validare și aprobări

- **F5.1 Cadrul de validare.** Forma verdictului, cascada, agregarea, bucla de reparație. *Gata când:* un validator de probă blochează și trimite autorului instrucțiunea de corectare.
- **F5.2 Validatorii de structură și de limbă (G1, G10).** *Gata când:* textele fără diacritice sau peste limită sunt respinse.
- **F5.3 Verificatorul de fapte (G2).** Extragerea afirmațiilor și potrivirea cu registrul. *Gata când:* un text cu un preț greșit și unul cu o afirmație neacoperită sunt blocate.
- **F5.4 Pachetele de reguli și validatorul de politici (G3).** Reguli versionate, pe platformă și pe nișă. *Gata când:* fiecare regulă are un exemplu blocat și unul care trece.
- **F5.5 Auditorul de ton (G4) și evaluatorul de lizibilitate și conversie (G8).** *Gata când:* un text în ton greșit este semnalat și un text cu două apeluri la acțiune este respins.
- **F5.6 Originalitate (G7) și garda juridică (G9).** *Gata când:* un text copiat dintr-o sursă este blocat și o reducere fără preț de referință este semnalată.
- **F5.7 Seturile de aur și bancul de evaluare (K4).** 30–100 de exemple per validator, plus setul de materiale intenționat greșite. *Gata când:* bancul rulează dintr-o atingere și arată scorurile.
- **F5.8 Calibrarea judecătorilor (G14).** Eșantion săptămânal și statistica de acord. *Gata când:* acordul cu etichetele tale este măsurat pentru fiecare judecător.
- **F5.9 Biroul de aprobări.** Ecranul din secțiunea 18.3, cu motive de respingere și editare pe loc. *Gata când:* aprobi, respingi și editezi de pe telefon, iar motivul se salvează.
- **F5.10 Carantină și contestații.** *Gata când:* un verdict contestat ajunge în setul de aur.

**Poarta F5:** cel puțin 95% din materialele intenționat greșite sunt blocate și cel mult 10% din cele bune sunt respinse pe nedrept.

### 23.9 F6 – Producția de text și publicarea asistată

- **F6.1 Strategul de conținut și calendarul.** Piloni, formate și calendar lunar, din strategia aprobată în F4.11. *Gata când:* un brand propriu are calendar pe 30 de zile, aprobat.
- **F6.2 Autorul de brief.** *Gata când:* fiecare intrare de calendar are brief cu fapte permise.
- **F6.3 Hook-uri și postări.** Variante, alegere, scriere, editare. *Gata când:* zece postări trec validarea, cel mult două cu reparație.
- **F6.4 Scripturi video.** Scripturi pe bătăi, cu durată estimată. *Gata când:* cinci scripturi trec validarea și se încadrează în durata-țintă.
- **F6.5 Adaptorul pe platformă.** *Gata când:* aceeași idee are variante corecte ca lungime pentru fiecare canal.
- **F6.6 Publicarea asistată.** Pachet complet pe telefon, partajare, lipirea linkului. *Gata când:* publici o postare reală din două atingeri și linkul ei apare în sistem.
- **F6.7 Capturarea feedbackului.** Motivele și editările devin exemple. *Gata când:* o respingere apare ca exemplu negativ în contextul următoarei sarcini similare.
- **F6.8 Proba de două săptămâni.** Platforma produce zilnic pentru cele două branduri proprii, la L1. *Gata când:* trec 14 zile fără incident critic și rata de aprobare din prima este măsurată.

**Poarta F6:** prima versiune utilizabilă intern (poarta de lansare 1 din secțiunea 25.4). Aici începi cele zece discuții de vânzare și recrutarea clienților-pilot, în paralel cu fazele F7–F10. Pilotul propriu-zis pornește la poarta de lansare 2.

### 23.10 F7 – Site, portal, facturare

- **F7.1 Site-ul complet.** Paginile din secțiunea 19.1, cu consimțământ pentru cookie-uri. *Gata când:* toate paginile sunt publice și rapide pe telefon.
- **F7.2 Formularul de audit.** Captare cu opt-in dublu, legată prin rețea de motorul de audit din BigBrain, printr-un adaptor. *Gata când:* un audit cerut produce un raport și un lead în sistem.
- **F7.3 Portalul: cont și onboarding.** *Gata când:* un client de test își face contul și parcurge interviul.
- **F7.4 Portalul: Creier, calendar, aprobări.** *Gata când:* clientul de test aprobă un lot de pe telefon.
- **F7.5 Portalul: materiale și inboxul de tendințe.** Încărcare de fișiere, cu verificare de tip. *Gata când:* o fotografie încărcată apare în biblioteca de active, cu sursă.
- **F7.6 Facturare.** Planuri, abonamente, webhook-uri, perioadă de grație. *Gata când:* în mediul de probă al procesatorului, un abonament se creează, se reînnoiește și se suspendă la neplată.
- **F7.7 Export și ștergere.** *Gata când:* datele clientului de test se exportă complet și se șterg la cerere.
- **F7.8 Raportul lunar, prima formă.** Livrabile și stare, încă fără metrici. *Gata când:* raportul se generează pentru un brand propriu.
- **F7.9 Oferta, pâlnia și paginile de captare (D2, E3).** Arhitectul de ofertă propune magnetul de lead-uri și traseul. Copywriterul de conversie scrie pagina de captare, reclamele text și studiul de caz. Pagina este găzduită de platformă. *Gata când:* pagina de audit a agenției este generată din platformă, trece G2, G3 și G9 și are un singur apel la acțiune.
- **F7.10 Cercetarea SEO și articolele (C6, E5, E7).** Grupuri de cuvinte-cheie pe intenție, brief SEO, articol în trei pași, lista on-page deterministă. *Gata când:* două articole pentru blogul agenției trec validarea și lista on-page, fiecare cu sursele citate.

**Poarta F7:** un client de test parcurge tot drumul, de la audit la plată și la prima aprobare.

### 23.11 F8 – Media

- **F8.1 Vocea și licența ei.** Motorul de voce, profilul de voce, decizia privind licența sau vocea proprie. *Gata când:* o frază în română este sintetizată și statutul licenței este scris în registrul de active.
- **F8.2 Normalizarea textului românesc.** Numere, date, sume, abrevieri, diacritice, dicționar de pronunție. *Gata când:* setul de 100 de fraze de probă este citit corect.
- **F8.3 Transcrierea inversă și timpii pe cuvânt.** *Gata când:* pentru o narațiune de probă, fiecare cuvânt are moment, iar o frază citită greșit este detectată.
- **F8.4 Furnizorul de imagini și biblioteca de active.** Materialele clientului, stock, generare, cu licența salvată. *Gata când:* niciun activ nu poate fi folosit fără licență înregistrată.
- **F8.5 Lista de decizii de montaj și Regizorul.** Schema și validarea ei. *Gata când:* un script produce o listă validă, cu durate care se potrivesc cu vocea.
- **F8.6 Montajul pentru formatele A și B.** *Gata când:* un video vertical complet iese dintr-o listă, fără intervenție.
- **F8.7 Subtitrări și sunet.** Cuvânt cu cuvânt, zone sigure, muzică atenuată sub voce. *Gata când:* subtitrările sunt sincronizate și nivelul sonor este în țintă.
- **F8.8 Controlul media (G6) și auditorul vizual (G5).** *Gata când:* colecția de clipuri defecte este respinsă integral.
- **F8.9 Testul de capacitate.** Zece video, pe toate culoarele grele deodată, cu producția de text în mers. *Gata când:* timpul per video și consumul de memorie sunt măsurate, iar bugetele sunt confirmate.
- **F8.10 Șabloane grafice și Compozitorul.** Propunerea de identitate vizuală, acolo unde lipsește; creativuri, carusele, coperți. *Gata când:* fiecare brand propriu are șase șabloane și textul apare cu diacritice corecte.
- **F8.11 Proveniență și dezvăluire AI (G11).** Pașaportul activului și eticheta per canal. *Gata când:* fiecare fișier final are pașaport și etichetă stabilită.
- **F8.12 Formatul E, om real.** Prompter în portal, tăierea pauzelor, subtitrări. *Gata când:* o filmare brută de un minut devine clip publicabil.

**Poarta F8:** zece video consecutive trec controlul media fără intervenție.

### 23.12 F9 – Publicarea prin API

- **F9.1 Interfața comună de conector.** Autorizare, publicare, stare, limite, erori. *Gata când:* conectorul fals trece toate testele de contract.
- **F9.2 Facebook, pagini.** *Gata când:* o postare de test apare pe pagina agenției, o singură dată, iar cererea de App Review pleacă împreună cu înregistrarea fluxului.
- **F9.3 Instagram.** Servirea fișierelor prin linkuri semnate și citirea limitei din endpoint. *Gata când:* o imagine și un clip apar pe contul agenției, iar permisiunea de publicare este cerută în App Review.
- **F9.4 YouTube.** Încărcare, câmpul de conținut modificat sau sintetic, citirea costului în unități. *Gata când:* un clip este public după audit sau privat înainte, cu starea afișată corect, iar cererea de audit este trimisă.
- **F9.5 LinkedIn.** Profil la început, pagină după aprobare. *Gata când:* o postare apare pe profilul tău.
- **F9.6 TikTok.** Trimitere ca ciornă sau postare directă după audit, cu previzualizare și consimțământ. *Gata când:* fluxul respectă regulile lor, cererea de audit este trimisă cu înregistrarea fluxului și starea ei se vede în panou.
- **F9.7 Planificarea, alegerea canalelor și zilele blocate (D4).** Sloturi pe client și canal, limite de frecvență, zile blocate. *Gata când:* o postare programată pleacă la minut, iar pauza de criză oprește tot.
- **F9.8 Gardianul sănătății conturilor.** *Gata când:* un token aproape expirat generează o cerere de reautorizare, iar o serie de erori pune canalul pe pauză.
- **F9.9 Site și blog (H6).** Publicarea articolelor și a paginilor în CMS-ul clientului sau în paginile găzduite de platformă. *Gata când:* un articol aprobat din F7.10 apare pe blogul agenției, cu verificările on-page trecute.
- **F9.10 Ecranul „Publicare”.** *Gata când:* vezi starea fiecărei aprobări API și poți trece un canal pe asistat.

**Poarta F9:** pe fiecare canal aprobat, o postare publică pleacă prin API, o singură dată. Canalele neaprobate rămân pe asistat.

### 23.13 F10 – Analiză și cercetare continuă

- **F10.1 Colectorul de metrici.** Citiri la intervalele din secțiunea 7.2, pentru fiecare canal conectat. *Gata când:* metricile unei postări reale apar la fiecare interval.
- **F10.2 Curba de retenție YouTube.** *Gata când:* curba unui clip propriu se vede în panou.
- **F10.3 Legarea de etichete.** Fiecare rezultat este legat de hook, format, slot și unghi. *Gata când:* poți sorta postările după tiparul de hook.
- **F10.4 Tablourile de bord și scorul de sănătate al clientului (L4).** Indicatorii de business și semnalele de risc din secțiunea 4.10, pe reguli. *Gata când:* indicatorii din secțiunea 4.13 se văd pentru fiecare client, iar un client de test cu aprobări întârziate apare semnalat.
- **F10.5 Raportul lunar complet.** *Gata când:* raportul unui brand propriu conține cifre reale, verificate de G2.
- **F10.6 Analiza de trafic proprie.** Evenimente pe site și pe paginile de captare, cu consimțământ. *Gata când:* vezi câți vizitatori cer audit.
- **F10.7 Cercetătorul de tendințe (C2).** Sursele oficiale din secțiunea 12.1 și inboxul de tendințe, transformate în fișe de tendință cu dovezi, pe cadența din secțiunea 12.7. *Gata când:* în fiecare dimineață apar fișe pentru nișa unui brand propriu, iar un link lipit în inbox devine fișă și propunere de calendar.
- **F10.8 Analistul de reclame ale concurenței (C3).** Citirea bibliotecilor oficiale de reclame și harta unghiurilor. *Gata când:* pentru concurenții unui brand propriu există harta unghiurilor, cu reclamele care rulează de cel mai mult timp, iar un text prea apropiat de o reclamă observată este blocat de G7.

**Poarta F10:** un raport lunar complet, din date reale, fără cifre introduse manual.

### 23.14 F11 – Învățare, prima treaptă

- **F11.1 Reflectorul.** Compară rezultatele, verdictele și editările și propune lecții. *Gata când:* după un lot închis apar propuneri de lecții cu dovezi.
- **F11.2 Curatorul și playbook-ul.** Actualizări mici, contoare, limite, retragere automată. *Gata când:* o lecție aprobată apare în contextul sarcinii următoare și contorul ei se actualizează.
- **F11.3 Alegerea adaptivă.** Variante, recompense întârziate, explorare, mediile nișei. *Gata când:* alegerea hook-urilor și a sloturilor se schimbă vizibil pe date simulate, apoi pe date reale.
- **F11.4 Registrul de experimente.** Ipoteză, variante, indicator, regulă de oprire. *Gata când:* un experiment simplu rulează cap-coadă.
- **F11.5 Constituția.** Garduri tehnice: drepturi de scriere, indicatori de gardă, o schimbare pe săptămână, înghețare. *Gata când:* o încercare de a modifica un pachet de reguli din fluxul de învățare este refuzată.
- **F11.6 Ecranul „Învățare”.** *Gata când:* aprobi o lecție și anulezi o promovare de pe telefon.

**Poarta F11:** o lecție promovată și una retrasă, ambele cu urmă completă.

### 23.15 F12 – CRM, email, inbox

- **F12.1 CRM-ul minimal.** Firme, contacte, lead-uri, etape, consimțământ, unirea duplicatelor, sarcini de urmărire. *Gata când:* un lead din formular apare cu sursă și temei, iar același lead trimis de două ori nu se dublează.
- **F12.2 Email către abonați.** Furnizor, domeniu autentificat, dezabonare, listă de suprimare, matricea pe țări. *Gata când:* o adresă dezabonată nu mai poate primi nimic, din nicio campanie.
- **F12.3 Secvența de după audit.** *Gata când:* un abonat de test primește secvența și dezabonarea funcționează.
- **F12.4 Calificare și scor.** *Gata când:* lead-urile de test sunt împărțite corect în cele trei grupe.
- **F12.5 Programări.** *Gata când:* rezervi un apel de pe telefon și primești invitația.
- **F12.6 Generatorul de oferte.** *Gata când:* o ofertă pornește din audit și din pachete și ajunge la tine spre aprobare.
- **F12.7 Inboxul social.** Citirea mesajelor și a comentariilor pe canalele aprobate, cu clasificare. *Gata când:* mesajele de test sunt clasificate corect.
- **F12.8 Răspunsuri și escaladare.** Regulile din secțiunea 17.8, ferestrele de mesagerie, dezvăluirea AI. *Gata când:* o critică de test ajunge la om, iar un mesaj în afara ferestrei nu se trimite.
- **F12.9 Lista de conturi-țintă.** *Gata când:* o listă de firme dintr-o nișă are mini-audit și nu conține date personale.
- **F12.10 Asistentul de suport din portal (L5).** Răspunde la întrebări despre cont și livrabile, din datele clientului. Escaladează restul. *Gata când:* o întrebare despre starea unui livrabil primește răspuns corect, iar o întrebare despre facturare sau o reclamație ajunge la tine.

**Poarta F12:** un lead real parcurge drumul de la audit la apel programat.

### 23.16 F13 – Reclame, Strateg, Consiliu

- **F13.1 Citirea rezultatelor Meta.** *Gata când:* cifrele contului agenției apar în panou și coincid cu managerul de reclame.
- **F13.2 Citirea rezultatelor Google Ads.** *Gata când:* la fel, pentru Google.
- **F13.3 Planificatorul media.** *Gata când:* un plan de probă are structură, plafoane și criterii de oprire și trece verificarea.
- **F13.4 Constructorul de campanii, propunerile de schimbare și executorul (I2).** Campanii create în pauză, din planul aprobat. Obiecte tipizate, starea de dinainte, anulare. *Gata când:* o campanie de probă apare în pauză pe contul agenției, iar o schimbare aplicată se poate anula dintr-o atingere.
- **F13.5 Gardianul de buget și oprirea de urgență.** *Gata când:* o propunere peste plafon este refuzată, iar o anomalie simulată pune totul pe pauză și te anunță.
- **F13.6 Strategul și înregistrările de decizie.** Revizuire săptămânală, patru ieșiri, pivot pe 20%. *Gata când:* pe date de probă cu rezultate slabe, Strategul propune oprirea și trei alternative.
- **F13.7 Consiliul.** Dosarul de Consiliu, importul deciziei, bugetul de apeluri și modul de conectare ales din secțiunea 7.6. *Gata când:* o decizie luată în Claude apare în platformă și schimbă starea unei campanii.
- **F13.8 Verificarea reclamelor înainte de lansare.** *Gata când:* reclamele de probă cu probleme de politică sunt blocate.
- **F13.9 Testarea creativurilor.** *Gata când:* un test cu trei variante și buget mic declară un câștigător după regulile din secțiunea 16.6.
- **F13.10 Campania reală de probă.** Pe contul agenției, cu buget mic, către pagina de audit. *Gata când:* trec două săptămâni fără depășire de plafon, cu raport dublu: platformă și site.

**Poarta F13:** oprirea de urgență este testată pe o campanie reală și nicio schimbare nu a trecut de plafoane.

### 23.17 F14 – Învățare, a doua treaptă

- **F14.1 Optimizatorul de prompturi.** Rulare nocturnă, raport, comparație cu campionul. *Gata când:* o rulare produce un candidat cu scor pe setul de test.
- **F14.2 Umbră, canar, promovare, revenire.** *Gata când:* un candidat trece prin toate etapele și revenirea funcționează.
- **F14.3 Predictorul de performanță.** Doar dacă pragul de date este atins. *Gata când:* pe date trecute, predicția bate alegerea la întâmplare cu o marjă măsurată.
- **F14.4 Teste A/B formale.** *Gata când:* un test are ipoteza declarată dinainte și verdictul calculat automat.
- **F14.5 Scorul de lead și riscul de plecare, ca modele.** Doar la pragul de date. *Gata când:* bat regulile simple pe date trecute.
- **F14.6 Consolidarea nocturnă a memoriei.** *Gata când:* duplicatele dispar și intrările vechi ies din rotație.

**Poarta F14:** un prompt optimizat a bătut campionul, a fost promovat și a fost măsurat față de grupul de control.

### 23.18 F15 – Întărire și lansare

- **F15.1 Teste de avarie.** Scenariile din secțiunea 25. *Gata când:* toate trec pe staging.
- **F15.2 Revizuire de securitate.** Al doilea model revizuiește codul sensibil. Se rulează testele de izolare și colecția de atacuri. *Gata când:* nu rămâne nicio problemă critică deschisă.
- **F15.3 Exercițiu de restaurare completă.** *Gata când:* platforma este refăcută din backup pe un mediu curat, în ținta de timp.
- **F15.4 Juridic finalizat.** *Gata când:* contractul, acordul de prelucrare și paginile legale sunt cele revizuite de avocat.
- **F15.5 Pilot cu trei clienți.** L1, preț de pilot, feedback săptămânal. *Gata când:* trec patru săptămâni fără incident critic, cu aprobare din prima de peste 85%.
- **F15.6 Lansarea comercială.** Prețuri publice, studii de caz, pâlnia de audit pornită. *Gata când:* lista din secțiunea 25.5 este bifată integral.

### 23.19 F16 – Extensii, după lansare

- Formatul C, grafică animată.
- Canale noi: Pinterest, Google Business Profile, Threads.
- Localizare într-o a doua limbă.
- Voce proprie antrenată.
- Generator video extern, când există buget.
- Reclame pe TikTok.
- White-label pentru freelanceri și agenții mici.
- Al doilea server.

### 23.20 Ce poate merge în paralel

- Pașii F0.1–F0.4 se încheie înainte de faza F1. Pașii F0.5–F0.8 merg în paralel cu fazele F1–F3. Aprobările externe curg în fundal.
- După faza F6, fazele F7, F8 și F10 pot alterna, fiindcă ating zone diferite.
- Faza F9 se face canal cu canal. F9.1 și primul conector pot începe imediat după F6, ca prima cerere de review să plece devreme.
- F11 are nevoie de F10. F13 are nevoie de F9, de F10 și de aprobările de reclame. F14 are nevoie de date și poate rămâne după lansare.
- Faza F15 nu așteaptă fazele F11–F14. Ce trebuie încheiat înainte de pilot depinde de pachetul vândut (secțiunea 23.21).
- Regulă: o singură ramură deschisă pe un modul. Două sesiuni nu modifică aceleași fișiere.

### 23.21 Drumul critic până la pilot, pe pachet

Toate pachetele conțin video și raport lunar. De aceea pilotul nu poate porni doar cu faza F7 încheiată.

| Pachetul vândut în pilot | Ce trebuie încheiat înainte de primul client | Ce poate veni după |
| --- | --- | --- |
| Start | Fazele F0–F8; pașii F10.1 și F10.3–F10.5; pașii F15.1–F15.4 | F9 (până atunci se lucrează asistat), F10.7–F10.8, F11–F14 |
| Creștere | Tot ce cere Start, plus F9.9 și F12.1–F12.3 | F11, restul fazei F12, F13, F14 |
| Pro | Tot ce cere Creștere, plus F9 pe canalele cu reclame, F10.8, F11.4 și faza F13 integral | F14 |

- Recomandare: pilotul pornește pe Start sau pe Creștere. Pachetul Pro se vinde după ce poarta F13 a trecut pe contul agenției.
- Până la aprobarea permisiunilor de mesaje, „răspunsurile asistate la comentarii” din pachetul Creștere înseamnă răspunsuri propuse de platformă și trimise de om.
- Până la aprobările API, cifrele din raportul unui client-pilot vin din exporturile platformelor sau din accesul de test dat aplicației, nu din citirea automată \[I\]. Timpul acesta se adaugă la minutele de om per client.
- Dacă planul întârzie, fazele F11–F14 se mută după lansare. Fazele F0–F8 și F10 nu se scurtează.
