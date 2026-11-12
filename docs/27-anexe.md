## 27. Anexe

Anexele conțin tot ce restul documentului numește „din anexă”: convențiile de notare și glosarul, 16 șabloane, fișa fiecăruia dintre cei 146 de pași, tabelul care leagă fiecare componentă de pasul în care se construiește, sursele și lista schimbărilor din această versiune.

### 27.1 Convenții de notare și glosar

| Notație | Ce înseamnă | Definită în |
| --- | --- | --- |
| A1 … L5 | Componentă din catalog: litera departamentului și numărul ei | Secțiunea 5 |
| F0 … F16 | Fază de construcție | Secțiunea 23.2 |
| F3.6 | Pas de construcție: faza și numărul pasului | Secțiunea 23 |
| L0 … L4 | Nivel de autonomie | Secțiunea 7.4 |
| T1 … T4 | Nivel de model | Secțiunea 5.1 |
| V0 … V5 | Treaptă de validare | Secțiunea 9.1 |
| N0 … N8 | Treaptă de învățare | Secțiunea 11.2 |
| P0 … P3 | Prioritate în cozi | Secțiunea 7.5 |
| D, L, A, M, H | Tipul unei componente | Secțiunea 5.1 |
| ADR-01 … ADR-16 | Decizie de arhitectură | Secțiunea 6.7 |
| RP, RT, RC, RJ, RB, RX | Risc, pe grupe | Secțiunea 26 |
| PD1 … PD8 | Punct de decizie | Secțiunea 26.9 |
| Ș1 … Ș16 | Șablon | Secțiunea 27.2 |
| \[V\], \[S\], \[I\] | Verificat din sursă oficială, sursă secundară, ipoteză de validat | Secțiunea 1 |

Două suprapuneri de evitat:

- **F1–F8** înseamnă și componentele departamentului F (Design și media), și primele faze de construcție. Un cod cu punct (F8.1) este întotdeauna un pas. O fază se scrie „faza F8” ori de câte ori contextul nu este evident.
- **L1–L4** înseamnă și componente ale departamentului L (Clienți și finanțe), și niveluri de autonomie. Un nivel se scrie „nivelul L2” ori de câte ori contextul nu este evident.
- În cod și în baza de date, componentele, fazele, nivelurile de autonomie și tipurile au nume întregi, nu coduri scurte. Regula intră în fișierul de reguli pentru agenți.

| Termen | Înțeles în acest document |
| --- | --- |
| Livrabil | O unitate de muncă pentru client: o postare, un articol, un video, o reclamă |
| Creierul de brand | Memoria unui client, în zece compartimente (secțiunea 10.1) |
| Registru de fapte | Lista faptelor aprobate de client. Singura sursă de cifre, prețuri și promisiuni |
| Pachet de context | Ce primește un agent pentru o sarcină: fapte, ton, exemple, lecții, constrângeri |
| Set de aur | Exemple etichetate de om, folosite ca test pentru un prompt sau un validator |
| Campion și candidat | Versiunea de prompt aflată în producție și cea care încearcă să o înlocuiască |
| Culoar greu | Un loc în semaforul pentru joburi care consumă procesor: randare, voce, transcriere, OCR, generare locală |
| Preț-umbră | Cât ar fi costat un apel gratuit la un furnizor plătit |
| Efect extern | Orice acțiune care iese din platformă: publicare, email, schimbare de reclamă, plată |
| Cheie de idempotență | Identificatorul care face ca un efect extern să nu se execute de două ori |
| Mod asistat | Platforma pregătește pachetul, iar un om apasă „postează” |
| Pașaportul activului | Fișa unui fișier media: sursă, licență, modele folosite, etichetă AI |
| Dosar de Consiliu | Documentul pregătit pentru o decizie luată cu Claude (șablonul Ș12) |
| Înregistrare de decizie | Urma scrisă a unei hotărâri a Strategului (șablonul Ș13) |
| Coada de erori | Joburile care au eșuat repetat și cer o decizie umană |
| Poartă | Condiția de trecere de la o fază la alta sau de la o lansare la alta |
| Staging | Copia de test a platformei, pornită permanent pe același VPS |
| CI | Verificările automate care rulează pe GitHub la fiecare schimbare |

### 27.2 Șabloane

Șabloanele sunt liste de câmpuri, nu formulare definitive. Agentul de cod le transformă în fișiere, în pasul F0.2, în directorul docs/sabloane.

#### Ș1 Fișierul de decizii

Folosit în F0.1 și în rutina zilnică (secțiunea 24.9). Un rând pentru fiecare hotărâre.

- Data.
- Decizia, într-o propoziție.
- Opțiunile respinse.
- Motivul.
- Cine a decis.
- Ce pas sau ce secțiune atinge.
- Când se revede.

Primele trei intrări: nișa-pilot, cu notele pe cele șase criterii din secțiunea 4.2; pachetul-pilot; numele agenției și domeniul.

#### Ș2 Inventarul modelelor

Folosit în F0.3 și încărcat în registru în F3.1. Un rând pentru fiecare pereche furnizor–model.

| Câmp | Ce notezi |
| --- | --- |
| Furnizor și model | Numele exacte, așa cum apar la furnizor |
| Nivel estimat | T1, T2 sau T3, până la testul comparativ din F3.6 |
| Limite | Cereri pe minut și pe zi; tokeni pe minut și pe zi; ora de resetare |
| Capacități | Ieșire JSON, unelte, imagini, fereastră de context |
| Uz comercial | Permis sau nu, cu linkul către termeni |
| Date | Dacă furnizorul antrenează pe datele trimise |
| Restricții regionale | Mai ales pentru utilizatorii din SEE |
| Sursă și dată | De unde ai citit și când |
| Referința cheii | Numele secretului, niciodată cheia însăși |

Regulă: un rând fără „uz comercial permis”, cu link, rămâne inactiv pentru producția clienților.

#### Ș3 Fișa de pregătire și măsurare a VPS-ului dedicat

Folosit în F0.4. Închide punctul de decizie PD1.

- **Ce ai cumpărat:** furnizor, plan, locație, număr de nuclee, nuclee dedicate sau partajate, memorie, disc și tipul lui.
- **Drepturi:** ai acces de administrator sau nu; cine face instalarea inițială.
- **Instalarea inițială, bifată punct cu punct:**
  - [ ] Docker și Docker Compose
  - [ ] Utilizator fără drepturi de administrator, sub care rulează platforma
  - [ ] Firewall: deschise doar 80, 443 și administrarea, pe cheie
  - [ ] Proxy cu certificate automate și subdomeniile create
  - [ ] Serviciile repornesc singure după repornirea serverului
  - [ ] Actualizări de securitate automate pentru sistem
- **Test de procesor:** timpul unei sarcini de probă pe un nucleu și pe toate nucleele.
- **Rezultat:** numărul de culoare grele, tabelul din secțiunea 6.4 refăcut, bugetul de disc pentru media.
- **Decizia PD1:** continui, ajustezi sau schimbi VPS-ul.

#### Ș4 Tabelul de urmărire a aprobărilor

Folosit de la F0.6 până la ultima aprobare. Se revede săptămânal (secțiunea 22.10).

Coloane: platformă, cerere, val, ce cere, data trimiterii, stare, ultima verificare, observații primite, pasul care depinde de ea.

