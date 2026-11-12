## 7. Orchestrare, mașina de stări și rolul lui Claude

Fiecare livrabil parcurge o mașină de stări cu tranziții permise, limite de reîncercare și porți de aprobare. Nimic nu se rotește la infinit și nimic nu pleacă în exterior de două ori.

### 7.1 Trei niveluri de stare

- **Client:** onboarding, activ, suspendat, închis.
- **Campanie:** descoperire, strategie propusă, strategie aprobată, producție, live, revizuire. Din revizuire: continuă, pivotează, pauză sau oprire.
- **Livrabil:** o postare, un articol, un video, o reclamă. Stările sunt mai jos.

### 7.2 Stările unui livrabil

| Stare | Ce se întâmplă | Cine o mută mai departe |
| --- | --- | --- |
| Planificat | Există în calendar, cu termen și canal | D3, A4 |
| Briefat | Are brief și pachet de context | D5 |
| În scriere | Autorul produce variante | E1–E6 |
| În validare | Rulează cascada de validatori | G1–G13 |
| În reparație | Autorul primește instrucțiuni de corectare; cel mult 2 runde | E, apoi G |
| Validat | A trecut toate verificările | B1 |
| Așteaptă aprobare | Doar dacă nivelul de autonomie o cere | Biroul de aprobări (componenta L2): tu sau clientul |
| Aprobat | Poate intra în producția media sau în programare | B1 |
| În randare | Voce, imagini, video | F3–F7 |
| Control media | Verificări tehnice pe fișierul final | G5, G6, G11 |
| Gata | Pachet complet pentru fiecare canal | H1 |
| Programat | Are slot de publicare | B4 |
| În publicare | Executorul trimite spre platformă | B7 |
| Publicat | Are identificator și link de la platformă | K1 |
| În măsurare | Metrici la 1 oră, 24 de ore, 72 de ore, 7 și 28 de zile | K1, K2 |
| Închis | Rezultatele au intrat în învățare | K8 |

Stări de excepție: respins (de om, cu motiv), carantină (blocat de un validator critic), eșec temporar (se reîncearcă), coada de erori (cere intervenție), anulat, expirat (slotul a trecut fără aprobare).

### 7.3 Reguli care previn buclele și dublurile

- **Tranziții permise.** Există un tabel de tranziții. Orice altă tranziție este refuzată și înregistrată.
- **Reparații limitate.** Cel mult 2 runde per livrabil. A treia încercare merge la om, cu diagnostic.
- **Buget per livrabil.** Număr maxim de apeluri LLM și timp maxim. La depășire: oprire și escaladare.
- **Predări limitate.** Cel mult 12 predări între componente pentru un livrabil.
- **Întrerupător global.** Dacă rata de eșec depășește 30% într-o oră, producția nouă se oprește și primești alertă.
- **Idempotență.** Fiecare efect extern are o cheie formată din client, livrabil, canal și versiune. După o eroare, executorul verifică la platformă dacă postarea există deja, înainte să reîncerce.
- **Fără aprobare automată.** O aprobare care întârzie nu devine aprobare. Livrabilul expiră și se reprogramează.

### 7.4 Niveluri de autonomie

| Nivel | Ce face platforma singură | Ce rămâne la om |
| --- | --- | --- |
| L0 Umbră | Produce, dar nu publică nimic | Totul; folosit la testare |
| L1 Aprobare totală | Produce și programează | Fiecare livrabil se aprobă |
| L2 Aprobare prin excepție | Publică singură ce trece toate verificările peste prag | Excepțiile și un eșantion de 10–20% |
| L3 Autonom cu plafon | În plus: răspunsuri în inbox și ajustări de reclame în limitele aprobate | Un eșantion de 5–10% și alertele |
| L4 Autonom în perimetru | Strategul poate schimba planul în perimetrul contractului | Rapoarte, alerte, decizii de buget |

- Nivelul se setează separat pe client și pe cinci clase de acțiuni: publicare de conținut, răspuns în inbox, schimbare de reclame, schimbare de strategie, cheltuială.
- Promovare de la L1 la L2: pe ultimele 30 de livrabile, rată de aprobare din prima de cel puțin 90% și zero incidente critice. Pe conturile unui client se cere și acordul lui, dat în portal (secțiunea 19.4).
- Retrogradare automată cu un nivel la orice incident critic.
- Cheltuiala nu trece peste plafoanele din contract, la niciun nivel.
- TikTok rămâne la L1 cât timp regulile lor cer consimțământ per postare.

### 7.5 Cozi, priorități și reîncercări

