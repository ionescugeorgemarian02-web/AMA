## 11. Sistemul de învățare autonomă

Platforma învață pe nouă trepte, de la jurnalizare la decizii de strategie. Fiecare treaptă pornește doar când există destule date. Nimic învățat nu ajunge în producție fără să bată varianta curentă și fără să treacă toate verificările de conformitate.

### 11.1 Ce înseamnă „învățare” aici

- Nu se antrenează modelele mari. Se îmbunătățesc prompturile, exemplele, playbook-urile, alegerile dintre variante, modelele mici de predicție și strategia.
- Semnalul vine din trei surse: verdictele validatorilor, deciziile oamenilor (aprobări, respingeri, editări) și rezultatele reale de pe platforme.
- La început, semnalul uman este cel mai valoros. Rezultatele reale devin utile când crește volumul.

### 11.2 Treptele

| Treaptă | Ce învață | Tehnică | Date minime | Fază |
| --- | --- | --- | --- | --- |
| N0 Urme complete | Nimic încă; înregistrează tot | Jurnal de apeluri, pași, verdicte, decizii și rezultate | – | F2–F3 |
| N1 Seturi de aur și evaluări | Dacă o schimbare este mai bună sau mai rea | 30–100 de exemple etichetate per componentă; test de regresie | 30 de exemple | F5 |
| N2 Feedback uman | Ce respinge și ce editează omul | Motive structurate de respingere; diferența dintre ciornă și versiunea editată devine exemplu | Prima respingere | F5–F6 |
| N3 Playbook evolutiv | Lecții scurte, pe agent, nișă și client | Metoda ACE: generator, reflector, curator; actualizări mici, numerotate | 20 de livrabile închise | F11 |
| N4 Alegere adaptivă | Ce hook, format, unghi și slot să folosească mai des | Bandiți cu eșantionare Thompson și explorare minimă garantată | 10 publicări per variantă | F11 |
| N5 Optimizare de prompturi | Instrucțiuni mai bune pentru fiecare agent | GEPA și MIPROv2 din DSPy, rulate offline | 50 de exemple cu scor | F14 |
| N6 Predicție | Șansa de succes înainte de publicare; scor de lead; risc de plecare | Gradient boosting pe trăsături de text, format și context | 500–1.000 de publicări pe canal | F14 |
| N7 Experimente formale | Răspunsuri cauzale la întrebări precise | Teste A/B cu ipoteză, indicator și regulă de oprire declarate dinainte | După volum | F14 |
| N8 Strategie care se corectează | Ce direcție merită continuată | Revizuire săptămânală și lunară, cu înregistrări de decizie | O lună de date | F13 |

Nu intră în plan căutarea automată de arhitecturi de agenți și antrenarea continuă a modelelor mari. Cer mult calcul și seturi de evaluare mature. Ajustarea fină a modelului local pe textele aprobate devine o opțiune după câteva mii de exemple și cere GPU o singură dată.

### 11.3 N3 în detaliu: playbook-ul evolutiv

- **Forma.** Fiecare lecție este un rând scurt, cu identificator, domeniu (agent, nișă, client, canal), text, dovezi și două contoare: de câte ori a ajutat și de câte ori a dăunat.
- **Generatorul** este agentul care lucrează. El notează ce lecții a folosit.
- **Reflectorul** compară rezultatul cu verdictele, cu editările omului și cu cifrele. Propune lecții noi sau modifică contoarele.
- **Curatorul** (K8) aplică schimbări mici: adaugă, unește, retrage. Nu rescrie tot playbook-ul.
- **De ce această metodă.** Actualizările mici costă puține apeluri, deci încap în cotele gratuite. Playbook-ul rămâne lizibil pentru tine.
- **Limite.** Cel mult 40 de lecții active per domeniu. Lecțiile la care „a dăunat” depășește „a ajutat” se retrag automat.
- **Control.** Lecțiile care ating conformitatea, prețurile sau promisiunile cer aprobarea ta.

Exemplu de lecție, inventat pentru ilustrare: „La saloane, primele trei secunde arată rezultatul, nu procedura. A ajutat: 9. A dăunat: 1.”