| Platformă | Cerere | Val | Pasul care depinde de ea |
| --- | --- | --- | --- |
| Meta | Verificarea firmei în Meta Business | 1 | F9.2, F13.1 |
| Meta | Aplicație în modul de dezvoltare | 1 | F9.2, F9.3 |
| Meta | App Review pentru pagini și Instagram | 2 | Publicarea pe conturile clienților |
| Meta | App Review pentru mesaje și comentarii | 2 | F12.7 pe conturile clienților |
| Meta | App Review pentru administrarea reclamelor | 2 | F13 pe conturile clienților |
| Meta | Confirmarea identității pentru Ad Library API | 1 | F10.8 |
| Google | Proiect Cloud și ecran de consimțământ, în modul de test | 1 | F9.4 |
| Google | Verificarea OAuth și auditul de conformitate YouTube | 2 | Clipuri publice prin API |
| Google | Acces Google Ads API, nivelul Explorer | 1 | F13.2 |
| Google | Acces la Google Trends API | 1 | F10.7 |
| TikTok | Aplicație cu Content Posting API, în modul de test | 1 | F9.6 |
| TikTok | Auditul aplicației | 2 | Postări publice prin API |
| LinkedIn | Aplicație și Community Management API | 1 | F9.5 pe pagini de companie |

#### Ș5 Specificația unui pas

Folosit înaintea fiecărei sesiuni de cod (secțiunea 24.5). Un fișier scurt, în docs/specs, numit după codul pasului.

- **Pasul:** cod, titlu, fază.
- **Context:** ce există deja și de ce este nevoie de acest pas.
- **Ce se construiește:** listă numerotată, fără cod.
- **Ce nu se construiește:** ce rămâne pentru alți pași, cu codul lor.
- **Contracte de date:** ce intră, ce iese, ce tabele sau scheme apar sau se schimbă.
- **Teste de acceptare:** 4–8 teste observabile, scoase din „Gata când”.
- **Riscuri:** cu trimitere la registrul din secțiunea 26.
- **Module atinse.**
- **Depinde de** și **deblochează.**
- **Revizuire obligatorie:** da sau nu (secțiunea 24.4).
- **Întrebări deschise:** tot ce documentul nu hotărăște.

Exemplu completat, pentru F2.5 Executorul de efecte externe:

- **Context.** Există execuția durabilă (F2.1), cozile (F2.2) și mașina de stări (F2.3). Nu există încă niciun conector real. Executorul este singura ușă spre exterior (componenta B7, secțiunile 6.1 și 7.3).
- **Ce se construiește.**
  1. Tabelul „de trimis”: client, livrabil, canal, versiune, tipul efectului, conținutul de trimis, cheia de idempotență, starea, numărul de încercări, răspunsul platformei, momentele.
  2. Stările unui efect: în așteptare, în trimitere, trimis, eșuat temporar, eșuat definitiv, anulat.
  3. Regula cheii: client, livrabil, canal și versiune. A doua cerere cu aceeași cheie întoarce rezultatul primei.
  4. Verificarea „există deja la platformă?”, înaintea oricărei reîncercări de după o eroare.
  5. Interfața de conector și un conector fals, care poate fi pus să reușească, să eșueze sau să răspundă cu eroare după ce a executat.
  6. Oprirea publicării, global și pe client.
  7. O intrare în jurnalul de audit pentru fiecare încercare.
- **Ce nu se construiește.** Conectorii reali (F9). Planificarea pe sloturi (F2.6). Ecranele (F2.9). Regulile de reclame (F13).
- **Contracte de date.** Intră o cerere de efect, cu câmpurile de la punctul 1. Iese starea, identificatorul de la platformă, linkul sau eroarea. Nicio componentă nu apelează direct un conector.
- **Teste de acceptare.**
  1. Același efect cerut de două ori se execută o singură dată.
  2. Conectorul fals execută, apoi răspunde cu eroare: executorul verifică și nu trimite a doua oară.
  3. Procesul este oprit forțat în timpul trimiterii: după repornire, la conectorul fals există un singur efect.
  4. Cu oprirea globală activă nu pleacă niciun efect nou, iar cererile rămân în așteptare.
  5. Un efect pentru clientul A nu poate fi cerut cu datele clientului B.
  6. Fiecare încercare apare în jurnalul de audit.
- **Riscuri.** RT5, publicare dublă. RT6, material pe contul altui client.
- **Module atinse.** Operare (executorul), publicare (interfața de conector), migrări, teste de contract și de avarie.
- **Depinde de** F2.1 și F2.3. **Deblochează** F6.6, F9.1, F12.2 și F13.4.
- **Revizuire obligatorie:** da.

#### Ș6 Instrucțiunea standard pentru sesiunea de cod

Folosită la pornirea fiecărei sesiuni (secțiunea 24.9). Completezi doar codul și titlul pasului.

> Lucrezi în repo-ul agenției, la pasul \[cod\]: \[titlu\].
>
> 1. Citește, în această ordine: fișierul de reguli pentru agenți, specificația pasului din docs/specs și deciziile de arhitectură la care trimite specificația.
> 2. Înainte de orice cod, scrie în cel mult zece rânduri ce ai înțeles, ce presupui și ce nu vei atinge. Întreabă doar dacă lipsește ceva fără de care nu poți continua.
> 3. Creează ramura, cu codul pasului în nume.
> 4. Scrie întâi testele de acceptare din specificație. Arată că pică din motivul corect.
> 5. Scrie codul minim care le face să treacă. Fără dependențe noi nejustificate, fără apeluri la modele în afara gateway-ului, fără efecte externe în afara executorului, fără secrete în cod.
> 6. Rulează toate testele și verificările din fișierul de reguli. Pune în raport exact ce ai rulat și ce a ieșit.
> 7. Actualizează documentația atinsă și jurnalul de schimbări.
> 8. Deschide cererea de integrare, cu descrierea după șablon.
> 9. Încheie cu raportul de sesiune: ce ai făcut, ce nu ai făcut, ce nu ai putut verifica, cum verific eu „Gata când” de pe telefon și ce propui pentru alt pas.
>
> Nu declara pasul gata fără ieșirea testelor. Dacă specificația contrazice o decizie de arhitectură, oprește-te și spune.

#### Ș7 Instrucțiunea pentru revizor

Folosită cu celălalt model, după sesiunea de cod (secțiunea 24.4).

> Ești revizorul pasului \[cod\]. Primești specificația și diferența de cod. Nu ai văzut conversația autorului și nu ai nevoie de ea.
>
> Verifică, în această ordine:
>
> 1. Fiecare test de acceptare din specificație există și verifică într-adevăr criteriul, nu o variantă slăbită a lui.
> 2. Codul nu face mai mult decât cere pasul.
> 3. Cazurile-limită: intrări goale, valori duble, repornire la mijloc, doi clienți diferiți.
> 4. Securitatea: izolarea pe client, secretele, validarea intrărilor, drepturile minime.
> 5. Lucrurile interzise din fișierul de reguli.
> 6. Dependențele noi și justificarea lor.
> 7. Complexitatea care se poate scoate.
>
> Răspunde cu: verdictul (aprobat, aprobat cu observații, respins); lista problemelor, pe severitate (blocant, important, minor), fiecare cu fișierul, locul și remedierea propusă; ce ai verificat fără să găsești probleme. Nu rescrie codul.

#### Ș8 Instrucțiunea pentru redactarea specificației

