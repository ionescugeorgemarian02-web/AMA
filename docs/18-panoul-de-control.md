## 18. Panoul de control

Panoul are 18 ecrane gândite întâi pentru telefon. Primele patru (Acasă, Aprobări, Producție, Alerte) acoperă munca zilnică. Restul sunt pentru configurare și diagnostic.

### 18.1 Principii de interfață

- Aplicație web instalabilă pe ecranul principal al telefonului, cu notificări push.
- Bară de jos cu cinci file: Acasă, Aprobări, Producție, Alerte, Meniu. Orice acțiune zilnică se face cu o mână.
- Fiecare cifră duce, la atingere, spre lista din care provine.
- Fiecare decizie automată are un „de ce”: pașii, verdictele și contextul trimis modelului.
- Acțiunile periculoase cer confirmare și lasă urmă în jurnalul de audit.
- Telegram este canalul de rezervă: alerte, aprobări simple și butoanele de oprire.

### 18.2 Ecranele

| Ecran | Ce arată | Ce poți face |
| --- | --- | --- |
| 1 Acasă | Starea sistemului, producția zilei, aprobările în așteptare, cotele rămase, alertele | Butoanele de oprire; salt spre orice problemă |
| 2 Aprobări | Coada de livrabile, cu previzualizare, verdictele validatorilor și diferențele față de versiunea anterioară | Aprobi, respingi cu motiv, editezi, aprobi în grup |
| 3 Producție | Fiecare livrabil pe etape, cu timpi și reîncercări | Reiei un pas, anulezi, deschizi urma completă |
| 4 Alerte | Incidentele pe severitate, cu starea lor | Preiei, rezolvi, amâni |
| 5 Clienți | Lista clienților, scorul de sănătate, pachetul, nivelul de autonomie, starea conectorilor | Schimbi autonomia, suspenzi, deschizi Creierul de brand |
| 6 Creierul de brand | Profilul, registrul de fapte, ofertele, identitatea, exemplele, playbook-ul | Editezi, aprobi versiuni, exporți |
| 7 Campanii | Tablă pe stări; în detaliu: strategia, arborele de indicatori, experimentele, deciziile | Aprobi strategia, ceri pivot, închizi |
| 8 Calendar | Postările programate, pe client și canal | Muți, blochezi zile, pui pauză de criză |
| 9 Agenți | Catalogul: versiunea promptului, modelul, scorul pe setul de aur, rata de trecere, prețul-umbră | Activezi, dezactivezi, revii la o versiune |
| 10 Validatoare | Pachetele de reguli, pragurile, verdictele contestate, statistica de acord | Editezi reguli, revizuiești contestații |
| 11 Modele și cote | Furnizorii, sănătatea lor, cota folosită și rămasă, consumul pe client și pe agent | Activezi furnizori, schimbi rutarea, pornești testul comparativ |
| 12 Învățare | Experimentele, starea alegerii adaptive, lecțiile de curatoriat, rulările de optimizare, promovările | Aprobi lecții, promovezi, revii, îngheți |
| 13 Media | Biblioteca de active cu licențe, profilurile de voce, șabloanele, coada de randare, eșecurile de control cu cadre | Încarci, retragi un activ, re-randezi |
| 14 Publicare | Conectorii și starea aprobărilor API, coada, eșecurile, sănătatea conturilor | Reautorizezi, treci un canal pe asistat, reîncerci |
| 15 Reclame | Conturile, plafoanele, propunerile de schimbare, regulile, anomaliile | Aprobi propuneri, editezi reguli, oprești tot |
| 16 CRM și inbox | Lead-urile pe etape, conversațiile cu răspunsuri propuse, programările | Răspunzi, preiei, califici, trimiți oferta |
| 17 Rapoarte și analiză | Indicatorii pe client, performanța pe hook, format și slot, curbele de retenție | Construiești raport, exporți |
| 18 Operare | Cozile, coada de erori, jurnalul de audit, backupurile, utilizatorii și rolurile, comutatoarele de funcții, dosarele de Consiliu | Triezi erori, rulezi o restaurare de test, gestionezi accesul |

### 18.3 Ecranul de aprobări, în detaliu

- Un card per livrabil, cu previzualizarea așa cum va apărea pe canal.
- Sub previzualizare: verdictele pe scurt, avertismentele, faptele folosite.
- Trei acțiuni mari: aprobă, cere schimbări, respinge.
- La respingere alegi un motiv dintr-o listă scurtă și, opțional, scrii o frază. Motivul intră direct în învățare.
- Editarea pe loc salvează diferența ca exemplu.
- Aprobarea în grup acoperă un lot întreg, cu excepțiile evidențiate.
- Țintă: sub un minut per postare și sub trei per video.

Motive standard de respingere: fapt greșit, ton nepotrivit, prea lung, hook slab, subiect nepotrivit, vizual slab, problemă de conformitate, altceva.

### 18.4 Urma unui livrabil

- Linia timpului, cu fiecare pas: componentă, model, versiunea promptului, durată.
- Contextul exact trimis și răspunsul primit.
- Verdictul fiecărui validator, cu dovada.
- Deciziile oamenilor.
- Rezultatele de după publicare.

Aceasta este unealta ta de diagnostic. O poți trimite agentului de cod când ceva nu merge.

### 18.5 Roluri

| Rol | Vede | Poate |
| --- | --- | --- |
| Proprietar | Tot | Tot, inclusiv butoanele de oprire, plafoanele și utilizatorii |
| Operator | Clienții alocați | Aprobă, editează, răspunde în inbox |
| Analist | Rapoartele și învățarea | Doar citire |
| Client, titular | Datele propriei firme | Aprobă, editează Creierul, stabilește plafoanele de reclame, vede facturile |
| Client, aprobator | Livrabilele | Aprobă și comentează |
| Client, vizitator | Rapoartele | Doar citire |

### 18.6 Notificări

- **Critice** (bani, cont restricționat, sistem oprit): push și Telegram, imediat, la orice oră.
- **Importante** (aprobări care expiră, canal pe pauză): push, în program.
- **Informative:** rezumat zilnic, la ora aleasă de tine.
- Fiecare tip se poate opri sau muta pe alt canal.
