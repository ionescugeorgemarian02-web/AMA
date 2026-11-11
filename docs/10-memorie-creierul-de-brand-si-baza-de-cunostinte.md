## 10. Memorie, Creierul de brand și baza de cunoștințe

Fiecare client are un „Creier de brand” cu zece compartimente. Un agent nu primește tot Creierul, ci un pachet de context construit pentru sarcina lui.

### 10.1 Compartimentele

| Compartiment | Conține | Cine îl schimbă |
| --- | --- | --- |
| Profil de brand | Poziționare, public, atribute de ton cu exemple „așa da” și „așa nu”, vocabular permis și interzis | Clientul aprobă fiecare schimbare |
| Registru de fapte | Fapte aprobate, cu sursă și valabilitate | Clientul |
| Catalog de oferte | Produse, pachete, prețuri, garanții, promoții cu date | Clientul |
| Identitate vizuală | Culori, fonturi, logo, zone sigure, șabloane | Clientul, prin F1 |
| Exemple de aur | Livrabile aprobate, pe tip și canal | Automat, la aprobare |
| Exemple negative | Livrabile respinse, cu motiv | Automat, la respingere |
| Insight de public | Citate reale, obiecții, întrebări frecvente | C4, C5 |
| Memorie de performanță | Hook-urile, unghiurile, formatele și sloturile care au mers sau nu, cu cifre | K2 |
| Playbook | Lecții scurte, numerotate, cu contor „a ajutat” și „a dăunat” | K8, cu revizuire |
| Constrângeri | Reguli juridice și de conformitate ale nișei și ale clientului | Tu |

### 10.2 Trei niveluri de cunoaștere

- **Pe client.** Tot ce este mai sus. Nu părăsește niciodată clientul.
- **Pe nișă.** Tipare anonimizate și agregate, de exemplu: „în această nișă, hook-urile cu întrebare țin mai bine privitorul”. Fără texte, nume sau cifre ale unui client anume.
- **Pe platformă.** Reguli de format și lecții generale pe canal.

Contractul cu clientul spune explicit ce se învață agregat.

### 10.3 Cum ajunge memoria la agent: pachetul de context

1. Sarcina declară ce tipuri de context îi trebuie și bugetul de tokeni.
2. Constructorul ia întotdeauna părțile relevante din profilul de brand, faptele permise pentru subiect și constrângerile.
3. Caută exemple de aur și lecții de playbook prin căutare hibridă: cuvinte-cheie plus vectori, filtrat pe tip și canal.
4. Adaugă unul sau două exemple negative apropiate, cu motivul respingerii.
5. Taie la buget, în ordinea priorității: constrângeri, fapte, ton, exemple, lecții.
6. Salvează exact ce a trimis, ca să poți vedea mai târziu de ce a ieșit un rezultat.

### 10.4 Reguli de igienă

- Fiecare intrare de memorie are proveniență: cine a creat-o, din ce și când.
- Faptele au dată de expirare. Un fapt expirat nu mai intră în context și declanșează o întrebare către client.
- La conflict între două intrări, câștigă cea aprobată mai recent de om.
- Consolidarea nocturnă unește duplicatele, rezumă și scoate din rotația activă intrările nefolosite de 90 de zile.
- Memoria de performanță păstrează și eșecurile, nu doar succesele.
- Orice text venit din exterior (recenzii, comentarii, pagini web) este stocat ca dată și nu poate conține instrucțiuni pentru agenți.

### 10.5 Tehnic

- Tabele în Postgres, cu vectori în pgvector și căutare de text cu configurație pentru română.
- Vectorii se calculează local, cu un model multilingv mic, ținut încărcat în worker-light. Nu consumă cotă externă și nu așteaptă pe un culoar greu.
- Fiecare schimbare creează o versiune nouă. Versiunile vechi rămân pentru audit.
- Ștergerea unui client șterge tot Creierul lui, inclusiv vectorii și fișierele.

### 10.6 Ce vede clientul

- Poate citi și edita profilul de brand, faptele și ofertele.
- Vede playbook-ul lui într-un limbaj simplu: „Ce am învățat despre publicul tău”.
- Poate exporta tot Creierul, la cerere.