Folosită într-o sesiune separată de cea de cod (secțiunea 24.5).

> Redactează specificația pasului \[cod\], după șablonul Ș5, din documentul de arhitectură. Citește secțiunile indicate în fișa pasului (secțiunea 27.3) și specificațiile pașilor de care depinde. Nu scrie cod. Transformă „Gata când” în 4–8 teste de acceptare observabile. Scrie explicit ce nu se construiește. Marchează orice presupunere. Dacă documentul se contrazice sau lipsește o decizie, pune întrebarea la începutul specificației. Nu alege în tăcere.

#### Ș9 Cererea de integrare și raportul de sesiune

- Pasul: cod și titlu.
- Ce s-a schimbat, în 3–5 rânduri.
- Testele de acceptare, bifate, fiecare cu locul lui în repo.
- Ce s-a rulat și ce a ieșit.
- Migrări: există sau nu; sunt compatibile cu versiunea anterioară.
- Dependențe noi, cu justificare.
- Comutatoare de funcții adăugate.
- Cum se verifică pe staging, de pe telefon.
- Cum se revine la versiunea anterioară.
- Ce nu s-a putut verifica.
- Ce a rămas în afara pasului, ca propunere.

#### Ș10 Lista ta de verificare a unui pas

- [ ] Raportul de sesiune conține ieșirea testelor, nu doar afirmația că trec
- [ ] CI este verde pe cererea de integrare
- [ ] „Gata când” l-ai văzut tu, pe staging, de pe telefon
- [ ] Revizorul nu are probleme blocante deschise
- [ ] Nu au apărut dependențe noi fără justificare
- [ ] Nimic din afara pasului nu a fost modificat
- [ ] Documentația și jurnalul de schimbări sunt actualizate
- [ ] Hotărârile luate pe parcurs sunt în fișierul de decizii
- [ ] Știi cum se revine la versiunea anterioară
- [ ] Pasul următor are specificație

#### Ș11 Decizia de arhitectură

- Număr și titlu.
- Stare: propusă, acceptată sau înlocuită de altă decizie.
- Context.
- Opțiunile, fiecare cu avantaje și costuri.
- Decizia.
- Consecințe.
- Ce ar schimba decizia.
- Data și cine a decis.

#### Ș12 Dosarul și decizia de Consiliu

Dosarul, pregătit de platformă (secțiunea 7.6):

- Clientul și campania.
- Motivul: revizuire lunară, escaladare, pivot, schimbare de prompt sau incident.
- Întrebarea precisă. Una, cel mult trei.
- Contextul pe scurt: obiectiv, strategia curentă, criteriile de oprire.
- Cifrele: indicatorul principal față de prag, pe ultimele ferestre.
- Ce s-a încercat și ce a ieșit.
- Opțiunile, fiecare cu dovezi, cost și risc.
- Constrângerile: contract, plafoane, reguli.
- Ce date lipsesc.

Decizia, întoarsă de Consiliu:

- Alegerea.
- Motivele, pe scurt.
- Condițiile.
- Ce se măsoară și când se reverifică.
- Ce cere aprobarea ta sau a clientului.
- Nivelul de încredere.

Reguli: dosarul nu conține date personale și nici secrete. O decizie care atinge bani sau contract rămâne propunere până o aprobi tu.

#### Ș13 Înregistrarea de decizie a Strategului

- Data și fereastra analizată.
- Ce s-a văzut: cifrele, față de prag.
- Dacă datele sunt suficiente.
- Verdictul: continuă, ajustează, pivotează, oprește sau așteaptă.
- La pivot: cele trei ipoteze, cu dovezi și cost, și cea aleasă.
- Ce se schimbă concret.
- Ce rezultat se așteaptă.
- Data verificării.
- Cine a aprobat.

#### Ș14 Procedura de incident și analiza de după

Procedura (secțiunea 22.9):

- Titlu și severitate.
- Simptom: cum îl recunoști.
- Primele cinci minute: ce buton de oprire apeși.
- Verificări, în ordine.
- Acțiuni de remediere.
- Cum confirmi că s-a rezolvat.
- Pe cine anunți și cu ce text.
- Criteriul de închidere.

Analiza de după:

- Ce s-a întâmplat, pe linia timpului.
- Impactul.
- Cauza.
- Ce a mers bine.
- Ce regulă, test sau alertă nouă îl previne.
- Pasul de reparație, cu termen.

#### Ș15 Regula, faptul și rândul de conformitate

O regulă dintr-un pachet (secțiunea 9.7):

- Identificator și pachet: platformă, nișă sau client.
- Textul regulii.
- Tipul de potrivire: listă, expresie, calcul sau rubrică.
- Severitate.
- Sursa: politica platformei sau legea, cu link.
- Data ultimei verificări.
- Un exemplu care trebuie blocat și unul care trebuie să treacă.

Un fapt din registru (secțiunea 9.3):

- Enunțul.
- Tipul: preț, caracteristică, garanție, program, adresă sau mențiune legală.
- Valoarea exactă și unitatea.
- Sursa.
- Cine l-a aprobat.
- Valabil de la, până la.
- Canalele pe care se poate folosi.

Un rând din registrul de conformitate sau din matricea pe țări (secțiunile 21.10 și 17.4):

- Platforma sau țara.
- Regula-cheie.
- Controlul nostru.
- Cine a verificat și când.
- Data următoarei verificări.

#### Ș16 Jurnalul de fricțiuni din pilot

Folosit în F15.5 (secțiunea 25.6). Un rând pentru fiecare problemă.

- Data și clientul.
- Etapa: onboarding, aprobare, publicare, raport sau facturare.
- Ce s-a întâmplat.
- Cât timp a costat.
- Cauza.
- Ce devine: pas de reparație, regulă, exemplu sau nimic.
- Starea.

### 27.3 Fișa pașilor

Tabelele completează secțiunea 23. Pentru fiecare pas arată cine îl face, de ce depinde, ce secțiuni citește cel care scrie specificația și ce trebuie să ai tu pregătit înainte de sesiune. „Agent” înseamnă agentul de cod. Verificarea lui „Gata când” este a ta la fiecare pas.

#### F0 – Fundația fără cod

| Pas | Cine | Depinde de | Citește | Pregătești înainte |
| --- | --- | --- | --- | --- |
| F0.1 Decizii de pornire | Tu | – | 4.1–4.5, 21.12 | Notele pe cele șase criterii pentru 3–4 nișe; trei variante de nume, cu domeniu liber |
| F0.2 Repo și reguli | Tu și agent | F0.1 | 24.1–24.3, 24.8, 6.7, 27.2 | Cont GitHub, repo privat gol, acces pentru agentul de cod |
| F0.3 Inventarul modelelor | Tu | – | 8.1, 2.2 | Conturile și cheile pe care le ai; paginile de termeni ale furnizorilor |
| F0.4 Pregătirea și măsurarea VPS-ului dedicat | Tu și agent | F0.2 | 6.4–6.6, 2.1 | Datele de acces la VPS; subdomeniile create la registrar |
| F0.5 Site minim | Agent | F0.1, F0.4 | 19.1, 21.7–21.9, 15.3 | Domeniul, datele firmei, textele legale de lucru |
| F0.6 Cereri de aprobare | Tu | F0.5, F0.8 | 15.3, 16.2, 12.1 | Documentele firmei, un act de identitate, conturile agenției |
| F0.7 Juridic | Tu | F0.1 | 21.13, 4.11, 21.7–21.12 | Avocatul ales; o pagină care descrie platforma |
| F0.8 Conturile agenției | Tu | F0.1 | 15.1, 4.3 | Numele, un logo provizoriu, o adresă de email a firmei |

