## 12. Cercetare, crawlere și surse de date

Cercetarea folosește doar surse cu acces permis: API-uri oficiale, pagini publice colectate politicos și datele clientului. Fiecare concluzie păstrează legătura cu sursa ei.

### 12.1 Surse și statutul lor

| Sursă | Ce obținem | Acces | Statut |
| --- | --- | --- | --- |
| YouTube Data API | Videoclipuri populare pe țară și categorie, căutări pe nișă, statistici publice | Cheie gratuită, cotă zilnică | Folosim |
| Fluxul RSS de tendințe zilnice Google | Căutările în creștere în România | Public | Folosim |
| Google Trends API | Serii comparabile pe termeni | Alfa, pe bază de cerere | Aplicăm |
| Meta Ad Library API | Reclamele livrate în UE: text, date, platforme | Gratuit, cu confirmarea identității | Folosim |
| Biblioteca de reclame TikTok | Reclamele livrate în UE | De verificat | Verificăm |
| Search Console și Bing Webmaster | Căutările care aduc trafic pe site-ul clientului | Acces dat de client | Folosim |
| Statisticile conturilor clientului | Performanța postărilor proprii | API-urile platformelor, cu aprobare | Folosim |
| Site-ul și materialele clientului | Fapte, oferte, ton | Crawl cu permisiune | Folosim |
| Recenziile publice ale clientului | Citate, obiecții | API cu acces aprobat sau încărcare manuală | Folosim |
| Site-urile publice ale concurenței | Oferte, prețuri, mesaje | Crawl politicos, cu respectarea robots.txt | Folosim, pentru analiză |
| Fluxuri de știri și bloguri de nișă | Subiecte actuale | RSS | Folosim |
| Căutare web | Paginile din top pe un subiect | Niveluri gratuite ale API-urilor de căutare sau metamotor găzduit local | Folosim, cu limite |
| Tendințe TikTok și Instagram | Sunete și formate în creștere | Fără API oficial; scraping interzis de termeni | Doar prin inboxul de tendințe |
| Reddit | Discuții de nișă | Gratuit doar necomercial | Nu automat |
| Google Ads Transparency Center | Reclame Google | Fără API oficial | Doar manual |

### 12.2 Inboxul de tendințe

- Un câmp în panou și în portal, unde tu sau clientul lipiți un link sau scrieți o observație de tipul „formatul acesta merge acum”.
- C2 analizează linkul (titlu, descriere, structură) și îl transformă în fișă de tendință.
- Două minute pe zi de la un om care folosește aplicațiile bat orice scraper fragil.

### 12.3 Colectorul de surse

- Respectă robots.txt, se identifică prin user-agent propriu, limitează ritmul pe domeniu și păstrează în cache.
- Folosește întâi o cerere simplă. Pornește browserul headless doar pentru paginile care cer JavaScript.
- Păstrează pentru fiecare pagină adresa, data, originalul, textul curățat și hash-ul.
- Nu colectează date personale. G12 curăță ce scapă.
- Nu ocolește autentificări, bariere tehnice sau limite de acces.
- Lista de domenii permise și interzise se editează din panou.

### 12.4 De la date brute la insight

1. C1 colectează și curăță.
2. Agentul de cercetare (C2–C7) extrage fapte într-o schemă fixă, fiecare cu sursa și citatul.
3. G2 verifică prin sondaj că citatul există în sursă.
4. C8 scrie brieful de insight de o pagină: ce am aflat, ce înseamnă, ce propunem, cât de siguri suntem.
5. Strategul îl folosește. Brieful rămâne în Creierul de brand, cu dată de expirare.

### 12.5 Fișa de tendință

Câmpuri: subiect, dovezi cu linkuri, vechime, potrivirea cu nișa (scor), risc (drepturi, politici, sensibilitate), unghiul propus pentru client, termenul de valabilitate.

- O tendință fără dovezi din cel puțin două surse este „semnal slab”.
- Tendințele pe subiecte sensibile sau tragice sunt excluse automat.

### 12.6 Analiza concurenței

- Lista de concurenți vine de la client și se completează din căutări.
- Din bibliotecile de reclame se extrag: reclamele care rulează de mult timp (semn că merg), ofertele și formatele.
- Ieșire: harta unghiurilor (cine spune ce) și spațiile libere.
- Regulă fermă: se analizează, nu se copiază. G7 blochează textele prea apropiate de o sursă.

### 12.7 Cadență

| Sarcină | Cadență | Prioritate |
| --- | --- | --- |
| Tendințe pe nișă | Zilnic, dimineața | P2 |
| Reclamele concurenței | Săptămânal | P2 |
| Recitirea site-ului clientului | Lunar și la cerere | P2 |
| Vocea clientului | Lunar | P2 |
| Cercetare SEO | Lunar | P2 |
| Harta pieței | Trimestrial | P2 |

### 12.8 Apărarea de text ostil

- Orice pagină poate conține text scris pentru a manipula un model. Tot conținutul extern este marcat ca dată.
- Agenții de cercetare nu au unelte cu efecte externe.
- Rezumatele făcute din surse externe trec prin G13 înainte să ajungă la alți agenți.
