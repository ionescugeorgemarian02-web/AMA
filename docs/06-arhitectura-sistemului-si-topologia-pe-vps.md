## 6. Arhitectura sistemului și topologia pe VPS

Platforma este un monolit modular în Python, cu un singur Postgres, două tipuri de workeri și mai multe „culoare grele” pentru joburile care consumă procesor. Rulează singură pe un VPS dedicat și ține toate serviciile încărcate, în circa 21 GB din 24.

### 6.1 Principii

1. **Un singur loc pentru adevăr.** Postgres ține datele, cozile, starea workflow-urilor și vectorii.
2. **O singură ușă spre exterior.** Publicarea, emailul, reclamele și plățile trec prin executorul B7.
3. **LLM-ul propune, codul execută.** Niciun model nu apelează direct un API de publicare, de reclame sau de plăți.
4. **Totul este versionat.** Prompturi, reguli, șabloane, modele, strategii.
5. **Totul este izolat pe client.** De la rândurile din baza de date până la fișiere.
6. **Degradare controlată.** Când lipsește un furnizor, munca se amână sau trece pe rezervă, fără pierderi.
7. **Buget de resurse.** O componentă nouă este acceptată doar dacă încape în bugetul de memorie și de nuclee.

### 6.2 Straturile

| Strat | Ce conține |
| --- | --- |
| 1 Interfețe | Site public, portal pentru clienți, panou de control ca aplicație web instalabilă, bot Telegram, conector pentru Claude |
| 2 Aplicație | API, autentificare, roluri, module pe departamente |
| 3 Orchestrare | Mașini de stări, workflow-uri durabile, cozi cu priorități, planificator de timp |
| 4 Agenți și validatori | Componentele de tip L, A și M, plus pachetele de reguli |
| 5 Inteligență | Gateway de modele, registru de prompturi, constructor de context, banc de evaluare |
| 6 Execuție | Media, crawler, conectori de platforme, email, reclame |
| 7 Date | Postgres cu vectori, fișiere media pe disc, jurnal de evenimente, backup extern |
| 8 Infrastructură | Docker Compose, proxy propriu cu certificate automate, CI pe GitHub |

### 6.3 Stack tehnologic recomandat

| Rol | Alegere | De ce | Alternativă |
| --- | --- | --- | --- |
| Limbaj și framework | Python 3.12+, FastAPI | Același ecosistem ca platformele tale existente; biblioteci pentru ML și media | – |
| Interfață | Pagini randate pe server, HTMX, Alpine.js | Un singur runtime, fără lanț de build JavaScript, memorie puțină | React, dacă interfața o cere mai târziu |
| Bază de date | PostgreSQL 16+ cu pgvector și pg\_trgm | Date, cozi, vectori și căutare text într-un singur loc | – |
| Execuție durabilă | DBOS Transact, ca bibliotecă | Workflow-uri care reiau de la ultimul pas, cozi cu limită de rată, fără server separat | Coadă proprie pe Postgres |
| Acces la date și migrări | SQLAlchemy 2, Alembic | Standard, bine cunoscut de agenții de cod | – |
| Scheme | Pydantic 2 | Validare strictă a ieșirilor LLM | – |
| Client LLM | Client propriu, subțire, pe protocolul compatibil OpenAI | Fără dependență grea în punctul prin care trec toate cheile | – |
| Model local | Server llama.cpp cu model cuantizat de 7–9 miliarde de parametri, ținut încărcat | Rezervă nelimitată; preia clasificările și extragerile | Model mai mic, dacă procesorul este prea lent |
| Embeddings | Model multilingv mic, încărcat în worker-light | Nu consumă cotă și nu ocupă un culoar greu | – |
| Optimizare de prompturi | DSPy (GEPA, MIPROv2), rulat offline | Metodele de referință în 2026 | – |
| ML clasic | scikit-learn, LightGBM | Suficient pentru scorare și predicție | – |
| Transcriere și aliniere | faster-whisper, pe CPU | Timpi pe cuvânt pentru subtitrări; verificarea vocii | – |
| Voce | Piper | Rapid pe CPU, are voce în română | Furnizor cloud, prin adaptor |
| Video | FFmpeg cu libass | Stabil și determinist | HyperFrames pentru animații HTML |
| Imagini din șabloane, pagini dinamice | Chromium headless prin Playwright | HTML în PNG; pagini cu JavaScript | – |
| Text din pagini web | trafilatura | Curăță articolele de meniuri și reclame | – |
| OCR | Tesseract cu limba română | Verifică textul din cadre | – |
| Notificări | Web Push și Telegram Bot API | Gratuite, merg pe iPhone | – |
| CI și imagini | GitHub Actions, GHCR | Gratuite pentru un repo mic | – |