#### F1 – Scheletul platformei

| Pas | Cine | Depinde de | Citește | Pregătești înainte |
| --- | --- | --- | --- | --- |
| F1.1 Aplicația de bază | Agent | F0.2 | 6.1–6.3, 24.1 | – |
| F1.2 Dependențe fixate | Agent | F1.1 | 6.3, 21.5 | – |
| F1.3 Baza de date și migrările | Agent | F1.1 | 6.3, 6.4, 20.1 | – |
| F1.4 Clienți, utilizatori, roluri | Agent | F1.3 | 20.1, 20.2, 21.1, 18.5 | – |
| F1.5 Autentificare | Agent | F1.4 | 21.3 | Telefonul, cu o aplicație de coduri |
| F1.6 Jurnalul de audit și de evenimente | Agent | F1.4 | 20.1, 22.1 | – |
| F1.7 Coaja panoului | Agent | F1.5 | 18.1, 18.2, 6.3 | Telefonul; acordul pentru notificări |
| F1.8 Livrarea | Agent și tu | F0.4, F1.2 | 6.4, 6.6, 22.8, 25.1 | Secretele de CI, puse de tine în GitHub |
| F1.9 Backup | Agent și tu | F1.8 | 22.6, 22.7 | Spațiul de stocare extern ales și cheile lui |
| F1.10 Botul Telegram | Agent și tu | F1.6 | 18.6, 7.8, 22.4 | Botul creat și identificatorul conversației tale |

#### F2 – Motorul

| Pas | Cine | Depinde de | Citește | Pregătești înainte |
| --- | --- | --- | --- | --- |
| F2.1 Execuția durabilă | Agent | F1.3, F1.8 | 6.3, 7.3, 6.7 (ADR-03) | – |
| F2.2 Cozile | Agent | F2.1 | 7.5, 6.4 | Numărul de culoare grele, din F0.4 |
| F2.3 Mașina de stări a livrabilului | Agent | F2.1 | 7.1, 7.2, 20.2 | – |
| F2.4 Limite anti-buclă | Agent | F2.3 | 7.3 | – |
| F2.5 Executorul de efecte externe | Agent | F2.1, F2.3 | 7.3, 7.8, 6.1, 20.1 | – |
| F2.6 Planificatorul de timp | Agent | F2.2 | 7.5, 5.3 | – |
| F2.7 Watchdog și coada de erori | Agent | F2.2, F1.10 | 22.3–22.5 | – |
| F2.8 Cererile de aprobare | Agent | F2.3, F1.7 | 7.2, 7.3, 18.6 | – |
| F2.9 Ecranele Producție și Operare | Agent | F2.3–F2.8 | 18.2, 18.4, 22.5 | – |
| F2.10 Nivelurile de autonomie | Agent | F2.8 | 7.4 | – |

#### F3 – Gateway de modele

| Pas | Cine | Depinde de | Citește | Pregătești înainte |
| --- | --- | --- | --- | --- |
| F3.1 Registrul de furnizori și modele | Agent | F0.3, F2.9 | 8.1 | Inventarul completat; cheile puse în secretele de pe VPS |
| F3.2 Clientul unificat | Agent | F3.1 | 8.3, 8.6, 21.5 | – |
| F3.3 Limitatoarele de cotă | Agent | F3.2 | 8.4 | – |
| F3.4 Rutarea și lanțurile de rezervă | Agent | F3.3 | 8.2, 8.3 | – |
| F3.5 Modelul local și modelul de embeddings | Agent | F0.4, F2.2 | 6.3, 6.4, 8.6 | Decizia PD1 |
| F3.6 Testul comparativ pe română | Agent și tu | F3.4, F3.5 | 8.10 | 2–3 ore pentru evaluarea umană pe eșantion |
| F3.7 Registrul de prompturi și jurnalul de apeluri | Agent | F3.2 | 8.8 | – |
| F3.8 Bugete și priorități | Agent | F3.3, F3.4 | 8.5 | – |
| F3.9 Garda de date personale și garda de injecții | Agent | F3.2 | 8.9, 12.8, 21.6 | – |
| F3.10 Ecranul „Modele și cote” | Agent | F3.3, F3.7 | 18.2 | – |
| F3.11 Planificatorul de capacitate | Agent | F3.8, F2.6 | 5.2, 4.7, 8.5 | – |

#### F4 – Creierul de brand și onboarding

| Pas | Cine | Depinde de | Citește | Pregătești înainte |
| --- | --- | --- | --- | --- |
| F4.1 Modelul Creierului | Agent | F1.4 | 10.1, 10.4, 20.2 | – |
| F4.2 Colectorul de surse | Agent | F2.2, F3.9 | 12.3, 12.8 | Lista de domenii permise: site-urile brandurilor proprii |
| F4.3 Vectori și căutare hibridă | Agent | F4.1, F3.5 | 10.3, 10.5 | – |
| F4.4 Asistentul de onboarding | Agent și tu | F4.1, F3.4 | 19.3, 13.8 | Răspunzi tu la interviu, pentru CariereAI și BigBrain |
| F4.5 Profilul de brand | Agent și tu | F4.2, F4.4 | 13.8, 10.1 | 20 de minute pentru alegerea tonului |
| F4.6 Registrul de fapte și catalogul de oferte | Agent și tu | F4.2, F4.4 | 9.3, 10.1, 10.4 | Prețurile și ofertele brandurilor proprii |
| F4.7 Constructorul de context | Agent | F4.3, F4.6 | 10.3 | – |
| F4.8 Ecranul „Creierul de brand” | Agent | F4.5–F4.7 | 18.2, 10.6 | – |
| F4.9 Profilul de public și vocea clientului | Agent și tu | F4.2, F4.6 | 5.4, 12.4 | Recenzii, întrebări frecvente și mesaje reale ale brandurilor proprii |
| F4.10 Harta pieței și brieful de insight | Agent | F4.2, F4.9 | 5.4, 12.4, 12.6 | 3–5 concurenți pentru fiecare brand |
| F4.11 Strategia pe 90 de zile, prima formă | Agent și tu | F4.10 | 7.7, 5.2 | Obiectivul pe 90 de zile al fiecărui brand |

#### F5 – Validare și aprobări

| Pas | Cine | Depinde de | Citește | Pregătești înainte |
| --- | --- | --- | --- | --- |
| F5.1 Cadrul de validare | Agent | F2.3, F3.2 | 9.1, 9.2 | – |
| F5.2 Validatorii de structură și de limbă | Agent | F5.1 | 9.4, 13.5 | – |
| F5.3 Verificatorul de fapte | Agent | F5.1, F4.6 | 9.3 | – |
| F5.4 Pachetele de reguli și validatorul de politici | Agent și tu | F5.1 | 9.7, 21.10–21.12 | Regulile nișei-pilot, dacă le ai de la avocat |
| F5.5 Auditorul de ton și evaluatorul de lizibilitate | Agent | F5.1, F4.3, F4.5 | 9.4, 9.6 | – |
| F5.6 Originalitate și garda juridică | Agent | F5.1, F4.3 | 9.4, 21.11 | – |
| F5.7 Seturile de aur și bancul de evaluare | Agent și tu | F5.2–F5.6 | 9.6, 9.9, 11.2 | Etichetezi 30–100 de exemple per validator, în tranșe |
| F5.8 Calibrarea judecătorilor | Agent și tu | F5.7 | 9.6 | – |
| F5.9 Biroul de aprobări | Agent | F2.8, F5.1 | 18.3, 11.2 | – |
| F5.10 Carantină și contestații | Agent | F5.9 | 9.8 | – |

