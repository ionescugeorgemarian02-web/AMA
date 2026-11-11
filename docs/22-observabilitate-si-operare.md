## 22. Observabilitate și operare

Platforma se supraveghează singură și te deranjează doar la avarii. Fiecare job are urmă, fiecare eroare are o reacție prevăzută, iar backupul se testează prin restaurare, nu prin presupunere.

### 22.1 Ce se înregistrează

- Jurnale structurate, cu identificator de corelare pe campanie, livrabil și job.
- Pașii de execuție: început, sfârșit, rezultat, reîncercări.
- Apelurile la modele, ca în secțiunea 8.8.
- Tranzițiile de stare și deciziile oamenilor.
- Efectele externe: ce s-a trimis, unde și ce a răspuns platforma.
- Măsurători de sistem: memorie, CPU, disc, lungimea cozilor.

Totul stă în Postgres și în fișiere de jurnal rotite. Nu se instalează o stivă separată de monitorizare: ar consuma peste 1 GB de memorie pentru ce poate arăta panoul.

### 22.2 Indicatori de sănătate și ținte \[I\]

| Indicator | Țintă |
| --- | --- |
| Livrabile care ajung la final fără intervenție tehnică | Peste 97% |
| Publicări la ora programată | Peste 99% |
| Vârsta celui mai vechi job din coadă | Sub 30 de minute pentru P0 și P1 |
| Epuizări de cotă pe zi | Zero pentru P0 și P1 |
| Timp de recuperare după un incident critic | Sub 4 ore |
| Disc folosit | Sub 70% |
| Memorie folosită de platformă | Sub 21 GB din 24, la vârf |
| Timp de așteptare la culoarele grele | Sub 15 minute pentru P0 și P1 |

### 22.3 Watchdog: ce face singur

| Semnal | Reacție automată | Te anunță |
| --- | --- | --- |
| Worker fără semn de viață | Repornește workerul și reia joburile de la ultimul pas | La a treia repornire într-o oră |
| Job peste timpul maxim | Îl oprește și îl reîncearcă o dată | Dacă eșuează din nou |
| Furnizor de modele cu multe erori | Îl scoate temporar din rutare | Dacă rămân sub doi furnizori sănătoși |
| Conector cu eroare de autentificare | Pune canalul pe pauză și cere reautorizare | Imediat |
| Coadă de erori care crește | Grupează erorile pe cauză | Când trece de prag |
| Disc peste 85% | Șterge intermediarele expirate și oprește randările noi | Imediat |
| Memorie aproape de limită | Amână joburile grele | Dacă durează peste 15 minute |
| Rată de eșec peste 30% într-o oră | Oprește producția nouă | Imediat |
| Backup eșuat | Reîncearcă o dată | Imediat |

### 22.4 Severități

| Nivel | Exemple | Canal | Termen de reacție |
| --- | --- | --- | --- |
| Critic | Cheltuială anormală, cont restricționat, scurgere de date, sistem oprit | Push și Telegram, la orice oră | Imediat |
| Major | Canal pe pauză, backup eșuat, coadă blocată | Push, în program | În aceeași zi |
| Minor | Un livrabil în coada de erori, un furnizor căzut | Rezumat zilnic | În aceeași săptămână |
| Informativ | Promovări, rapoarte, cote | Panou | – |

### 22.5 Coada de erori

- Fiecare intrare are contextul complet: ce job, ce pas, ce eroare și ce s-a încercat.
- Acțiuni: reîncearcă, reîncearcă de la un anumit pas, anulează, trimite la om.
- Erorile cu aceeași cauză se grupează. O cauză nouă devine incident.
- Nimic nu se șterge din coada de erori fără o decizie înregistrată.

### 22.6 Backup și restaurare

- **Baza de date.** Copie zilnică, comprimată și criptată.
- **Fișiere.** Copierea zilnică a fișierelor media finale și a celor încărcate de clienți.
- **Configurare.** Fișierele de mediu și configurarea proxy-ului, criptate.
- **Destinație.** Un spațiu de stocare extern, pe un nivel gratuit, în altă locație decât VPS-ul. Capacitatea și termenii se verifică în F1.9.
- **Păstrare.** 7 copii zilnice, 4 săptămânale, 6 lunare.
- **Test.** Săptămânal, restaurare automată într-o bază de probă și o interogare de verificare. Un backup netestat nu se consideră backup.
- **Ținte \[I\].** Pierdere maximă de date de 24 de ore. Repunere în funcțiune în 4 ore.

### 22.7 Un singur VPS: ce înseamnă

- VPS-ul dedicat este punct unic de defectare pentru platformă. CariereAI și BigBrain nu mai depind de el.
- VPS-ul vechi poate ține a doua copie criptată a backupului și poate găzdui exercițiul de restaurare, dacă are loc pe disc \[I\].
- Măsuri: backup extern testat, documentație de reinstalare de la zero, coadă de publicare care reia de unde a rămas.
- Postările ratate în timpul unei căderi nu se publică în rafală la revenire. Se reprogramează.
- La treapta 3 de scalare apare al doilea server, pentru joburile grele sau ca rezervă.

### 22.8 Livrarea versiunilor noi

1. Agentul de cod lucrează pe o ramură și deschide o cerere de integrare.
2. CI rulează testele, verificările de stil, scanarea de secrete și de vulnerabilități.
3. După aprobare, CI construiește imaginea și o publică în registru.
4. Staging preia imaginea și rulează testele de fum.
5. Tu apeși „Promovează în producție” din panou sau din Telegram.
6. Migrările de bază rulează întâi și sunt compatibile cu versiunea veche.
7. Versiunea nouă pornește lângă cea veche. După verificarea de sănătate, traficul se mută.
8. Versiunea veche rămâne disponibilă pentru revenire rapidă.

După instalarea inițială, totul rulează fără sudo, ca utilizator obișnuit, în Docker. Livrarea este declanșată de un mic serviciu intern, nu prin acces direct la server.

### 22.9 Proceduri pentru incidente

Fiecare procedură are simptom, verificări, acțiuni și criteriu de închidere (șablonul Ș14). Lista minimă:

- cheltuială anormală la reclame;
- cont restricționat sau postare eliminată;
- publicare greșită, cu text sau client greșit;
- suspiciune de scurgere de date;
- cote epuizate;
- bază de date indisponibilă;
- disc plin;
- furnizor principal de modele retras;
- token compromis;
- restaurare completă pe un server nou.

Fiecare incident critic se încheie cu o analiză scurtă: ce s-a întâmplat, de ce și ce regulă sau test nou îl previne.

### 22.10 Rutina ta \[I\]

| Cadență | Ce faci | Durată |
| --- | --- | --- |
| Zilnic | Aprobări, alerte, o privire pe Acasă | 15–30 de minute |
| Săptămânal | Eșantionul de audit, contestațiile, lecțiile de curatoriat, starea aprobărilor API | 45 de minute |
| Lunar | Dosarele de Consiliu, rapoartele clienților, testul comparativ al modelelor, actualizările de dependențe, registrul de riscuri | 2–3 ore |
| Trimestrial | Revizuirea politicilor de platformă, a prețurilor și a riscurilor; exercițiu de restaurare completă | 3 ore |
