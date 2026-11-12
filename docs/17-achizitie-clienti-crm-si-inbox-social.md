## 17. Achiziție clienți, CRM și inbox social

Același modul servește două scopuri: aduce clienți agenției și se vinde ca serviciu clienților ei. Lucrează doar cu persoane care au cerut contactul sau au scris primele.

### 17.1 De unde vin lead-urile

| Sursă | Cum intră | Temeiul contactului |
| --- | --- | --- |
| Formularul de audit gratuit | Din site în CRM | Solicitare și opt-in pentru email |
| Resurse descărcabile | Din pagina de captare în CRM | Opt-in dublu |
| Formulare de lead din reclame | Prin API-ul platformei | Acordul dat în formular |
| Mesaje și comentarii | Din inbox, când persoana cere o ofertă | Persoana a scris prima |
| Programări | Din pagina de rezervare | Solicitare directă |
| Recomandări și parteneri | Introduse manual | Introducere personală |
| Liste de conturi-țintă | Din date publice de firmă | Fără email automat; contact făcut de om |

### 17.2 Lista de conturi-țintă, fără date personale

- Conține firme, nu persoane: nume, domeniu, nișă, localitate, site, pagini sociale publice și semnale (site lent, pagini neactualizate).
- Surse: registre publice de firme, hărți deschise, site-urile firmelor.
- Fiecare firmă primește un mini-audit și trei argumente de discuție.
- Tu sau un om de vânzări contactați personal, pe canalul potrivit.
- Platforma nu trimite singură mesaje către această listă.

### 17.3 Email către abonați

- Furnizor de email prin adaptor. Se pornește pe un nivel gratuit, cu limitele lui.
- Subdomeniu dedicat, cu SPF, DKIM și DMARC.
- Opt-in dublu. Dezabonare dintr-un clic, în antet și în text.
- Listă de suprimare globală: dezabonați, adrese respinse, plângeri. Nicio campanie nu o poate ocoli.
- Volumul crește treptat, pe parcursul câtorva săptămâni.
- Praguri de oprire: rată de respingere peste 2% sau rată de plângeri peste 0,1% \[I\].
- Verificarea adreselor: sintaxă și existența domeniului. Fără sondarea serverelor de email.

### 17.4 Matricea de conformitate pe țări

- Un tabel întreținut în platformă: țara, tipul de destinatar, ce este permis, ce mențiuni sunt obligatorii, cine a verificat și când.
- România este setată implicit pe „doar cu consimțământ”, inclusiv pentru firme.
- Orice altă piață rămâne blocată până când un avocat completează rândul.
- Expeditorul de email verifică matricea înainte de fiecare trimitere.

### 17.5 Calificare și scor

- La început, reguli simple: nișă potrivită, buget declarat, termen, persoană cu putere de decizie.
- Asistentul pune 3–5 întrebări, pe formular sau în conversație, și spune clar că este asistent AI.
- Scorul împarte lead-urile în trei: de sunat azi, de hrănit cu conținut, nepotrivit.
- Modelul statistic apare doar după câteva sute de lead-uri cu rezultat cunoscut.
- Lead-urile mari merg direct la om.

### 17.6 Programări

- Modul propriu, simplu: tipuri de întâlnire, sloturi, confirmare, invitație de calendar pe email, reamintiri.
- Sincronizare opțională cu un calendar extern.
- Fără un serviciu separat de programări: ar consuma memorie pentru o funcție mică.

### 17.7 CRM minimal, integrat

- **Obiecte:** firme, contacte, lead-uri, oportunități, activități, sarcini.
- **Etape:** nou, calificat, apel programat, ofertă trimisă, câștigat, pierdut cu motiv.
- **Consimțământ:** fiecare contact are sursa, temeiul contactului și istoricul consimțământului.
- **Igienă:** J4 unește duplicatele și creează sarcini de urmărire.
- **Oferte:** J5 scrie oferta din pachete și din audit. Tu o aprobi.
- **Export:** complet, în orice moment.

### 17.8 Inbox social

| Tip de mesaj | Ce face platforma | Cine decide |
| --- | --- | --- |
| Întrebare cu răspuns în registrul de fapte | Răspunde sau propune răspuns | După nivelul de autonomie |
| Cerere de preț sau de ofertă | Răspunde din catalog, trimite linkul potrivit, creează lead | După nivelul de autonomie |
| Laudă | Mulțumește scurt | Automat de la L2 |
| Critică sau reclamație | Nu răspunde singură; pregătește contextul și o variantă de răspuns | Om |
| Subiect sensibil: sănătate, juridic, bani | Nu răspunde singură | Om |
| Spam, înșelătorie, limbaj abuziv | Ascunde și înregistrează | Automat, cu eșantion verificat |
| Mesaj neclar | Pune o întrebare de clarificare | Automat de la L2 |

Reguli:

- Platforma respectă fereastra de mesagerie a fiecărei rețele. Pe Instagram: 24 de ore de la ultimul mesaj al persoanei și un singur răspuns privat la un comentariu, în 7 zile.
- Prelungirea ferestrei prin eticheta de „agent uman” este doar pentru răspunsuri scrise de un om.
- Asistentul se prezintă ca asistent AI. Există mereu calea către un om.
- Nu trimite oferte nesolicitate și nu insistă după un refuz.
- Criticile nu se șterg. Se ascund doar spamul, înșelătoriile și abuzul.
- Timp-țintă de răspuns la întrebările simple: sub 15 minute, în program \[I\].

### 17.9 Legătura cu restul sistemului

- Întrebările frecvente din inbox devin subiecte de conținut și fapte noi de cerut clientului.
- Obiecțiile intră în insightul de public.
- Lead-urile câștigate și pierdute, cu motiv, intră în învățare.