#### F6 – Producția de text și publicarea asistată

| Pas | Cine | Depinde de | Citește | Pregătești înainte |
| --- | --- | --- | --- | --- |
| F6.1 Strategul de conținut și calendarul | Agent și tu | F4.11, poarta F5 | 5.5, 13.1 | – |
| F6.2 Autorul de brief | Agent | F6.1, F4.7 | 13.2 | – |
| F6.3 Hook-uri și postări | Agent | F6.2 | 13.1–13.5 | – |
| F6.4 Scripturi video | Agent | F6.2 | 13.3, 13.4 | – |
| F6.5 Adaptorul pe platformă | Agent | F6.3 | 5.6, 15.4 | – |
| F6.6 Publicarea asistată | Agent și tu | F6.5, F2.5, F1.7 | 15.2, 15.4, 15.6 | Conturile agenției, deschise pe telefon |
| F6.7 Capturarea feedbackului | Agent | F5.9 | 11.2, 10.1 | – |
| F6.8 Proba de două săptămâni | Tu | F6.1–F6.7 | 25.4, 22.10 | 15–30 de minute pe zi, timp de 14 zile |

#### F7 – Site, portal, facturare

| Pas | Cine | Depinde de | Citește | Pregătești înainte |
| --- | --- | --- | --- | --- |
| F7.1 Site-ul complet | Agent și tu | F0.5 | 19.1 | Textele paginilor și prețurile de lucru |
| F7.2 Formularul de audit | Agent | F7.1, F1.4 | 17.1, 4.3, 21.8 | Adresa și cheia motorului de audit din BigBrain |
| F7.3 Portalul: cont și onboarding | Agent | F4.4 | 19.2, 19.3, 21.3 | – |
| F7.4 Portalul: Creier, calendar, aprobări | Agent | F7.3, F5.9, F4.8 | 19.2, 19.4 | – |
| F7.5 Portalul: materiale și inboxul de tendințe | Agent | F7.3 | 19.2, 12.2, 21.4 | – |
| F7.6 Facturare | Agent și tu | F7.3 | 19.5, 5.13 | Contul de comerciant, cu mediul de probă activ; hotărârea cu contabilul despre facturi |
| F7.7 Export și ștergere | Agent | F7.3 | 21.7, 10.5, 20.4 | – |
| F7.8 Raportul lunar, prima formă | Agent | F6.8 | 19.6 | – |
| F7.9 Oferta, pâlnia și paginile de captare | Agent și tu | F4.10, F5.6 | 5.5, 5.6, 13.3 | Oferta agenției pentru pagina de audit |
| F7.10 Cercetarea SEO și articolele | Agent | F4.2, poarta F5 | 13.6, 5.4, 5.6 | Accesul la Search Console pentru brandurile proprii |

#### F8 – Media

| Pas | Cine | Depinde de | Citește | Pregătești înainte |
| --- | --- | --- | --- | --- |
| F8.1 Vocea și licența ei | Agent și tu | F2.2 | 14.4, 2.2 | Răspunsul avocatului despre licența vocii sau hotărârea de a face o voce proprie |
| F8.2 Normalizarea textului românesc | Agent | F8.1 | 14.4 | – |
| F8.3 Transcrierea inversă și timpii pe cuvânt | Agent | F8.1 | 14.4, 14.5 | – |
| F8.4 Furnizorul de imagini și biblioteca de active | Agent și tu | F4.1 | 14.3, 5.7 | Conturi la surse de stock cu licență; cheia pentru imagini generate |
| F8.5 Lista de decizii de montaj și Regizorul | Agent | F8.3, F6.4 | 14.5, 14.6 | – |
| F8.6 Montajul pentru formatele A și B | Agent | F8.5, F8.4 | 14.1, 14.5 | – |
| F8.7 Subtitrări și sunet | Agent | F8.6 | 14.7, 14.8 | Biblioteca de muzică, cu fișierele de licență |
| F8.8 Controlul media și auditorul vizual | Agent | F8.6, F5.1 | 9.5 | – |
| F8.9 Testul de capacitate | Tu și agent | F8.8 | 14.11, 6.4, 4.7 | O zi obișnuită de producție de text, ca fundal |
| F8.10 Șabloane grafice și Compozitorul | Agent și tu | F4.5 | 14.10, 5.7 | Logoul, culorile și fonturile brandurilor proprii |
| F8.11 Proveniență și dezvăluire AI | Agent | F8.4, F8.6 | 15.6, 21.9, 5.8 | Încadrarea de la avocat, dacă a sosit |
| F8.12 Formatul E, om real | Agent și tu | F8.7, F7.5 | 14.1 | O filmare brută de un minut |

#### F9 – Publicarea prin API

| Pas | Cine | Depinde de | Citește | Pregătești înainte |
| --- | --- | --- | --- | --- |
| F9.1 Interfața comună de conector | Agent | F2.5 | 15.4, 15.7, 24.7 | – |
| F9.2 Facebook, pagini | Agent și tu | F9.1, F0.6 | 15.1, 15.3 | Aplicația Meta, în modul de dezvoltare; pagina agenției |
| F9.3 Instagram | Agent și tu | F9.2, F8.6 | 15.1, 6.5 | Contul profesional de Instagram, legat de pagină |
| F9.4 YouTube | Agent și tu | F9.1, F0.6, F8.6 | 15.1, 15.6 | Proiectul Google Cloud și canalul agenției |
| F9.5 LinkedIn | Agent și tu | F9.1 | 15.1 | Aplicația LinkedIn |
| F9.6 TikTok | Agent și tu | F9.1, F0.6, F8.6 | 15.1, 2.2 | Aplicația TikTok și contul agenției |
| F9.7 Planificarea, alegerea canalelor și zilele blocate | Agent | F2.6, F9.1 | 15.5, 5.5 | – |
| F9.8 Gardianul sănătății conturilor | Agent | F9.2 | 15.7, 5.3, 5.9 | – |
| F9.9 Site și blog | Agent | F7.10 | 5.9, 13.6 | Accesul la CMS-ul blogului |
| F9.10 Ecranul „Publicare” | Agent | F9.2–F9.6 | 18.2 | – |

#### F10 – Analiză și cercetare continuă

| Pas | Cine | Depinde de | Citește | Pregătești înainte |
| --- | --- | --- | --- | --- |
| F10.1 Colectorul de metrici | Agent | F6.6; cel puțin un conector din F9 | 5.12, 7.2 | – |
| F10.2 Curba de retenție YouTube | Agent | F9.4 | 2.2, 16.7 | – |
| F10.3 Legarea de etichete | Agent | F10.1 | 11.4, 13.4 | – |
| F10.4 Tablourile de bord și scorul de sănătate al clientului | Agent | F10.1 | 4.10, 4.13, 18.2 | – |
| F10.5 Raportul lunar complet | Agent | F10.3, F7.8 | 19.6, 5.12 | – |
| F10.6 Analiza de trafic proprie | Agent | F7.1 | 19.1, 16.7, 21.8 | – |
| F10.7 Cercetătorul de tendințe | Agent și tu | F4.2, F7.5 | 12.1, 12.2, 12.5, 12.7 | Cheia pentru YouTube Data API |
| F10.8 Analistul de reclame ale concurenței | Agent și tu | F4.10, F0.6 | 12.6, 12.1 | Identitatea confirmată pentru Meta Ad Library API |

