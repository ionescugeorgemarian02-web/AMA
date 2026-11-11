## 14. Pipeline media: imagine, voce, video

Versiunea 1 produce video vertical fără avatar, complet pe CPU: voce sintetizată local, cadre din materialele clientului, din stock sau generate, subtitrări cuvânt cu cuvânt și muzică licențiată. Modelul scrie un plan de montaj, iar un program determinist îl execută.

### 14.1 Cinci formate fără avatar

| Format | Ce este | Materiale | Când se folosește |
| --- | --- | --- | --- |
| A Cadre și subtitrări | Clipuri tăiate pe bătăile scriptului, subtitrări mari, voce, muzică | Stock video | Sfaturi, liste, explicații |
| B Imagini în mișcare | Fotografii cu mișcare lentă și subtitrări | Fotografiile clientului sau imagini generate | Produse, locații, rezultate |
| C Grafică animată | Scene HTML animate, în culorile brandului | Șabloane | Oferte, cifre, anunțuri |
| D Demonstrație pe ecran | Înregistrare de ecran cu zoom și subtitrări | Înregistrarea clientului | Software, tutoriale |
| E Om real, montaj automat | Clientul se filmează citind scriptul. Platforma taie pauzele, pune subtitrări și cadre de sprijin. | Filmarea brută a clientului | Încredere, expertiză, povești |

Formatul E este cel mai credibil și nu cere etichetă AI pentru imagine. Portalul oferă un prompter pe telefon.

### 14.2 Ce nu intră în versiunea 1

- **Avatare cu sincronizare de buze.** Cer GPU.
- **Video generativ.** Cere GPU sau API plătit. Nivelurile gratuite au de regulă filigran sau interzic uzul comercial.
- **Adaptor pregătit.** Există un adaptor „generator video extern”. Se activează când apare buget sau o sursă gratuită cu drept comercial verificat. Atunci produce doar inserturi de 3–6 secunde.
- **Clonarea vocii unei persoane reale.** Doar cu acord scris; dezactivată implicit.

### 14.3 Imagini

Ordinea surselor:

1. Materialele reale ale clientului. Sunt cele mai bune pentru încredere.
2. Stock cu licență. Fiecare fișier se salvează cu identificatorul, autorul și o copie a licenței de la data descărcării.
3. Imagini generate din cota gratuită. Se folosesc ca fundal sau ilustrație, fără text în imagine.
4. Grafică din șabloane HTML, pentru orice material cu text.

Reguli:

- Textul nu se generează în imagine, pentru că modelele de imagine greșesc diacriticele. Textul se pune din șablon.
- Imaginile realiste generate primesc etichetă AI, prin G11.
- Fără persoane reale generate, fără mărci ale altora, fără stilul unui artist numit.
- F3 păstrează promptul, modelul și sămânța pentru fiecare imagine generată.

### 14.4 Voce

- **Motor.** Piper, local. Rapid pe CPU, fără cotă.
- **Voce de pornire.** Vocea românească existentă, pe set de date CC0. Dreptul de uz comercial pe tot lanțul de antrenare se verifică în F8.1.
- **Voce proprie, recomandat.** O persoană care își dă acordul în scris înregistrează circa două ore de text. Se antrenează o voce Piper o singură dată, pe GPU împrumutat sau închiriat câteva ore. Rezultatul are drepturi clare și sună unic.
- **Adaptor.** Un furnizor cloud poate fi adăugat mai târziu, fără schimbări în restul sistemului.

Normalizarea textului înainte de sinteză:

- numere, date, ore, procente și sume scrise în cuvinte, în română;
- abrevieri și unități desfăcute;
- ș și ț cu virgulă, nu cu sedilă;
- dicționar de pronunție pe client, pentru nume de brand și cuvinte străine;
- adrese web și simboluri citite natural sau eliminate.

Sinteză și verificare:

- Se sintetizează frază cu frază, cu pauze de 150–300 ms între ele.
- Fiecare frază se transcrie înapoi și se compară cu scriptul.
- Frazele cu prea multe diferențe se resintetizează, apoi se semnalează.
- Durata reală a narațiunii devine baza de timp a montajului.

### 14.5 De la script la video

1. E2 livrează scriptul pe bătăi.
2. F5 sintetizează vocea și măsoară durata fiecărei fraze.
3. Transcrierea cu timpi pe cuvânt se potrivește cu textul scriptului. Rezultă momentul exact al fiecărui cuvânt.
4. F6 scrie lista de decizii de montaj: pentru fiecare bătaie, ce cadru, de când până când, ce mișcare, ce text pe ecran.
5. F2 și F3 aduc cadrele. Fiecare cadru are licență înregistrată.
6. G1 validează lista: durate, fișiere existente, zone sigure.
7. F7 compune: cadre, tranziții, subtitrări, voce, muzică.
8. F7 exportă variantele pe canal.
9. G6, G5 și G11 verifică fișierele finale.
10. F4 produce coperta.

### 14.6 Lista de decizii de montaj

- Este contractul dintre model și program. Modelul nu scrie comenzi FFmpeg.
- Conține: rezoluția, durata totală, pista de voce, pista de muzică cu nivelul ei, lista de scene (sursă, început, sfârșit, încadrare, mișcare), lista de texte (cuvânt, moment, stil) și coperta.
- Fiind date, se poate valida, compara și re-randa identic.
- Două motoare de randare o pot citi: FFmpeg pentru formatele A, B, D și E; HyperFrames pentru formatul C.

### 14.7 Subtitrări

- Cuvânt cu cuvânt, cu evidențierea cuvântului rostit, 2–4 cuvinte pe ecran.
- Font cu toate diacriticele românești, din identitatea brandului.
- Zone sigure pe platformă: fără text sub butoanele și descrierile aplicației.
- Stil pe client: culoare, contur, poziție.
- Subtitrările sunt arse în imagine. Un fișier separat se trimite acolo unde platforma îl acceptă.

### 14.8 Sunet

- Vocea este în față. Muzica se atenuează automat sub voce.
- Bibliotecă de muzică cu licență clară, fiecare piesă cu fișierul ei de licență.
- Fără piese „în trend”. Conturile de firmă au oricum acces restrâns la muzica comercială.
- Efectele sonore sunt opționale și vin din aceeași bibliotecă.
- „Fără muzică” este o variantă validă.

### 14.9 Export

| Destinație | Format | Observații |
| --- | --- | --- |
| TikTok, Reels, Shorts | 1080×1920, 30 de cadre pe secundă, H.264, AAC | Durata după regulile fiecărei platforme |
| Feed pătrat | 1080×1080 | Re-aranjat, nu decupat orbește |
| Orizontal | 1920×1080 | Pentru YouTube lung și site |
| Copertă | Imagine statică din șablon | Text mare, contrast verificat |

### 14.10 Creativuri și miniaturi din șabloane

- Fiecare client are 6–10 șabloane HTML în identitatea lui: citat, ofertă, sfat, rezultat, anunț, copertă video.
- F4 completează șablonul cu textul aprobat și îl transformă în imagine.
- Variante pentru teste: aceeași ofertă cu titluri, culori sau imagini diferite.
- G5 verifică fiecare ieșire.

### 14.11 Resurse și ritm

- Câte un job media pe fiecare culoar greu. La 8 nuclee, două video se randează în paralel \[I\].
- Lotul săptămânal al unui client se randează dinainte, cât culoarele sunt libere, nu în ziua publicării.
- Ciornele se randează rapid, la calitate mai mică. Finalul se randează o singură dată, după aprobare.
- Viteza reală se măsoară în F8.9. Ținta de pornire: un video de 45 de secunde gata în mai puțin de 10 minute \[I\].
- Intermediarele se șterg după 7 zile.
