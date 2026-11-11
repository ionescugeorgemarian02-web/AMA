## 15. Publicare și distribuție

Publicarea automată depinde de aprobări pe care nu le controlăm. De aceea fiecare canal are trei moduri (asistat, automat cu aprobare, automat), iar platforma pornește în modul asistat din prima zi.

### 15.1 Canale și porți

| Canal | Ce cere publicarea automată | Limite cunoscute | Mod de pornire |
| --- | --- | --- | --- |
| Facebook, pagini | Aplicație Meta, App Review și Business Verification pentru paginile clienților | Limitele de rată ale API-ului | Asistat, apoi automat |
| Instagram, cont profesional | La fel, plus permisiunea de publicare; fișier la URL public | 100 de postări API în 24 h, de verificat în endpoint; containerele expiră în 24 h | Asistat, apoi automat |
| YouTube, Shorts și lung | Proiect Google Cloud, verificare OAuth și audit de conformitate | 10.000 de unități pe zi; fără audit, video rămâne privat | Asistat, apoi automat |
| LinkedIn, profil | Aplicație self-serve | Limită zilnică largă | Automat de la început, pe profilul tău |
| LinkedIn, pagină de companie | Community Management API, cu review | – | Asistat până la aprobare |
| TikTok | Aplicație și audit; previzualizare și consimțământ per postare | Neauditat: doar privat, 5 utilizatori pe zi | Asistat sau „trimite ca ciornă în aplicație” |
| Site și blog | Acces la CMS sau pagini găzduite de platformă | – | Automat |
| Email | Furnizor de email și domeniu autentificat | Limitele nivelului gratuit | Automat, către abonați |
| Extensii: Pinterest, Google Business Profile, Threads, Telegram, Bluesky | Fiecare cu regulile lui; unele cer aprobare | De verificat la construcție | După primele cinci |

X nu este în planul inițial. Condițiile API-ului se verifică dacă un client îl cere.

### 15.2 Cele trei moduri

- **Asistat.** Platforma pregătește pachetul complet: fișier, text, hashtag-uri, copertă, ora recomandată. Îl primești pe telefon și postezi din două atingeri, prin meniul de partajare. Apoi lipești linkul postării, ca măsurarea să pornească.
- **Automat cu aprobare.** După aprobarea din portal, executorul publică la ora programată. Aprobarea este consimțământul pentru acea postare.
- **Automat.** Doar de la L2 în sus și doar pe canalele unde platforma o permite.

### 15.3 Ce se cere și când

Aprobările durează săptămâni și vin în două valuri. Primul val nu are nevoie de cod și pleacă în pasul F0.6. Al doilea cere o înregistrare video a fluxului real. El pleacă abia când conectorul funcționează în modul de test, pe conturile agenției.

Primul val, în F0.6, fără cod:

- [ ] Verificarea firmei în Meta Business
- [ ] Aplicație Meta creată, în modul de dezvoltare, cu pagina și contul de Instagram ale agenției
- [ ] Proiect Google Cloud și ecran de consimțământ OAuth configurat, în modul de test
- [ ] Acces Google Ads API la nivelul Explorer
- [ ] Aplicație TikTok creată, cu Content Posting API în modul de test
- [ ] Aplicație LinkedIn și cererea pentru Community Management API
- [ ] Confirmarea identității pentru Meta Ad Library API
- [ ] Cererea de acces la Google Trends API

Al doilea val, la conectorul fiecărui canal, cu fluxul filmat:

- [ ] Meta App Review pentru pagini și Instagram, după F9.2 și F9.3
- [ ] Meta App Review pentru mesaje și comentarii, după F12.7
- [ ] Meta App Review pentru administrarea reclamelor, după F13.1
- [ ] Verificarea OAuth și auditul de conformitate YouTube, după F9.4
- [ ] Auditul TikTok, după F9.6

Toate recenziile cer aceleași lucruri: site public cu politică de confidențialitate, termeni și instrucțiuni de ștergere a datelor; descrierea clară a cazului de utilizare; înregistrare video a fluxului; firmă verificată. De aceea site-ul minim este pasul F0.5. Dacă o platformă cere demonstrația și pentru o cerere din primul val, cererea se mută în al doilea \[I\].

Până la aprobare, aplicațiile în modul de test lucrează doar pe conturile agenției. Pe conturile clienților se lucrează asistat.

O cerere poate fi respinsă. Atunci canalul rămâne în modul asistat și cererea se reface cu observațiile primite.

### 15.4 Pachetul de publicare

Fiecare canal primește un pachet propriu: fișierul în formatul potrivit, textul adaptat, hashtag-urile, coperta, eticheta AI, marcajul de conținut comercial, ora și cheia de idempotență.

### 15.5 Planificarea

- **Calendar propriu.** Unele platforme nu au programare prin API. Platforma ține coada și publică la minut.
- **Ora.** Se alege din sloturile care au mers pentru acel client, cu o parte de explorare.
- **Frecvență.** Limite pe canal, ca postările să nu se sufoce între ele.
- **Zile blocate.** Sărbători, evenimente sensibile, cereri ale clientului.
- **Pauză de criză.** Un buton oprește tot ce este programat, pe un client sau global.

### 15.6 Dezvăluirea AI și conținutul comercial

- G11 decide eticheta pe baza pașaportului activului: ce este generat și cât de realist este.
- Eticheta se setează prin API acolo unde există câmp. Altfel apare în pachetul asistat, ca pas obligatoriu.
- Metadatele de proveniență din fișier se păstrează.
- Conținutul plătit sau în parteneriat primește marcajul cerut de platformă.
- Narațiunea sintetică și grafica evident ilustrativă se tratează după regulile fiecărei platforme, păstrate în pachetul de reguli.

### 15.7 Gardianul limitelor și al sănătății conturilor

- Citește limitele din API și din antetele răspunsurilor. Nu ghicește.
- Urmărește erorile de publicare, tokenurile care expiră, avertismentele de politică și scăderile bruște de reach față de media contului.
- Reacții: încetinește, pune canalul pe pauză, cere reautorizare, te anunță.
- Nu folosește proxy-uri, conturi multiple sau întârzieri menite să ascundă automatizarea.

### 15.8 După publicare

- Executorul salvează identificatorul și linkul postării.
- K1 programează citirile de metrici.
- H4 începe să urmărească comentariile.
- O postare ștearsă sau restricționată de platformă devine incident, cu analiză.