#### F11 – Învățare, prima treaptă

| Pas | Cine | Depinde de | Citește | Pregătești înainte |
| --- | --- | --- | --- | --- |
| F11.1 Reflectorul | Agent | F10.3, F6.7 | 11.3 | – |
| F11.2 Curatorul și playbook-ul | Agent și tu | F11.1 | 11.3, 10.1 | – |
| F11.3 Alegerea adaptivă | Agent | F10.3 | 11.4 | – |
| F11.4 Registrul de experimente | Agent | F10.1 | 5.2, 11.2 | – |
| F11.5 Constituția | Agent | F11.2, F5.4 | 11.6, 7.8 | – |
| F11.6 Ecranul „Învățare” | Agent | F11.1–F11.5 | 11.7, 18.2 | – |

#### F12 – CRM, email, inbox

| Pas | Cine | Depinde de | Citește | Pregătești înainte |
| --- | --- | --- | --- | --- |
| F12.1 CRM-ul minimal | Agent | F7.2 | 17.7, 17.1 | – |
| F12.2 Email către abonați | Agent și tu | F12.1, F2.5 | 17.3, 17.4, 21.8 | Furnizorul de email ales; înregistrările DNS de pe subdomeniu |
| F12.3 Secvența de după audit | Agent | F12.2 | 17.3, 13.3 | – |
| F12.4 Calificare și scor | Agent | F12.1 | 17.5 | – |
| F12.5 Programări | Agent | F12.1 | 17.6 | Programul tău de apeluri |
| F12.6 Generatorul de oferte | Agent | F12.4, F7.2 | 17.7, 4.4, 4.5 | – |
| F12.7 Inboxul social | Agent și tu | F9.2 sau F9.3 | 17.8 | Permisiunile de mesaje și comentarii din aplicația Meta |
| F12.8 Răspunsuri și escaladare | Agent | F12.7, F4.6 | 17.8, 21.9 | – |
| F12.9 Lista de conturi-țintă | Agent | F4.2, F12.1 | 17.2 | Nișa și localitățile vizate |
| F12.10 Asistentul de suport din portal | Agent | F7.4, F12.8 | 5.13, 19.2 | – |

#### F13 – Reclame, Strateg, Consiliu

| Pas | Cine | Depinde de | Citește | Pregătești înainte |
| --- | --- | --- | --- | --- |
| F13.1 Citirea rezultatelor Meta | Agent și tu | F9.2 | 16.2, 16.7 | Contul de reclame al agenției, cu drept de citire |
| F13.2 Citirea rezultatelor Google Ads | Agent și tu | F0.6 | 16.2 | Contul Google Ads al agenției; nivelul Explorer activ |
| F13.3 Planificatorul media | Agent | F4.11, F10.8 | 16.3, 5.10 | – |
| F13.4 Constructorul de campanii, propunerile de schimbare și executorul | Agent | F2.5, F13.1 | 16.1, 16.3, 5.10 | – |
| F13.5 Gardianul de buget și oprirea de urgență | Agent | F13.4 | 16.4, 16.5 | – |
| F13.6 Strategul și înregistrările de decizie | Agent | F10.3, F4.11 | 7.7, 16.9 | – |
| F13.7 Consiliul | Agent și tu | F13.6 | 7.6 | Modul de conectare ales; planul tău Claude |
| F13.8 Verificarea reclamelor înainte de lansare | Agent | F5.4, F7.9 | 16.8 | – |
| F13.9 Testarea creativurilor | Agent | F13.4, F11.4 | 16.6 | – |
| F13.10 Campania reală de probă | Tu și agent | F13.1–F13.9, F7.2 | 16.3–16.7 | Un buget mic de probă, pe cardul agenției |

#### F14 – Învățare, a doua treaptă

| Pas | Cine | Depinde de | Citește | Pregătești înainte |
| --- | --- | --- | --- | --- |
| F14.1 Optimizatorul de prompturi | Agent | F5.7, F3.8 | 11.5 | – |
| F14.2 Umbră, canar, promovare, revenire | Agent | F14.1, F11.5 | 11.5, 11.6 | – |
| F14.3 Predictorul de performanță | Agent | F10.3; pragul de date | 11.2 | – |
| F14.4 Teste A/B formale | Agent | F11.4 | 11.2, 16.6 | – |
| F14.5 Scorul de lead și riscul de plecare, ca modele | Agent | F12.4, F10.4; pragul de date | 17.5, 5.13 | – |
| F14.6 Consolidarea nocturnă a memoriei | Agent | F4.3 | 10.4 | – |

#### F15 – Întărire și lansare

| Pas | Cine | Depinde de | Citește | Pregătești înainte |
| --- | --- | --- | --- | --- |
| F15.1 Teste de avarie | Agent și tu | Drumul critic din 23.21 | 25.3 | – |
| F15.2 Revizuire de securitate | Agent, cu alt model, și tu | F15.1 | 21.1–21.6, 24.4 | – |
| F15.3 Exercițiu de restaurare completă | Tu și agent | F1.9 | 22.6, 22.7 | Un mediu curat: VPS-ul vechi sau un set nou de containere |
| F15.4 Juridic finalizat | Tu | F0.7 | 21.13, 4.11 | – |
| F15.5 Pilot cu trei clienți | Tu | Poarta de lansare 2 | 25.6, 4.5 | Trei clienți semnați |
| F15.6 Lansarea comercială | Tu | Poarta de lansare 3 | 25.5 | – |

### 27.4 Trasabilitate: unde se construiește fiecare lucru

Tabelele arată că nicio componentă, niciun ecran și nicio zonă a portalului nu rămâne fără pas de construcție. Dacă adaugi o componentă, adaugi și rândul ei aici.

#### Cele 87 de componente

