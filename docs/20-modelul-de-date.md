## 20. Modelul de date

Modelul are 13 grupuri de entități. Fiecare rând poartă identificatorul clientului, iar baza de date refuză singură accesul între clienți.

### 20.1 Reguli generale

- Fiecare tabel cu date de client are coloana de client și o politică de securitate la nivel de rând.
- Identificatorii sunt unici, ordonați în timp și generați de aplicație.
- Prompturile, briefurile, ieșirile, strategiile, regulile și Creierul de brand au versiuni care nu se modifică. O schimbare creează o versiune nouă.
- Ștergerea este întâi logică, apoi reală, după termenul din politica de păstrare.
- Jurnalul de evenimente acceptă doar adăugări: cine, ce, când, pe ce obiect, cu ce identificator de corelare.
- Efectele externe trec printr-un tabel „de trimis”, cu cheie de idempotență și stare.
- Câmpurile flexibile stau în JSON validat de scheme. Câmpurile după care se caută sunt coloane.
- Secretele nu stau în clar în tabele. Tokenurile sunt criptate cu o cheie păstrată în afara bazei.

### 20.2 Entitățile

| Grup | Entități | Câmpuri și legături importante |
| --- | --- | --- |
| Conturi și acces | Client, utilizator, rol, sesiune, cheie API, invitație | Clientul are pachet, stare, matrice de autonomie și plafoane |
| Creierul de brand | Profil de brand, fapt, ofertă, identitate vizuală, exemplu, intrare de playbook, insight, constrângere | Toate versionate; faptul are sursă și valabilitate; lecția are contoare |
| Cercetare | Sursă, document colectat, fapt extras, fișă de tendință, concurent, reclamă observată, brief de insight | Fiecare fapt extras trimite la document și la citat |
| Planificare | Campanie, strategie, înregistrare de decizie, pilon de conținut, intrare de calendar, experiment, variantă | Strategia are ipoteză, indicator, prag și criteriu de oprire |
| Producție | Livrabil, brief, versiune de ieșire, tranziție de stare, cerere de aprobare, decizie umană | Livrabilul are tip, canal, stare, termen și buget; decizia are motiv |
| Validare | Regulă, pachet de reguli, verdict, element de set de aur, contestație | Verdictul trimite la versiunea de ieșire și la regula încălcată |
| Media | Activ, licență, pașaport de proveniență, profil de voce, șablon, listă de decizii de montaj, job de randare | Activul are hash, tip, sursă, licență și etichetă AI |
| Publicare | Conector, autorizare, pachet de publicare, publicare, efect extern de trimis | Publicarea are identificatorul și linkul de pe platformă |
| Reclame | Cont de reclame, plan media, campanie, set de reclame, reclamă, propunere de schimbare, regulă de buget, anomalie | Propunerea păstrează starea de dinainte și de după |
| CRM | Firmă, contact, consimțământ, lead, oportunitate, activitate, conversație, mesaj, programare | Contactul are sursă și temei; mesajul are fereastra de răspuns |
| Analiză și învățare | Metrică, citire de metrici, curbă de retenție, rezultat de experiment, starea alegerii adaptive, rulare de optimizare, model, promovare | Metrica trimite la publicare; promovarea trimite la campion și la candidat |
| Inteligență și operare | Furnizor, model, contor de cotă, prompt, versiune de prompt, apel la model, pas de execuție, job, incident, înregistrare de audit, comutator de funcție, backup | Apelul la model trimite la livrabil, componentă și versiunea promptului |
| Finanțe | Plan, abonament, factură, plată, eveniment de plată | Abonamentul leagă clientul de plan și de starea plății |

### 20.3 Legăturile care contează

- Client → campanii → livrabile → versiuni de ieșire → verdicte și decizii → publicări → metrici.
- Livrabil → brief → pachet de context → faptele și exemplele folosite.
- Livrabil video → listă de decizii de montaj → active → licențe.
- Metrică → publicare → livrabil → hook, format, slot → starea alegerii adaptive.
- Promovare → rulare de optimizare → set de aur → versiune de prompt.

Cu aceste lanțuri poți răspunde la orice „de ce”: de ce s-a publicat un material, din ce fapte, cu ce model, cine a aprobat și ce a ieșit.

### 20.4 Păstrarea datelor \[I\]

| Tip de date | Păstrare |
| --- | --- |
| Conținutul complet al apelurilor la modele | 30 de zile, apoi doar metadate |
| Livrabilele și versiunile lor | Pe durata contractului plus 12 luni |
| Fișiere media finale | 90 de zile local, apoi arhivă sau ștergere |
| Fișiere media intermediare | 7 zile |
| Documente colectate din exterior | 90 de zile |
| Mesaje din inbox | 12 luni |
| Lead-uri fără activitate | 24 de luni, apoi ștergere sau anonimizare |
| Jurnalul de audit | 5 ani |
| Datele unui client plecat | Export la cerere, apoi ștergere în 30 de zile |

Termenele se confirmă cu avocatul și se scriu în politica de confidențialitate.

### 20.5 Dimensiuni estimate \[I\]

- Baza de date: câțiva GB în primul an, la 10 clienți. Cel mai mare tabel este cel al apelurilor la modele.
- Curățarea automată lunară ține dimensiunea sub control.
- Indexuri pe client, stare, termen și identificator de corelare.
