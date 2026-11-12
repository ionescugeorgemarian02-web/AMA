## 8. Gateway de modele și FinOps

Toate apelurile la modele trec printr-un singur serviciu. El știe ce cotă mai are fiecare furnizor, alege modelul potrivit sarcinii și refuză să degradeze în tăcere sarcinile importante.

### 8.1 Registrul de furnizori și modele

Fiecare intrare conține:

- furnizorul, adresa și o referință la cheie (cheia stă în secrete, nu în baza de date);
- modelele oferite și capacitățile lor: ieșire JSON, unelte, imagini, fereastră de context, scor de calitate în română;
- limitele: cereri pe minut și pe zi, tokeni pe minut și pe zi, ora de resetare;
- condițiile de folosire: uz comercial permis, date folosite la antrenare, restricții regionale;
- starea de sănătate: rata de erori și latența din ultima oră.

Registrul se editează din panou. Un furnizor fără uz comercial permis nu poate fi activat pentru producția clienților.

### 8.2 Profiluri de sarcină

| Profil | Exemple | Nivel | Când lipsește cota |
| --- | --- | --- | --- |
| Clasificare și extragere | Intenția unui comentariu, extragerea afirmațiilor | T1 | Model local |
| Rescriere și adaptare | Adaptare pe canal, editare | T2 | Alt furnizor T2, apoi local, cu o verificare în plus |
| Creație | Hook-uri, scripturi, postări | T2–T3 | Alt furnizor; altfel amânare |
| Judecată | Validatori cu rubrică | T2, alt model decât autorul | Alt furnizor; altfel amânare |
| Strategie și sinteză | Strategie, brief de insight, plan media | T3 | Amânare; niciodată un model mai slab |
| Consiliu | Decizii lunare și escaladări | T4 | Amânare, sau T3 cu eticheta „provizoriu” |

### 8.3 Cum se alege modelul pentru un apel

1. Sarcina declară profilul, schema de ieșire și prioritatea.
2. Gateway-ul păstrează doar modelele cu capacitățile cerute și cu condiții de folosire potrivite.
3. Elimină modelele fără cotă rămasă sau cu sănătate proastă.
4. Ordonează restul după scorul de calitate pe acel profil, apoi după cota rămasă.
5. Rezervă cota înainte de apel și o confirmă după.
6. La eșec, urmează lanțul de rezervă al profilului.

### 8.4 Limitatoare de cotă

- Există un contor pentru fiecare pereche furnizor–model și pentru fiecare tip de limită.
- Contoarele stau în Postgres, deci supraviețuiesc repornirilor.
- Gateway-ul citește antetele de limită din răspunsuri și se corectează după ele.
- Se păstrează o rezervă de siguranță de 10% din fiecare limită zilnică.
- Nu se folosesc conturi multiple la același furnizor pentru a înmulți cota. Furnizorii aplică limita global și pot închide conturile.

### 8.5 Bugete și priorități

- Bugete zilnice de apeluri pe client, pe campanie și pe livrabil.
- P0 și P1 au cotă garantată. P2 primește ce rămâne. P3 rulează pe modelul local oricând există un culoar liber și pe cota găzduită nefolosită, înainte de resetare.
- Când un client își epuizează bugetul zilnic, munca lui P2 și P3 se amână. P0 continuă.
- **Preț-umbră.** Fiecare apel gratuit este notat cu cât ar fi costat la un furnizor plătit. Așa vezi costul real per livrabil și știi când merită să plătești.

### 8.6 Ieșiri structurate

- Fiecare apel are o schemă de ieșire. Răspunsul se validează înainte să ajungă la componentă.
- La schemă invalidă: o cerere de reparație cu eroarea exactă, apoi alt model.
- Pe modelul local se folosește decodare constrânsă de gramatică, care garantează forma.
- Câmpuri obligatorii în orice ieșire: rezultat, dovezi, încredere, versiunea promptului.

### 8.7 Cache

- Cache exact pentru sarcini repetabile (clasificări, extrageri): aceeași intrare, același model, același prompt.
- Fără cache pentru creație.
- Fără cache semantic în versiunea 1: câștig mic, risc de răspunsuri nepotrivite.

### 8.8 Registrul de prompturi și jurnalul de apeluri

- Fiecare prompt este un fișier versionat în repo și o intrare în bază: nume, versiune, profil, schemă, scor pe setul de aur.
- Stările unui prompt: ciornă, candidat, campion, retras.
- Jurnalul păstrează pentru fiecare apel: client, livrabil, componentă, versiunea promptului, model, tokeni, durată, rezultatul validării, preț-umbră.
- Conținutul complet al apelurilor se păstrează 30 de zile, apoi rămân doar metadatele. Datele personale sunt mascate înainte de salvare.

### 8.9 Protecția datelor în apeluri

- G12 maschează datele personale înainte de orice apel extern.
- Datele confidențiale ale clienților nu merg la furnizori care antrenează pe date.
- Textul adus din exterior intră în prompt ca date marcate, niciodată ca instrucțiuni.

### 8.10 Testul comparativ pe română

- Un set de 60–100 de sarcini reale în română, pe fiecare profil.
- Fiecare model disponibil rulează setul. Scorul are două părți: verificări automate și evaluare umană pe eșantion.
- Rezultatul devine scorul de calitate din registru.
- Testul se repetă lunar și la apariția unui model nou.