| Componentă | Pași |
| --- | --- |
| A1 Consiliul | F13.7 |
| A2 Strategul de campanie | F4.11 (prima strategie), F13.6 (revizuiri și pivot) |
| A3 Managerul de experimente | F11.4, F14.4 |
| A4 Planificatorul de capacitate | F3.11 |
| B1 Orchestratorul | F2.3, F2.4 |
| B2 Gateway de modele și FinOps | F3.1–F3.4, F3.7, F3.8, F3.10 |
| B3 Watchdog și recuperare | F2.7 |
| B4 Planificatorul de timp | F2.6 |
| B5 Notificatorul | F1.7, F1.10, F2.8 |
| B6 Sănătatea conectorilor | F9.8 |
| B7 Executorul de efecte externe | F2.5 |
| C1 Colectorul de surse | F4.2 |
| C2 Cercetătorul de tendințe | F10.7 |
| C3 Analistul de reclame ale concurenței | F10.8 |
| C4 Profilerul de public | F4.9 |
| C5 Vocea clientului | F4.9 |
| C6 Cercetătorul SEO | F7.10 |
| C7 Analistul de piață și ofertă | F4.10 |
| C8 Sintetizatorul de cercetare | F4.10 |
| D1 Strategul de brand | F4.5 |
| D2 Arhitectul de ofertă și pâlnie | F7.9 |
| D3 Strategul de conținut | F6.1 |
| D4 Planificatorul de canale | F9.7 |
| D5 Autorul de brief | F6.2 |
| E1 Generatorul de hook-uri | F6.3 |
| E2 Scenaristul video | F6.4 |
| E3 Copywriterul de conversie | F7.9 |
| E4 Autorul de postări | F6.3 |
| E5 Autorul de articole SEO | F7.10 |
| E6 Autorul de secvențe email | F12.3 |
| E7 Agentul SEO on-page | F7.10, F9.9 |
| E8 Editorul | F6.3 |
| E9 Localizatorul | Faza F16 |
| E10 Adaptorul pe platformă | F6.5 |
| F1 Designerul de identitate | F8.10 |
| F2 Inginerul de prompturi vizuale | F8.4 |
| F3 Furnizorul de imagini | F8.4 |
| F4 Compozitorul de creativuri și miniaturi | F8.10 |
| F5 Vocea | F8.1–F8.3 |
| F6 Regizorul video | F8.5 |
| F7 Montajul și post-producția | F8.6, F8.7, F8.12 |
| F8 Bibliotecarul de active | F8.4, F8.11 |
| G1 Validatorul de structură | F5.2 |
| G2 Verificatorul de fapte | F5.3 |
| G3 Validatorul de politici | F5.4 |
| G4 Auditorul de ton | F5.5 |
| G5 Auditorul vizual | F8.8 |
| G6 Controlul tehnic media | F8.8 |
| G7 Originalitate și drepturi | F5.6, F8.4 |
| G8 Lizibilitate și conversie | F5.5 |
| G9 Garda juridică | F5.6 |
| G10 Calitatea limbii | F5.2 |
| G11 Proveniență și dezvăluire AI | F8.11 |
| G12 Garda de date personale | F3.9 |
| G13 Garda de injecții | F3.9 |
| G14 Calibrarea judecătorilor | F5.8 |
| H1 Editorul multi-canal | F6.6, F9.1–F9.6 |
| H2 Gardianul limitelor și al sănătății conturilor | F9.8 |
| H3 Răspunsuri în inbox | F12.8 |
| H4 Moderatorul de comentarii | F12.7 |
| H5 Expeditorul de email | F12.2 |
| H6 Editorul web | F9.9 |
| I1 Planificatorul media | F13.3 |
| I2 Constructorul de campanii | F13.4 |
| I3 Gardianul de buget | F13.5 |
| I4 Managerul de teste creative | F13.9 |
| I5 Verificarea înainte de lansare | F13.8 |
| I6 Anomalii și oprire de urgență | F13.5 |
| J1 Captare și îmbogățire conformă | F7.2, F12.1, F12.9 |
| J2 Scorarea și calificarea lead-urilor | F12.4, F14.5 |
| J3 Agentul de programări | F12.5 |
| J4 Igiena CRM | F12.1 |
| J5 Generatorul de oferte | F12.6 |
| J6 Asistentul de onboarding | F4.4 |
| K1 Colectorul de metrici | F10.1 |
| K2 Analistul de atribuire și retenție | F10.2, F10.3 |
| K3 Autorul de insight | F10.5 |
| K4 Bancul de evaluare | F5.7 |
| K5 Optimizatorul de prompturi și playbook-uri | F14.1, F14.2 |
| K6 Predictorul de performanță | F14.3 |
| K7 Analistul de experimente | F11.4, F14.4 |
| K8 Curatorul de cunoștințe | F11.2 |
| L1 Generatorul de rapoarte | F7.8, F10.5 |
| L2 Biroul de aprobări | F2.8, F5.9 |
| L3 Facturarea și abonamentele | F7.6 |
| L4 Monitorul de risc de plecare | F10.4 (pe reguli), F14.5 (ca model) |
| L5 Asistentul de suport | F12.10 |

#### Cele 18 ecrane ale panoului

| Ecran | Pasul în care apare | Pași care îl completează |
| --- | --- | --- |
| 1 Acasă | F1.7 | F2.5 (oprirea publicării), F3.10 (cote), F11.5 (înghețarea învățării), F13.5 (oprirea reclamelor) |
| 2 Aprobări | F5.9 | F5.10 |
| 3 Producție | F2.9 | F8.6 |
| 4 Alerte | F2.7 | F9.8, F13.5 |
| 5 Clienți | F1.4 | F2.10 (autonomie), F10.4 (scor de sănătate) |
| 6 Creierul de brand | F4.8 | F4.9, F11.2 |
| 7 Campanii | F4.11 | F11.4, F13.6 |
| 8 Calendar | F6.1 | F9.7 |
| 9 Agenți | F3.7 | F5.7 |
| 10 Validatoare | F5.4 | F5.8, F5.10 |
| 11 Modele și cote | F3.10 | F3.11 |
| 12 Învățare | F11.6 | F14.2 |
| 13 Media | F8.4 | F8.8, F8.10 |
| 14 Publicare | F9.10 | – |
| 15 Reclame | F13.1 | F13.2–F13.5 |
| 16 CRM și inbox | F12.1 | F12.5, F12.7 |
| 17 Rapoarte și analiză | F10.4 | F10.2, F10.5 |
| 18 Operare | F2.9 | F1.9 (backupuri), F13.7 (dosare de Consiliu) |

#### Zonele portalului

| Zonă | Pași |
| --- | --- |
| Onboarding | F7.3 |
| Creierul de brand | F7.4 |
| Calendar | F7.4 |
| Aprobări | F7.4 |
| Materiale | F7.5; prompterul, în F8.12 |
| Inboxul de tendințe | F7.5; prelucrarea linkurilor, în F10.7 |
| Reclame | F13.3–F13.5 |
| Rapoarte | F7.8, F10.5 |
| Facturare | F7.6 |
| Suport | F12.10 |
| Date | F7.7 |

### 27.5 Surse

Linkurile sunt cele din secțiunea 2.2, în aceeași ordine. Au fost verificate la 10 noiembrie 2026. La completarea din 11 noiembrie nu le-am reverificat și nu am adăugat fapte externe noi. Agentul de cod le reverifică în pasul în care construiește fiecare conector.