Versiunile exacte se fixează în pasul F1.2, cu fișier de blocare și hash-uri. Nu am verificat fiecare versiune în parte.

### 6.4 Servicii pe VPS și bugetul de resurse

VPS-ul este dedicat platformei: cel puțin 24 GB RAM, fără GPU. Tabelul este calculat pentru 24 GB și 8 nuclee \[I\] și se reface în F0.4, pentru nucleele reale.

Regula de bază: memoria ține totul încărcat, iar nucleele decid câte joburi grele merg deodată. Mai multă memorie nu face un video să se randeze mai repede. Îl lasă doar să pornească imediat și să ruleze lângă altele.

| Serviciu | Rol | Limită de memorie | Paralelism | Pornit |
| --- | --- | --- | --- | --- |
| proxy | Intrarea HTTPS, certificatele, fișierele media semnate | 0,1 GB | – | Permanent |
| app | API și interfețe, în 2–4 procese | 1 GB | Cereri web | Permanent |
| worker-light | Apeluri LLM, conectori, validatori ușori, modelul de embeddings | 2 GB | 24 de joburi în paralel | Permanent |
| postgres | Baza de date a platformei | 3,5 GB | – | Permanent |
| local-llm | Model local de text, ținut încărcat | 6,5 GB | Ocupă un culoar greu cât generează | Permanent |
| worker-heavy | Randare, voce, transcriere, OCR, cu modelele lor încărcate | 5 GB | 2 culoare grele | Permanent |
| browser | Grup de pagini Chromium headless | 1,5 GB | 3 pagini în paralel | Permanent |
| staging | Copie de test a platformei, cu baza ei de date | 1,5 GB | – | Permanent |
| Total limite | | 21,1 GB | | |

