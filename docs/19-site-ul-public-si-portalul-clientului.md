## 19. Site-ul public și portalul clientului

Site-ul are două sarcini: aduce lead-uri prin auditul gratuit și găzduiește paginile legale fără de care nicio platformă nu aprobă aplicația. Portalul este locul unde clientul aprobă, corectează și vede rezultatele, de pe telefon.

### 19.1 Site-ul public

| Pagină | Scop | Conținut-cheie |
| --- | --- | --- |
| Acasă | Explică oferta în 10 secunde | Promisiune, pentru cine, cum funcționează în trei pași, dovezi, buton spre audit |
| Audit gratuit | Captare de lead-uri | Formular scurt, ce primește firma, opt-in, exemplu de raport |
| Servicii și pachete | Compararea pachetelor | Livrabile numărabile și ce nu este inclus |
| Prețuri | Transparență | Pachete, setup, suplimente, întrebări frecvente |
| Cum lucrăm | Încredere | Agenți plus supraveghere umană, aprobare obligatorie, ce se întâmplă cu datele |
| Studii de caz | Dovadă | Situație, acțiune, rezultat; la început, CariereAI și BigBrain |
| Blog | Trafic organic și demonstrație | Articole produse de platformă |
| Despre și contact | Legitimitate | Datele firmei, formular, programare |
| Transparență AI | Conformitate și încredere | Ce este generat, cum este verificat, cum este etichetat |
| Legal | Cerință pentru aprobările API | Termeni, confidențialitate, cookie-uri, acord de prelucrare, instrucțiuni de ștergere a datelor |
| Stare | Încredere | Starea serviciului și incidentele |

Cerințe tehnice:

- Pagini statice sau randate pe server, rapide pe telefon.
- Banner de consimțământ pentru cookie-uri. Fără urmărire înainte de acord.
- Analiză de trafic proprie, găzduită local.
- Date structurate, harta site-ului, adrese canonice.
- Formulare cu protecție anti-spam și opt-in dublu.
- Versiunea minimă (Acasă, Legal, Contact, Transparență AI) se publică în F0.5, pentru cererile de aprobare.

### 19.2 Portalul clientului

| Zonă | Ce face clientul |
| --- | --- |
| Onboarding | Răspunde la interviul condus de asistent, încarcă materiale, conectează conturile, urmărește pașii rămași |
| Creierul de brand | Citește și corectează profilul, faptele și ofertele; aprobă versiunile |
| Calendar | Vede ce urmează, pe canal |
| Aprobări | Aprobă, cere schimbări sau respinge, cu previzualizare reală |
| Materiale | Încarcă fotografii și filmări; folosește prompterul pentru filmările proprii |
| Inboxul de tendințe | Lipește linkuri și idei |
| Reclame | Stabilește plafoane, aprobă planuri și depășiri, vede cheltuiala |
| Rapoarte | Raportul lunar, cifrele la zi, „ce am învățat despre publicul tău” |
| Facturare | Abonamentul, facturile, metoda de plată |
| Suport | Întreabă asistentul sau cere un om |
| Date | Exportă sau cere ștergerea datelor |

### 19.3 Onboardingul, pas cu pas

1. Clientul primește linkul de activare după plată.
2. Asistentul (J6) pune întrebări, una câte una, și cere clarificări unde răspunsul este vag.
3. Clientul încarcă logo, fotografii, liste de prețuri și materiale vechi.
4. Conectează conturile prin fluxurile oficiale de autorizare. Platforma nu cere și nu stochează parole.
5. Platforma citește site-ul și propune Creierul de brand.
6. Clientul corectează și aprobă profilul și registrul de fapte.
7. Strategul propune planul pe 90 de zile. Clientul îl aprobă.
8. Apare primul lot de conținut spre aprobare.

O bară arată progresul. Onboardingul se poate relua de unde a rămas.

Interviul acoperă: ce vinde firma, cui, la ce preț, de ce o aleg clienții, ce obiecții aude, ce concurenți are, ce a încercat, ce nu vrea să apară niciodată, ce ton vrea și ce obiectiv are pe 90 de zile.

### 19.4 Aprobarea de către client

- Notificare pe email și push când există un lot nou.
- Termen de 48 de ore, cu reamintire la 24 de ore.
- Fără răspuns, postarea nu se publică. Slotul se reprogramează și apare în raport.
- Când criteriul de promovare din secțiunea 7.4 este îndeplinit, clientul poate alege aprobarea prin excepție (L2). Alegerea se face în portal, se înregistrează și se poate retrage oricând.
- Fiecare aprobare este înregistrată cu utilizator, moment și versiune.

### 19.5 Facturare

- Planurile și abonamentele se creează prin API-ul de abonamente al procesatorului de plăți.
- Primul pas de plată salvează metoda. Reînnoirea este automată.
- Webhook-urile verificate actualizează starea contului.
- La plată eșuată: perioadă de grație de 7 zile, cu anunțuri. Apoi producția se suspendă, iar datele rămân.
- Facturile se emit cu instrumentul agreat cu contabilul.
- Platforma nu vede și nu stochează date de card.

### 19.6 Raportul lunar

1. Ce am livrat: număr pe tip, față de pachet.
2. Ce a ieșit: cifrele principale, față de luna trecută.
3. Ce a mers cel mai bine și de ce.
4. Ce nu a mers și ce schimbăm.
5. Ce am învățat despre public.
6. Planul lunii următoare.
7. Ce avem nevoie de la client.

Raportul are o pagină, cu linkuri spre detalii.