| Nr. | Subiect | Linkuri | Marcaj |
| --- | --- | --- | --- |
| 1 | Claude: Agent SDK și modul headless | [Claude: Agent SDK și modul headless](https://support.claude.com/en/articles/15036540-use-the-claude-agent-sdk-with-your-claude-plan) | \[V\] |
| 2 | Claude: credite API lunare | [Claude: credite API lunare](https://support.claude.com/en/articles/17154008-monthly-api-credits-for-max-ultra-and-team-plans) | \[V\] |
| 3 | OpenRouter: limite | [OpenRouter: limite](https://openrouter.ai/docs/limits) | \[V\] |
| 4 | Gemini API: termeni | [Gemini API: termeni](https://ai.google.dev/gemini-api/terms) | \[V\] |
| 5 | Groq: limite | [Groq: limite](https://console.groq.com/docs/rate-limits) | \[S\] |
| 6 | Cloudflare Workers AI: preț | [Cloudflare Workers AI: preț](https://developers.cloudflare.com/workers-ai/platform/pricing/) | \[S\] |
| 7 | Volatilitatea nivelurilor gratuite | [Volatilitatea nivelurilor gratuite](https://github.com/pacocartones/free-llm-api-hub) | \[S\] |
| 8 | TikTok: reguli de postare prin API | [TikTok: reguli de postare prin API](https://developers.tiktok.com/doc/content-sharing-guidelines) | \[V\] |
| 9 | YouTube: încărcare prin API | [YouTube: încărcare prin API](https://developers.google.com/youtube/v3/docs/videos/insert) | \[V\] |
| 10 | Instagram: publicare | [Instagram: publicare](https://developers.facebook.com/docs/instagram-platform/content-publishing) | \[V\] |
| 11 | LinkedIn: permisiuni | [LinkedIn: permisiuni](https://bundle.social/blog/linkedin-api-permissions) | \[S\] |
| 12 | Meta Ads: autorizare | [Meta Ads: autorizare](https://developers.facebook.com/docs/marketing-api/get-started/authorization) | \[V\] |
| 13 | Google Ads API: acces | [Google Ads API: acces](https://developers.google.com/google-ads/api/docs/first-call/dev-token) | \[V\] |
| 14 | Meta Ad Library API | [Meta Ad Library API](https://adsuploader.com/blog/facebook-ad-library-api) | \[S\] |
| 15 | Legea 506/2004, art. 12 | [Legea 506/2004, art. 12](https://legislatie.just.ro/Public/DetaliiDocument/56973) | \[V\] |
| 16 | AI Act, art. 50 | [AI Act, art. 50](https://www.actuia.com/en/news/ai-act-obligations-in-force-and-delays-under-omnibus-2026-1744/) | \[S\] |
| 17 | Etichetare AI pe platforme | [Etichetare AI pe platforme](https://www.postora.org/blog/ai-generated-content-labels-social-media-2026) | \[S\] |
| 18 | Voce în română: Piper | [Voce în română: Piper](https://huggingface.co/rhasspy/piper-voices/blob/952f41d04e72535c242ae181b2ee1ed13d357d12/ro/ro_RO/mihai/medium/MODEL_CARD); [VoxCPM2](https://huggingface.co/openbmb/VoxCPM2); [furnizor](https://tts.ai/text-to-speech/romanian/) | \[V\] |
| 19 | Video programatic: HyperFrames | [Video programatic: HyperFrames](https://github.com/heygen-com/hyperframes) | \[S\] |
| 20 | GEPA | [GEPA](https://arxiv.org/pdf/2507.19457); [ACE](https://arxiv.org/pdf/2510.04618) | \[V\] |
| 21 | DBOS | [DBOS](https://docs.dbos.dev) | \[V\] |
| 22 | Incidentul LiteLLM | [Incidentul LiteLLM](https://www.netspi.com/blog/executive-blog/ai-ml-pentesting/litellm-supply-chain-compromise/) | \[S\] |
| 23 | Reddit API | [Reddit API](https://octolens.com/blog/reddit-api-pricing) | \[S\] |
| 24 | Google Trends API | [Google Trends API](https://scrapfly.io/blog/posts/google-trends-api-alternatives) | \[S\] |
| 25 | Retenție video pe YouTube | [Retenție video pe YouTube](https://academy.adriel.com/en/youtube-analytics) | \[S\] |
| 26 | Revolut: Subscriptions API | [Revolut: Subscriptions API](https://developer.revolut.com/docs/guides/merchant/billing-subscriptions/api/introduction) | \[V\] |

### 27.6 Ce s-a schimbat în versiunea 1.1

Completări:

- Secțiunea 26, nouă: registrul de riscuri, primele zece, punctele de decizie, întrebările deschise.
- Secțiunea 27, nouă: convenții și glosar, 16 șabloane, fișa celor 146 de pași, trasabilitatea, sursele.
- Secțiunea 23.21, nouă: drumul critic până la pilot, pe pachet.

Schimbare de infrastructură, cerută de tine:

- VPS dedicat platformei, cu cel puțin 24 GB RAM, în locul celui de 12 GB împărțit cu CariereAI și BigBrain (secțiunile 1, 2.1, 6.4, 22.7).
- Toate serviciile stau pornite permanent. Bugetul de memorie urcă de la 6 GB la circa 21 GB, cu 3 GB rezervă.
- Culoarul greu unic devine mai multe culoare grele, câte unul la fiecare 4 nuclee (secțiunile 6.4, 7.5, 14.11).
- Modelul local trece de la unul mic, pornit la cerere, la unul de 7–9 miliarde de parametri, ținut încărcat.
- Staging rămâne pornit permanent. Învățarea pe modelul local nu mai așteaptă noaptea.
- Platforma primește proxy propriu și instalare inițială proprie. Motorul de audit din BigBrain este apelat prin rețea.
- Decizia de arhitectură ADR-16, nouă.
- Numărul de nuclee și discul nu îmi sunt cunoscute. Cifrele pornesc de la 8 nuclee și se refac în F0.4.

Corecturi:

| Ce era | De ce era o problemă | Ce este acum |
| --- | --- | --- |
| Toate cererile de aprobare API plecau în F0.6, „înainte de orice cod” | Aceleași recenzii cer o înregistrare video a fluxului, care nu există fără cod | Două valuri: primul în F0.6, al doilea la conectorul fiecărui canal (secțiunea 15.3; pașii F9.2–F9.6) |
| Embeddings în același serviciu cu modelul local, pe culoarul greu | Fiecare livrabil are nevoie de vectori; ar fi așteptat în spatele unei randări | Model de embeddings separat, încărcat în worker-light (secțiunile 6.3, 6.4, 10.5; pasul F3.5) |
| 12 componente din catalog nu aveau niciun pas de construcție, iar altele apăreau doar implicit | Secțiunea 5.1 promitea că planul arată unde apare fiecare | Nouă pași noi: F3.11, F4.9–F4.11, F7.9, F7.10, F10.7, F10.8, F12.10. Alți câțiva pași sunt extinși. Tabelul din 27.4 le acoperă pe toate |
| Poarta de pilot cerea doar faza F7 | Toate pachetele conțin video și raport cu cifre | Poarta cere drumul critic al pachetului vândut (secțiunile 23.21 și 25.4) |
| „Pornești pilotul în paralel cu F7–F9”, la poarta F6 | Contrazicea poarta de pilot | La poarta F6 pornesc discuțiile de vânzare. Pilotul pornește la poarta de lansare 2 |
| Două criterii diferite pentru trecerea la L2 (secțiunile 7.4 și 19.4) | „Trei luni fără respingeri” nu se potrivea cu „90% din prima” | Un singur criteriu, cel din 7.4, plus acordul clientului |
| Candidatul trecea „pe tot” traficul (secțiunea 11.5) | Constituția cere un grup de control de 10% | Candidatul merge pe 90%, iar 10% rămâne grup de control |
| „F0–F6 merg strict în serie” și „F0 în paralel cu F1” | Se contraziceau | F0.1–F0.4 înainte de F1; restul fazei F0, în fundal |
| Trimiteri la „anexă” fără anexă | Șabloanele nu existau | Trimiteri la șabloanele Ș1–Ș16 |
| Coduri care se suprapun: F1–F8 și L1–L4 | Un agent de cod le poate confunda | Regulă de citire în secțiunile 5.1 și 27.1 |

Numerotarea pașilor existenți nu s-a schimbat. Pașii noi sunt adăugați la sfârșitul fazelor lor.