- **Totul pornit permanent.** Niciun serviciu nu se mai încarcă la cerere. Modelul local, vocea, transcrierea și browserul stau în memorie, deci un job greu pornește în secunde, nu după un minut de încărcare.
- **Culoare grele.** Joburile care consumă procesor (randare, voce, transcriere, OCR, generare pe modelul local) trec printr-un semafor cu mai multe locuri, ținut în baza de date. Numărul de culoare este numărul de nuclee împărțit la 4, rotunjit în jos, minimum unul: 2 la 8 nuclee, 3 la 12, 4 la 16 \[I\]. Fiecare culoar primește cel mult 4 fire de execuție.
- **Embeddings în afara culoarelor grele.** Căutarea în memorie și verificările de similaritate sunt pe drumul fiecărui livrabil. Modelul de embeddings este mic, stă încărcat în worker-light și nu așteaptă în spatele unei randări.
- **Apeluri la modele în paralel.** worker-light ține 24 de joburi deodată. Limita reală rămâne cea a furnizorilor de modele, aplicată de gateway (secțiunea 8.4).
- **Model local mai mare.** În 6,5 GB încape un model de 7–9 miliarde de parametri, cuantizat, în locul unuia mic. Rămâne lent pe procesor, dar scrie mai bine în română și poate prelua singur profilul de clasificare și extragere. Viteza reală se măsoară în F3.5 \[I\].
- **Rezervă.** Limitele adunate dau circa 21 GB. Restul de 3 GB rămâne sistemului și memoriei-tampon de disc. Nu se alocă 100%: fără rezervă, sistemul oprește procese la primul vârf.
- **Peste 24 GB.** Surplusul se împarte în această ordine: încă un culoar greu, dacă există 4 nuclee pentru el (2,5 GB); un model local mai bun (până la 10 GB); mai multă memorie pentru Postgres.
- **Ce nu schimbă memoria.** Avatarele și video generativ cer în continuare GPU (secțiunea 14.2).
- **Staging permanent.** Fiecare cerere de integrare aprobată ajunge singură pe staging, iar testele de fum rulează imediat. Staging are bază de date și secrete proprii și folosește culoarele grele doar când producția le lasă libere.
- **Prioritate.** Producția are prioritate la procesor față de staging și față de joburile de învățare.
- **Învățare continuă.** Joburile de învățare care folosesc modelul local rulează oricând există un culoar liber, nu doar noaptea. Cele care folosesc cote găzduite rulează din cota rămasă, înainte de resetare.
- **Plan de rezervă.** Dacă F0.4 arată mai puține nuclee sau mai puțină memorie, se reduce întâi numărul de culoare, apoi mărimea modelului local.
- **Platformele existente.** CariereAI și BigBrain rămân pe VPS-ul lor. Un incident într-o parte nu o atinge pe cealaltă. Motorul de audit din BigBrain este apelat prin rețea, printr-un adaptor.

### 6.5 Stocare

- Fișierele media stau pe disc, într-un volum dedicat, organizate pe client și adresate după hash-ul conținutului.
- Buget de disc: jumătate din discul VPS-ului dedicat pentru media, stabilit în F0.4 \[I\]. Un video final de 45 de secunde are 15–25 MB.
- Păstrare: finalele 90 de zile local, intermediarele 7 zile. Apoi se mută în arhiva externă sau se șterg, după contract.
- Alerte la 70% și la 85% din disc.
- Fișierele cerute de Instagram și TikTok se servesc prin proxy, cu linkuri semnate care expiră.

### 6.6 Rețea și expunere

- Doar porturile 80 și 443, prin proxy-ul platformei. Trei subdomenii: site public, aplicație (panou și portal), fișiere media.
- Firewall-ul închide tot restul. Accesul de administrare la server se face doar cu cheie.
- Staging pe subdomeniu separat, protejat cu parolă.
- Niciun serviciu intern (Postgres, model local) nu este expus în afara rețelei Docker.

### 6.7 Deciziile de arhitectură de înregistrat

| Cod | Decizie |
| --- | --- |
| ADR-01 | Monolit modular, nu microservicii |
| ADR-02 | Postgres unic pentru date, cozi, workflow-uri și vectori |
| ADR-03 | Execuție durabilă prin bibliotecă; starea de business în tabele proprii |
| ADR-04 | Gateway de modele propriu și subțire |
| ADR-05 | Tipuri de componente D, L, A, M, H; implicit D |
| ADR-06 | Claude în afara căii critice |
| ADR-07 | Doar API-uri oficiale; fără proxy-uri și fără anti-detect |
| ADR-08 | Proveniență păstrată și etichetare AI |
| ADR-09 | Video fără avatar în versiunea 1 |
| ADR-10 | Voce locală pe CPU, cu licență verificată |
| ADR-11 | Învățare cu promovare controlată |
| ADR-12 | Autonomie graduală L0–L4 |
| ADR-13 | Interfață randată pe server, gândită întâi pentru telefon |
| ADR-14 | Multi-tenant cu izolare la nivel de rând, din prima zi |
| ADR-15 | Media pe disc local, cu politici de păstrare și backup extern |
| ADR-16 | VPS dedicat: toate serviciile pornite permanent; paralelismul greu se dimensionează după nuclee, nu după memorie |
