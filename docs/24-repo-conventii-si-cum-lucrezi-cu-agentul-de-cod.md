## 24. Repo, convenții și cum lucrezi cu agentul de cod

Repo-ul este organizat astfel încât un agent de cod fără memorie să poată prelua oricând. Regulile sunt în fișiere, deciziile sunt scrise, iar fiecare pas are specificație și teste de acceptare înainte de cod.

### 24.1 Structura repo-ului

| Director | Conținut |
| --- | --- |
| Rădăcină | Fișierul de reguli pentru agenți, fișierul de decizii, jurnalul de schimbări |
| docs | Acest document, împărțit pe secțiuni, cu index |
| docs/adr | Deciziile de arhitectură, una pe fișier |
| docs/specs | Specificația fiecărui pas, numită după codul pasului |
| docs/runbooks | Procedurile pentru incidente |
| docs/sabloane | Șabloanele din secțiunea 27.2 |
| docs/registre | Registrul de riscuri, tabelul de urmărire a aprobărilor, inventarul modelelor, fișa de măsurare a VPS-ului |
| app | Aplicația, pe module: conturi, creier, cercetare, planificare, producție, validare, media, publicare, reclame, CRM, analiză, învățare, operare, finanțe |
| app/gateway | Gateway-ul de modele |
| app/connectors | Un subdirector pentru fiecare platformă |
| app/web | Șabloanele și resursele interfeței |
| prompts | Prompturile, ca fișiere versionate, fiecare cu schema lui |
| rulepacks | Pachetele de reguli: pe platformă, pe nișă și pe client |
| evals | Seturile de aur și materialele intenționat greșite |
| templates | Șabloanele grafice și video |
| migrations | Migrările bazei de date |
| infra | Compose, configurarea proxy-ului, instalarea inițială a VPS-ului, scripturile de livrare și de backup |
| tests | Teste unitare, de contract, de integrare și de avarie |

### 24.2 Fișierul de reguli pentru agenți

Este un singur fișier, la rădăcină, citit de orice agent de cod la începutul sesiunii. Conține:

- scopul proiectului, în cinci rânduri;
- cele 16 decizii de arhitectură, cu interdicția de a le încălca fără o decizie nouă, scrisă;
- regulile de lucru din secțiunea 24.3;
- comenzile pentru teste și verificări;
- lista lucrurilor interzise: secrete în cod, dependențe noi fără justificare, apeluri la modele în afara gateway-ului, efecte externe în afara executorului, cod fără teste, schimbări în afara pasului;
- locul în care se găsește specificația pasului curent.

Pentru agenții care caută un alt nume de fișier se adaugă un fișier scurt care trimite la acesta.

### 24.3 Regulile unei sesiuni de cod

1. Citește fișierul de reguli, specificația pasului și deciziile legate de el.
2. Spune ce a înțeles și ce presupuneri face. Întreabă doar dacă lipsește ceva esențial.
3. Scrie întâi testele de acceptare din „Gata când”.
4. Scrie codul minim care trece testele.
5. Rulează toate testele și verificările. Raportează exact ce a rulat și ce a ieșit.
6. Actualizează documentația atinsă și jurnalul de schimbări.
7. Deschide cererea de integrare, cu descrierea completată.
8. Nu atinge nimic în afara pasului. Ce observă în plus notează ca propunere.

Agentul nu declară un pas „gata” fără dovada testelor rulate. Dacă nu a putut rula ceva, o spune.

### 24.4 Doi ochi diferiți

- Un model scrie, alt model revizuiește. Dacă Opus scrie pasul, modelul GPT face revizuirea, și invers.
- Revizorul primește specificația și diferența de cod, nu conversația autorului.
- Revizorul caută abateri de la specificație, cazuri-limită netestate, probleme de securitate și complexitate inutilă.
- Aprobi integrarea doar când CI este verde și revizorul nu are obiecții deschise.
- Pentru modulele sensibile (autentificare, izolare, executorul de efecte, reclame, facturare), revizuirea este obligatorie.

### 24.5 Specificația unui pas

- Fiecare pas are un fișier scurt, scris înainte de sesiune, după șablonul Ș5 din secțiunea 27.2.
- Conține: context, ce se construiește, ce nu se construiește, contracte de date, teste de acceptare, riscuri, fișiere atinse.
- Specificația o poate redacta Claude, din acest document, într-o sesiune separată de cea de cod. Tu o citești și o aprobi.

### 24.6 Decizii de arhitectură

- O decizie nouă sau schimbată se scrie într-un fișier: context, opțiuni, alegere, consecințe.
- Agentul de cod nu schimbă o decizie din proprie inițiativă. El propune, iar tu sau Consiliul hotărâți.
- Deciziile inițiale sunt cele 16 din secțiunea 6.7.

### 24.7 Testarea în repo

| Tip | Ce verifică | Când rulează |
| --- | --- | --- |
| Unitare | Funcții și reguli izolate | La fiecare commit |
| De contract | Fiecare conector, față de răspunsuri înregistrate, fără apeluri reale | La fiecare commit |
| De integrare | Fluxuri întregi, cu un furnizor de modele fals și determinist | La fiecare cerere de integrare |
| De izolare | Accesul între clienți este refuzat | La fiecare cerere de integrare |
| Evaluări pe seturi de aur | Calitatea prompturilor, pe modele reale | Zilnic, din capacitatea liberă, și la schimbarea unui prompt |
| De avarie | Reporniri, furnizori căzuți, disc plin | Înainte de fiecare lansare |
| De fum | Platforma pornită răspunde corect | După fiecare livrare |

CI nu consumă cote, pentru că folosește un furnizor fals. Evaluările reale rulează pe modelul local, când există un culoar liber, și pe cota găzduită rămasă, înainte de resetare.

### 24.8 Ramuri, versiuni, livrări

- Ramura principală este protejată: fără scriere directă, cu CI obligatoriu.
- Numele ramurii conține codul pasului.
- Mesajele de commit spun pe scurt ce s-a schimbat și de ce.
- Fiecare livrare în producție are o etichetă de versiune și o intrare în jurnalul de schimbări.
- Migrările sunt compatibile cu versiunea anterioară. Ștergerea unei coloane se face în doi pași, în versiuni diferite.

### 24.9 O zi de lucru pentru tine

1. Alegi pasul următor din plan.
2. Ceri specificația pasului (șablonul Ș8) sau o iei din repo, dacă există.
3. Pornești sesiunea de cod, cu instrucțiunea standard (șablonul Ș6).
4. Citești raportul sesiunii. Verifici „Gata când” pe staging, de pe telefon, cu lista Ș10.
5. Pornești revizuirea cu celălalt model (șablonul Ș7).
6. Aprobi integrarea. Promovezi din panou când vrei.
7. Notezi în fișierul de decizii orice hotărâre luată pe parcurs.

### 24.10 Capcane cunoscute la lucrul cu agenți de cod

- **Pași prea mari.** Un pas care atinge mai mult de un modul se împarte.
- **„La mine merge.”** Contează doar CI și staging.
- **Teste slăbite ca să treacă.** Revizorul verifică dacă testele chiar testează criteriul.
- **Cod demonstrativ prezentat ca final.** Orice parte nefuncțională se marchează explicit și apare în raport.
- **Dependențe adăugate din comoditate.** Fiecare dependență nouă cere justificare în cererea de integrare.
- **Context pierdut între sesiuni.** Tot ce contează stă în repo, nu în conversație.