### 11.4 N4 în detaliu: alegerea adaptivă

- **Variantele.** Tipare de hook, formate video, unghiuri de mesaj, sloturi de publicare, variante de miniatură.
- **Recompensa.** La video: rata de vizionare până la capăt sau durata medie raportată la lungime. La postări: interacțiuni raportate la afișări. La reclame: costul per rezultat.
- **Întârziere.** Recompensa se citește la 72 de ore pentru conținutul organic și după pragul minim de cheltuială la reclame.
- **Explorare.** Cel puțin 15% din publicări merg pe variante mai puțin testate.
- **Pornire la rece.** Un client nou pornește cu mediile nișei, nu de la zero.
- **Schimbarea în timp.** Rezultatele vechi cântăresc mai puțin, pe o fereastră de 90 de zile.
- **Simplitate.** Algoritmul are câteva zeci de linii și nu cere o bibliotecă specializată.

### 11.5 N5 în detaliu: optimizarea de prompturi

1. Se aleg componenta și setul ei de aur, împărțit în antrenare și test.
2. Optimizatorul rulează offline, pe cota găzduită rămasă înainte de resetare sau pe creditul API al lui Claude. Evaluările candidatului pot rula pe modelul local, pentru componentele de nivel T1.
3. Produce un candidat și un raport: ce a schimbat și de ce.
4. Candidatul trebuie să bată campionul pe setul de test cu o marjă stabilită și să nu piardă nimic la conformitate.
5. Consiliul sau tu citiți raportul.
6. Candidatul rulează în umbră pe 20 de livrabile reale: produce, dar rezultatul nu se folosește.
7. Trece în producție pe 10% din trafic, apoi pe 90%. Restul de 10% rămâne pe campionul vechi, ca grup de control, până se măsoară câștigul real (secțiunea 11.6).
8. Campionul vechi rămâne disponibil pentru revenire dintr-o atingere.

### 11.6 Constituția: ce nu are voie învățarea să atingă

1. **Validatorii sunt în afara ei.** Regulile, pragurile de siguranță și registrul de fapte nu pot fi modificate de niciun optimizator.
2. **Obiectiv compus.** Performanța contează doar înmulțită cu rata de conformitate și cu scorul de brand. O scădere la conformitate respinge candidatul.
3. **Indicatori de gardă.** Lângă indicatorul principal se urmăresc ascunderile, dezabonările, comentariile negative și reclamațiile. Dacă urcă, „îmbunătățirea” se anulează.
4. **O schimbare o dată.** Cel mult o promovare pe săptămână per componentă, ca efectul să poată fi atribuit.
5. **Grup de control.** 10% din trafic rămâne pe varianta stabilă, pentru a măsura câștigul real.
6. **Date curate.** Semnalul vine doar din API-urile oficiale. Vârfurile anormale și traficul suspect se exclud.
7. **Izolare.** Datele unui client nu antrenează nimic pentru alt client, în afara tiparelor agregate din contract.
8. **Reversibilitate.** Orice promovare se poate anula dintr-o atingere și lasă urmă în jurnal.
9. **Înghețare.** Butonul de înghețare oprește toate promovările până îl dezactivezi.

### 11.7 Ce vezi în panou

- Registrul de experimente: ipoteză, stare, rezultat.
- Starea alegerii adaptive pe fiecare client și canal.
- Lecțiile noi care așteaptă curatoriere.
- Rulările optimizatorului, cu rapoarte și comparația dintre campion și candidat.
- Istoricul promovărilor și al revenirilor.
- Scorurile pe seturile de aur, în timp, per componentă.

### 11.8 Așteptări realiste

- În prima lună, învățarea vine aproape numai din feedbackul tău și al clienților. Este normal.
- Alegerea adaptivă dă semnal util după 6–8 săptămâni de publicare constantă pe un canal \[I\].
- Modelele predictive nu au sens înainte de câteva sute de publicări pe canal.
- Un sistem care „învață” fără set de test doar se schimbă. De aceea N1 vine înaintea tuturor celorlalte trepte.