| Coadă | Ce trece prin ea | Limită |
| --- | --- | --- |
| Câte una pe furnizor de modele | Apelurile către acel furnizor | Limita de rată a furnizorului |
| Greu | Randare, voce, transcriere, OCR, generare pe modelul local | Câte un job pe culoar; 2 culoare la 8 nuclee |
| Intrări și ieșiri | Conectori, crawl, email | 24 în paralel, cu limite pe platformă |
| Învățare | Optimizări, evaluări, consolidarea memoriei | Pe modelul local, când există un culoar liber; pe cota găzduită, doar din ce rămâne înainte de resetare |
| Urgent | Opriri, alerte, corecturi | Fără așteptare |

Priorități: P0 este termenul de client din următoarele 24 de ore. P1 este producția programată. P2 este cercetarea și raportarea. P3 este învățarea. În aceeași prioritate, câștigă termenul cel mai apropiat.

| Tip de eroare | Reacție |
| --- | --- |
| Limită de rată | Așteaptă până la resetare sau trece pe alt furnizor |
| Eroare de server | 3 reîncercări cu pauză crescătoare, apoi alt furnizor |
| Ieșire care nu respectă schema | O reparație, apoi alt model |
| Validator care respinge | Buclă de reparație, cel mult 2 runde, apoi om |
| Eroare de autentificare la un conector | Pauză pe conector și cerere de reautorizare |
| Job care eșuează repetat | Coada de erori, cu context complet |

### 7.6 Rolul lui Claude: Consiliu și Strateg

- **Ce face Consiliul:** revizuirea lunară a strategiei pe fiecare client, deciziile de pivot, al doilea aviz pe schimbările de prompturi propuse de optimizator, analiza după incidente, brieful campaniilor mari și verdictul final pe un număr limitat de reclame cu miză mare.
- **Ce nu face:** nu scrie fiecare postare, nu validează fiecare livrabil și nu stă în calea publicării.
- **Dosarul de Consiliu:** platforma pregătește un document cu cifre, context, opțiuni și întrebări precise. Consiliul întoarce o decizie structurată: alegerea, motivele, condițiile și ce se măsoară.
- **Buget:** fiecare apel are motiv și valoare așteptată. Există plafon lunar. Când se atinge, sarcinile se amână sau trec la T3.

| Mod de conectare | Cum funcționează | Plan | Observații |
| --- | --- | --- | --- |
| Manual asistat | Deschizi dosarul în Claude, pe telefon. Răspunsul se importă în platformă. | Pro | Cel mai robust; consum mic |
| Conector către platformă | Claude citește dosarele și scrie deciziile direct, printr-un conector personalizat | De verificat pe planul tău | Elimină copierea; cere autentificare sigură |
| Fără interfață, pe VPS | Claude Code rulează programat, logat cu abonamentul | Pro sau mai sus | Consumă din limitele planului \[V\]; trebuie să tolereze eșecul |
| API cu credit lunar | Gateway-ul apelează Claude API cu cheia organizației legate | Max: 100 USD; Ultra: 200 USD \[V\] | Cel mai curat mod programatic; la epuizare se oprește, nu taxează |

Recomandare: începi cu modul manual asistat. Treci la API cu credit lunar când venitul justifică planul Max.

### 7.7 Strategul: când oprește și schimbă direcția

- **Totul pornește cu criterii.** Fiecare strategie are din start ipoteza, indicatorul principal, pragul minim, fereastra de măsurare și criteriul de oprire.
- **Cadență.** Revizuire săptămânală automată, cu T3. Revizuire lunară de Consiliu, cu T4.
- **Patru ieșiri.** Continuă, ajustează, pivotează, oprește.
- **Pivot disciplinat.** Strategul scrie trei ipoteze alternative, fiecare cu dovezi și cost. Alege una, o testează pe 20% din volum și abia apoi mută restul.
- **Urmă scrisă.** Fiecare decizie se salvează ca înregistrare de decizie: ce s-a văzut, ce s-a decis, ce se așteaptă și când se verifică.
- **Fără decizii pe date puține.** Sub pragul minim de afișări sau de cheltuială, verdictul este „așteaptă”.

### 7.8 Butoane de oprire

- Oprirea globală a publicării.
- Oprirea pe un client.
- Oprirea tuturor reclamelor.
- Înghețarea învățării: nicio promovare nouă.
- Oprirea apelurilor plătite, dacă vor exista.

Fiecare buton stă pe prima pagină a panoului și are o comandă echivalentă în Telegram.
