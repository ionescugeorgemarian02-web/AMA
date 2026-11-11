## 21. Securitate, conformitate și juridic

Trei riscuri pot închide afacerea: scurgerea datelor unui client, o acțiune automată greșită pe bani sau pe conturi și o încălcare de lege sau de termeni. Fiecare are controale tehnice, nu doar reguli scrise.

### 21.1 Izolarea clienților

- Securitate la nivel de rând în Postgres, activă pe toate tabelele cu date de client. Aplicația setează clientul curent la fiecare cerere, iar baza refuză restul.
- Teste automate care încearcă să citească datele altui client și trebuie să eșueze.
- Fișierele media sunt separate pe client. Linkurile publice sunt semnate și expiră.
- Căutarea în vectori filtrează întotdeauna pe client.
- Jurnalele nu amestecă date între clienți.

### 21.2 Secrete și tokenuri

- Cheile de modele și secretele aplicației stau în fișiere de mediu cu drepturi restrânse, în afara repo-ului.
- Tokenurile conturilor clienților sunt criptate în bază, cu o cheie principală păstrată separat.
- Fiecare conector cere doar drepturile de care are nevoie.
- Reamintire de rotație la 90 de zile pentru chei. Reautorizare înainte de expirarea tokenurilor.
- Scanare de secrete la fiecare commit. Un secret ajuns în repo se consideră compromis și se schimbă.
- Niciun secret nu intră într-un prompt.

### 21.3 Autentificare și acces

- **Panoul de administrare:** parolă puternică și al doilea factor (aplicație de coduri sau cheie de acces).
- **Portalul clientului:** link pe email sau parolă, cu al doilea factor opțional.
- **Sesiuni:** expirare, cookie-uri sigure, protecție la cereri falsificate, limită de încercări la autentificare.
- **Roluri:** drepturi minime, ca în secțiunea 18.5.
- **Audit:** fiecare acțiune sensibilă intră în jurnal.

### 21.4 Suprafața de atac

- Expuse sunt doar site-ul, aplicația și fișierele media semnate, prin proxy, pe HTTPS.
- Antete de securitate și politică restrictivă de conținut.
- Toate intrările se validează. Fișierele încărcate sunt verificate ca tip și dimensiune și nu se execută niciodată.
- Webhook-urile sunt acceptate doar cu semnătură validă și cu protecție la reluare.
- Limite de rată pe formulare și pe API.

### 21.5 Lanțul de aprovizionare software

- Dependențe puține, fixate la versiuni exacte, cu hash-uri verificate la instalare.
- Imagini Docker fixate pe amprentă.
- Actualizări lunare, printr-un pas dedicat, cu testele rulate.
- Scanare de vulnerabilități în CI.
- Incidentul LiteLLM din martie 2026 arată de ce: o singură dependență compromisă, în punctul prin care trec toate cheile, expune tot.

### 21.6 Riscuri specifice agenților

| Risc | Control |
| --- | --- |
| Text extern care dă instrucțiuni unui model | Conținutul extern este marcat ca dată; G13; agenții de cercetare nu au unelte cu efecte |
| Model care inventează o acțiune | Modelele nu au acces la API-urile externe; propun obiecte tipizate, validate de reguli |
| Scurgere de date personale către furnizori | G12 maschează înainte de apel; furnizorii care antrenează pe date sunt excluși pentru date confidențiale |
| Buclă care consumă cotele | Bugete per livrabil, limite de predări, întrerupător global |
| Optimizator care învață să încalce regulile | Constituția din secțiunea 11.6 |
| Ieșire care conține cod sau linkuri periculoase | Ieșirile se tratează ca text; linkurile se verifică față de o listă permisă |
| Escaladare de drepturi între agenți | Fiecare componentă are o listă fixă de unelte și de date |

### 21.7 Protecția datelor

- **Roluri.** Pentru datele publicului unui client (mesaje, lead-uri, abonați), agenția este împuternicit, iar clientul este operator. Pentru lead-urile proprii, agenția este operator.
- **Documente.** Acord de prelucrare cu fiecare client, registru al activităților de prelucrare, listă de subîmputerniciți (furnizori de modele, email, găzduire), politică de confidențialitate.
- **Minimizare.** Se colectează doar ce servește scopului. Datele personale se maschează înainte de modele.
- **Drepturi.** Funcții de export și de ștergere pe persoană și pe client. Termen de răspuns: 30 de zile.
- **Incidente.** Procedură scrisă. Notificarea autorității în 72 de ore, când legea o cere.
- **Furnizori gratuiți.** Nivelurile gratuite oferă rar garanții contractuale de prelucrare. Datele personale nu ajung la ei. Pentru date confidențiale se folosește modelul local sau un furnizor cu termeni potriviți.
- **Decizii automate.** Scorarea lead-urilor are întotdeauna o cale de revizuire umană.

### 21.8 Comunicări comerciale și cookie-uri

- Email comercial doar cu consimțământ, inclusiv către firme, în România (secțiunea 17.4).
- Dovada consimțământului se păstrează: când, unde și ce text a văzut persoana.
- Dezabonarea funcționează dintr-un clic și se aplică imediat.
- Cookie-urile neesențiale și urmărirea pornesc doar după acord.

### 21.9 Transparența AI

- **Conversații.** Asistenții din inbox, din portal și de pe site spun de la început că sunt asistenți AI.
- **Conținut generat.** Imaginile și sunetul generate care pot părea reale se etichetează pe platformă. Proveniența se păstrează în fișier și în pașaportul activului.
- **Text.** Textele publicate au revizuire umană sau responsabilitate editorială asumată de client prin aprobare. Aprobarea se înregistrează.
- **Marcare lizibilă de mașini.** Dacă platforma este considerată furnizor de sistem generativ, ieșirile trebuie marcate tehnic. Mecanismul se construiește din prima versiune. Încadrarea exactă o stabilește avocatul, în F0.7.
- **Pagină publică.** „Transparență AI” explică toate acestea pe site.

### 21.10 Regulile platformelor

- Registru de conformitate: pentru fiecare platformă, regulile-cheie, controlul nostru și data ultimei verificări.
- Verificare trimestrială a schimbărilor de politici.
- Conturile clienților nu se folosesc niciodată pentru teste.
- O restricție primită pe un cont este incident major, cu analiză și cu regulă nouă în pachet.

### 21.11 Practici comerciale și drepturi de autor

- Fără recenzii false, fără urgență falsă, fără reclamă mascată. G9 verifică.
- Reducerile au preț de referință, conform regulilor de afișare a prețurilor.
- Conținutul sponsorizat este marcat.
- Fiecare activ extern are licență înregistrată. Materialele concurenței nu se refolosesc.
- Contractul spune cine deține livrabilele și menționează că protecția prin drept de autor a conținutului generat de AI este incertă.

### 21.12 Nișe și cereri refuzate

- Politică, jocuri de noroc, conținut pentru adulți, promisiuni medicale, scheme financiare.
- Orice cerere de a ascunde originea AI, de a ocoli regulile unei platforme sau de a contacta persoane fără temei.
- Lista este publică pe site și scrisă în contract.

### 21.13 Ce face avocatul, o singură dată

- [ ] Revizuiește contractul, acordul de prelucrare și termenii site-ului
- [ ] Stabilește rolul platformei sub AI Act, art. 50
- [ ] Confirmă regulile de email comercial și completează matricea pe țări
- [ ] Verifică licența vocii și modelul de acord pentru vocea proprie
- [ ] Confirmă termenele de păstrare a datelor
- [ ] Verifică regulile de publicitate pentru nișa aleasă
