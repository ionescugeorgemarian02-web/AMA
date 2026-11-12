## 16. Ads autonom și Strategul

Modelul propune, regulile decid, executorul aplică. Nicio schimbare de buget nu depinde de judecata unui LLM, iar platforma nu ține niciodată banii clientului.

### 16.1 Principii

1. Bugetul de reclame stă în contul de reclame al clientului, pe cardul lui. Platforma are rol de administrator de reclame, nu de administrator financiar.
2. Fiecare client are plafoane scrise în contract și în platformă: zilnic, lunar și pe campanie.
3. Modelele produc planuri și propuneri de schimbare. Un motor de reguli fără LLM le verifică. Executorul le aplică.
4. Totul pornește în pauză. Activarea este un pas separat.
5. Fiecare schimbare păstrează starea de dinainte și se poate anula.
6. Fără reclame politice sau pe teme sociale sensibile.

### 16.2 Acces

| Platformă | Ce trebuie | Observații |
| --- | --- | --- |
| Meta | Aplicație cu acces avansat la administrarea reclamelor, App Review, firmă verificată; clientul acordă acces contului lui | Accesul extins cere și un istoric de apeluri reușite |
| Google Ads | Nivel de acces pe proiectul Google Cloud: Explorer la început, Basic după verificarea de brand | Explorer blochează unele funcții de planificare |
| TikTok Ads | Aplicație aprobată pentru Marketing API | De verificat la construcție |

Până la aprobări există modul „copilot”: platforma primește rezultatele prin acces de citire sau prin exporturi, propune schimbările, iar tu le aplici manual în managerul de reclame.

### 16.3 Fluxul unei campanii

1. Clientul stabilește obiectivul, bugetul și plafoanele.
2. I1 scrie planul media: structură, public, împărțirea bugetului, matricea de creativuri, măsurare, criterii de oprire.
3. Clientul aprobă planul și plafoanele în portal.
4. E3, F4 și F7 produc creativurile. Ele trec prin validare și prin I5.
5. I2 construiește campania în pauză.
6. Verificarea dinaintea lansării: urmărire funcțională, pagini de destinație, etichete, plafoane.
7. Activare, după nivelul de autonomie.
8. I3 și I6 supraveghează continuu. I4 gestionează testele.
9. Strategul face revizuirea săptămânală.

### 16.4 Regulile gardianului de buget

Valori de pornire \[I\], editabile pe client:

| Regulă | Valoare de pornire |
| --- | --- |
| Plafon zilnic și lunar | Din contract; nu se depășește niciodată |
| Schimbare maximă de buget pe zi | 20–30% per campanie |
| Perioadă de așteptare după o schimbare | 48–72 de ore |
| Date minime înainte de o decizie pe o reclamă | Cheltuială de două ori costul-țintă per rezultat, sau 1.000 de afișări și un număr minim de clicuri |
| Oprire la pierdere | Cost per rezultat de peste trei ori ținta, după datele minime |
| Oboseala creativului | Scădere susținută a ratei de clic, cu frecvență în creștere |
| Schimbări automate pe zi | Cel mult 5 per cont |
| Schimbări peste plafon | Cer aprobarea clientului în portal |

### 16.5 Oprirea de urgență

I6 pune totul pe pauză și te anunță când:

- cheltuiala pe oră depășește de câteva ori ritmul planificat;
- urmărirea conversiilor nu mai trimite evenimente;
- pagina de destinație nu răspunde;
- costul pe mia de afișări sau costul per clic sare brusc;
- platforma semnalează o problemă de politică pe cont;
- apare o eroare de autentificare.

Repornirea după o oprire de urgență este întotdeauna manuală.

### 16.6 Testarea creativurilor

- Campanie de test separată, cu buget mic și egal între variante.
- O singură variabilă pe test: hook, ofertă, format sau public.
- Câștigătorul se declară când probabilitatea de a fi cel mai bun trece de 90% și fiecare variantă are datele minime.
- Câștigătoarele trec în campania de scalare. Pierzătoarele se opresc și intră în memoria de performanță.
- Platforma nu se luptă cu optimizarea automată a rețelei de reclame. Îi dă creativuri bune și semnale curate.

### 16.7 Măsurare și atribuire

- Schemă unică de parametri UTM pe toate linkurile.
- Evenimente proprii pe paginile de captare, cu acordul vizitatorului.
- Trimiterea evenimentelor de pe server către platformele de reclame, doar cu consimțământ.
- Raportul are două coloane: ce spune platforma de reclame și ce a măsurat site-ul. Diferența se explică, nu se ascunde.
- La video: rata de oprire din derulare (vizionări de 3 secunde din afișări), pragurile de 25, 50, 75 și 100% și costul per rezultat.

### 16.8 Verificarea reclamelor înainte de lansare

- Reguli pe platformă: afirmații despre atribute personale, promisiuni de rezultat, categorii speciale, produse restricționate.
- Potrivirea dintre reclamă și pagina de destinație.
- Dezvăluirea AI la nivel de reclamă, acolo unde platforma o cere.
- Mențiunile legale ale nișei.
- O reclamă respinsă de platformă devine exemplu în pachetul de reguli.

### 16.9 Strategul în reclame

- Citește săptămânal cheltuiala, rezultatele, costul per rezultat și testele încheiate.
- Decide: continuă, mută buget între campanii în limita plafoanelor, cere creativuri noi, pivotează unghiul sau oprește.
- O direcție se oprește după două ferestre consecutive sub pragul minim, cu date suficiente.
- La pivot scrie trei ipoteze noi și cere testarea lor pe 20% din buget.
- Deciziile care schimbă oferta, publicul-țintă sau bugetul total merg la client.

### 16.10 Ce vede clientul

- Cheltuiala zilei și a lunii față de plafon.
- Ce s-a schimbat, când și de ce, în cuvinte simple.
- Cereri de aprobare pentru orice trece de plafon.
- Un raport săptămânal scurt.
