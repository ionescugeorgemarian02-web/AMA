## 9. Sistemul de validare

Fiecare livrabil trece prin șase trepte de verificare, de la reguli gratuite până la om. Un singur eșec critic îl blochează, iar autorul nu este niciodată propriul judecător.

### 9.1 Cascada

| Treaptă | Ce verifică | Cost | Exemple |
| --- | --- | --- | --- |
| V0 Structură | Formă și completitudine | Zero | Schemă, lungimi, limbă, linkuri funcționale |
| V1 Reguli | Liste și calcule | Zero | Termeni interziși, prețuri față de registru, numărul de apeluri la acțiune, diacritice, lizibilitate |
| V2 Similaritate | Vectori de text | Local | Apropierea de tonul brandului, aproape-duplicate, noutate |
| V3 Judecători mici | Rubrici cu criterii da sau nu | T1–T2 | Hook clar, ton potrivit, promisiuni nepermise |
| V4 Judecător puternic | Cazuri cu miză mare | T3 | Reclame, nișe sensibile, pagini de vânzare |
| V5 Om | Aprobare și audit pe eșantion | Timp | După nivelul de autonomie |

Treptele rulează în ordine. Un eșec critic oprește cascada, ca să nu consume cotă inutil.

### 9.2 Forma unui verdict

Fiecare validator întoarce: identitatea și versiunea lui, verdictul (trece, avertisment sau eșec), severitatea, scorul, dovezile (fragmentul exact și regula încălcată), instrucțiunea de corectare și costul.

- Un eșec critic blochează livrabilul.
- Avertismentele se adună. Peste un prag, livrabilul merge la om.
- Instrucțiunile de corectare ale tuturor validatorilor se unesc într-un singur mesaj pentru autor.

### 9.3 Registrul de fapte: mecanismul anti-halucinații

- Fiecare client are un registru de fapte aprobate: prețuri, caracteristici, garanții, program, adrese, mențiuni legale. Fiecare fapt are sursă și perioadă de valabilitate.
- Autorii primesc faptele ca date structurate și au interdicție să introducă altele.
- G2 extrage din text toate afirmațiile verificabile: cifre, prețuri, termene, superlative, comparații, promisiuni.
- Fiecare afirmație trebuie să corespundă unui fapt din registru sau unei surse de cercetare citate. Cifrele și prețurile se compară exact, fără LLM.
- O afirmație neacoperită blochează livrabilul. Platforma nu „verifică pe internet” în locul registrului.
- Dacă lipsește un fapt necesar, livrabilul se oprește cu o întrebare către client, nu cu o presupunere.

### 9.4 Validatorii, pe scurt

| Validator | Trepte | Blochează când |
| --- | --- | --- |
| G1 Structură | V0 | Lipsește un câmp, lungimea depășește limita canalului sau limba este greșită |
| G2 Fapte | V1, V3 | Există o afirmație fără acoperire sau o cifră diferită de registru |
| G3 Politici | V1, V3 | Apare un termen interzis sau o promisiune nepermisă pe acea platformă |
| G4 Ton | V2, V3 | Similaritatea cu exemplele aprobate este sub prag și rubrica o confirmă |
| G5 Vizual | V0, V1 | Logo lipsă sau deformat, culori în afara paletei, text în afara zonei sigure, contrast slab |
| G6 Media | V0, V1 | Format greșit, cadre negre sau înghețate, tăcere, sunet prea tare, desincronizare, subtitrări tăiate |
| G7 Originalitate și drepturi | V1, V2 | Suprapunere mare cu o sursă sau activ fără licență înregistrată |
| G8 Lizibilitate și conversie | V1, V3 | Hook slab, mai multe apeluri la acțiune, text greu de citit |
| G9 Juridic | V1, V4 | Reducere fără preț de referință, promisiune de rezultat, mențiune obligatorie lipsă |
| G10 Limbă | V1, V3 | Diacritice lipsă, greșeli de acord, registru nepotrivit |
| G11 Dezvăluire AI | V1 | Activ generat fără etichetă stabilită pentru canal |
| G12 Date personale | V1 | Nume, telefon, email sau alt identificator care nu are ce căuta în text |
| G13 Injecții | V1 | Text extern care încearcă să dea instrucțiuni sau cerere de unealtă nepermisă |

### 9.5 Controlul tehnic media, în detaliu

- **Format:** 1080×1920 pentru vertical, 30 de cadre pe secundă, H.264, AAC, dimensiune sub limita canalului.
- **Imagine:** fără cadre negre mai lungi de 0,5 secunde și fără cadre înghețate mai lungi de 2 secunde, în afara celor intenționate.
- **Sunet:** nivel integrat în jur de −14 LUFS, vârf sub −1 dBTP, fără tăceri mai lungi de 1,5 secunde.
- **Sincronizare:** sub 100 ms diferență între durata sunetului și a imaginii.
- **Subtitrări:** în zona sigură a fiecărei platforme, verificate prin OCR pe cadre-eșantion, fără cuvinte tăiate.
- **Voce:** narațiunea se transcrie înapoi și se compară cu scriptul. Peste pragul de erori, fraza se resintetizează.
- **Miniaturi:** contrast suficient între text și fundal.

Pragurile sunt valori de pornire \[I\] și se calibrează pe colecția de clipuri defecte.

### 9.6 Judecători în care poți avea încredere

- **Rubrici clare.** Criterii da sau nu, cu cerință de dovadă. Fără note vagi de la 1 la 10.
- **Independență.** Model diferit de al autorului, de preferat de la alt furnizor.
- **Calibrare.** Fiecare judecător este comparat cu etichete umane pe un set de aur. Țintă de acord: cel puțin 85%.
- **Audit continuu.** G14 trimite săptămânal un eșantion la om. Diferențele devin exemple noi în setul de aur.
- **Derivă.** Dacă rata de trecere a unui judecător se schimbă brusc fără o schimbare de prompt, primești alertă.

### 9.7 Pachete de reguli

- Regulile stau în fișiere versionate: pe platformă, pe nișă și pe client.
- O regulă are identificator, text, tip de potrivire, severitate, sursă (politica platformei sau legea) și data ultimei verificări.
- Regulile se schimbă doar prin revizuire umană. Optimizatorul nu are drept de scriere asupra lor.
- Fiecare regulă are cel puțin un exemplu care trebuie blocat și unul care trebuie să treacă.

### 9.8 Carantină și contestație

- Un livrabil blocat critic intră în carantină, cu dovezile vizibile.
- Poți marca un verdict drept greșit. Marcajul intră în setul de aur și în statistica validatorului.
- Niciun livrabil din carantină nu se publică fără o decizie umană înregistrată.

### 9.9 Ținte de calitate \[I\]

| Indicator | Țintă |
| --- | --- |
| Materiale intenționat greșite, blocate pe setul de test | Cel puțin 95% |
| Materiale bune blocate pe nedrept | Cel mult 10% |
| Acord între judecător și om | Cel puțin 85% |
| Livrabile care trec din prima sau după o reparație | Cel puțin 80% |
| Incidente critice ajunse la publicare | Zero |
