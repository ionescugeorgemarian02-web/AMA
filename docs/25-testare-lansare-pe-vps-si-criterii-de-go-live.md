## 25. Testare, lansare pe VPS și criterii de go-live

Platforma trece prin trei medii (CI, staging, producție) și prin trei porți de lansare (intern, pilot, comercial). Nimic nu ajunge la un client real fără să fi fost stricat intenționat pe staging.

### 25.1 Mediile

| Mediu | Unde | Date | Modele | Conturi externe |
| --- | --- | --- | --- | --- |
| CI | GitHub | Sintetice | Furnizor fals | Niciunul |
| Staging | VPS, subdomeniu protejat | Sintetice și brandurile proprii | Reale, cu buget mic | Conturi de test și ale agenției |
| Producție | VPS | Reale | Reale | Ale clienților |

- Staging și producția au baze de date și secrete separate.
- Staging este pornit permanent și primește singur fiecare versiune aprobată.
- Conturile clienților nu se conectează niciodată la staging.

### 25.2 Matricea de teste funcționale

| Zonă | Test | Criteriu |
| --- | --- | --- |
| Izolare | Un utilizator al clientului A cere date ale clientului B, pe toate căile | Refuz, cu înregistrare în audit |
| Mașina de stări | Fiecare tranziție permisă și nepermisă | Cele nepermise sunt refuzate |
| Validare | Setul de materiale intenționat greșite | Cel puțin 95% blocate |
| Validare | Setul de materiale bune | Cel mult 10% respinse |
| Fapte | Texte cu prețuri și date greșite | Toate blocate |
| Media | Colecția de clipuri defecte | Toate respinse |
| Voce | 100 de fraze cu numere, date, sume și abrevieri | Citite corect |
| Publicare | Aceeași postare trimisă de două ori | Publicată o singură dată |
| Aprobare | O aprobare care întârzie | Expiră, nu se publică |
| Autonomie | Același livrabil la L1 și la L2 | Cere aprobare, respectiv trece singur |
| Reclame | O propunere peste plafon | Refuzată |
| Email | Trimitere către o adresă suprimată | Blocată |
| Facturare | Plată eșuată în mediul de probă | Perioadă de grație, apoi suspendare |
| Export și ștergere | Cerere de export și de ștergere | Complete și verificabile |

### 25.3 Teste de avarie

| Scenariu | Ce trebuie să se întâmple |
| --- | --- |
| Furnizorul principal de modele nu răspunde | Rutare pe rezervă; sarcinile strategice se amână; alertă minoră |
| Toate cotele găzduite sunt epuizate | P0 trece pe modelul local, unde profilul permite; restul se amână; alertă |
| Baza de date repornește în mijlocul unui workflow | Workflow-ul reia de la ultimul pas, fără efecte duble |
| Workerul este oprit forțat în timpul unei randări | Jobul se reia și fișierele parțiale se curăță |
| Discul ajunge la 85% | Curățare, oprirea randărilor noi, alertă |
| Memoria se apropie de limită | Joburile grele se amână; serviciile permanente nu sunt afectate |
| Toate culoarele grele sunt ocupate și sosește un job P0 | Jobul P0 trece în fața cozii și pornește la primul culoar eliberat |
| Un token de platformă expiră | Canalul intră pe pauză, apare cererea de reautorizare, nimic nu se pierde |
| Un webhook sosește de două ori | Este procesat o singură dată |
| Platforma răspunde cu eroare după ce a publicat | Verificare la platformă, fără publicare dublă |
| Un document colectat conține instrucțiuni ostile | Comportament neschimbat; cazul este înregistrat de G13 |
| Cheltuială anormală simulată la reclame | Pauză totală în mai puțin de un minut și alertă critică |
| VPS-ul repornește complet | Toate serviciile revin singure și cozile reiau |
| Restaurare pe un mediu curat | Platformă funcțională în ținta de timp |

### 25.4 Cele trei porți de lansare

| Poartă | Condiții | Ce permite |
| --- | --- | --- |
| 1 Intern | Fazele F1–F6 încheiate și primul val de cereri din F0 trimis; 14 zile de producție pentru brandurile proprii fără incident critic; backup testat | Folosire pentru CariereAI, BigBrain și agenție |
| 2 Pilot | Drumul critic al pachetului vândut este încheiat (secțiunea 23.21); contract și acord de prelucrare revizuite; cel puțin un canal cu publicare prin API sau modul asistat rodat; testele de avarie trecute | Trei clienți, la L1, cu preț de pilot |
| 3 Comercial | Patru săptămâni de pilot fără incident critic; aprobare din prima peste 85%; raport lunar real livrat; facturare în producție; exercițiu de restaurare trecut | Vânzare publică |

### 25.5 Lista de go-live comercial

Tehnic:

- [ ] Toate testele din 25.2 și 25.3 trec pe staging
- [ ] Backupul zilnic și restaurarea de test săptămânală sunt verzi de cel puțin 4 săptămâni
- [ ] Al doilea factor este activ pe toate conturile de administrare
- [ ] Butoanele de oprire sunt testate din panou și din Telegram
- [ ] Alertele critice ajung pe telefon în mai puțin de un minut
- [ ] Limitele de memorie și de disc au fost respectate în ultimele 14 zile
- [ ] Niciun secret în repo; scanarea este curată

Calitate:

- [ ] Acordul dintre judecător și om este de cel puțin 85% pe fiecare validator
- [ ] Rata de aprobare din prima este peste 85% în pilot
- [ ] Zero incidente critice publicate în pilot
- [ ] Testul comparativ al modelelor a fost rulat în ultima lună

Juridic și comercial:

- [ ] Contractul, acordul de prelucrare, termenii și politicile sunt revizuite de avocat
- [ ] Pagina „Transparență AI” și lista de nișe refuzate sunt publicate
- [ ] Matricea de conformitate pe țări este completată pentru piețele active
- [ ] Facturarea și e-Factura sunt confirmate cu contabilul
- [ ] Prețurile sunt validate în discuții de vânzare
- [ ] Două studii de caz sunt publicate

Operare:

- [ ] Procedurile pentru incidente sunt scrise și citite
- [ ] Rutina zilnică, săptămânală și lunară este în calendarul tău
- [ ] Starea fiecărei aprobări API este cunoscută și comunicată cinstit clienților

### 25.6 Protocolul de pilot

- Trei clienți din nișa aleasă, la L1.
- Onboarding însoțit de tine, ca să vezi unde se împiedică.
- Întâlnire săptămânală de 20 de minute cu fiecare client.
- Jurnal de fricțiuni: fiecare problemă devine pas de reparație sau regulă.
- Măsori minutele de om per client, rata de aprobare din prima, timpul până la primul lot și satisfacția clientului.
- La final decizi prețul, pachetele și ce intră în lansarea comercială.

### 25.7 După lansare

- În prima lună nu se adaugă nicio funcție nouă. Doar stabilitate și reparații.
- Fiecare client nou intră la L1.
- Riscurile și cotele se revizuiesc lunar.
- O dată pe trimestru: exercițiu de restaurare și revizuirea politicilor de platformă.
