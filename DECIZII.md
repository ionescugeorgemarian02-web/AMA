# Fișierul de decizii

Hotărârile luate pe parcurs, în ordine cronologică. Deciziile de arhitectură au fișier propriu în `docs/adr/`.

## De hotărât de proprietar (F0.1)

| Decizie | Stare | Valoare |
| --- | --- | --- |
| Nișa-pilot | **deschisă** | – |
| Pachetul-pilot | **deschisă** | – |
| Numele agenției | **deschisă** | – (în cod se folosește provizoriu „AMA”) |

## Decizii luate

### D-001 (2026-11-11) — Construim întâi pe git, VPS-ul vine la final

- **Context:** planul (secțiunea 23) cere VPS măsurat (F0.4) și staging înainte de F1.
- **Hotărâre (proprietar):** platforma se construiește și se validează în repo, capitol cu capitol; migrarea pe VPS se face o singură dată, la final.
- **Consecințe:** criteriile „Gata când” care cer staging, telefon sau servicii externe se verifică prin teste automate în CI și local. Ce rămâne de verificat pe VPS se adună în `docs/specs/STARE.md`, la „De verificat la migrare”. Pașii F0.3–F0.8 (inventar, VPS, cereri de aprobare, juridic, conturi) rămân ai proprietarului și curg în fundal.

### D-002 (2026-11-11) — O cerere de integrare pe fază

- **Context:** planul spune „un pas = o ramură = o cerere de integrare”.
- **Hotărâre:** până la migrare, o fază (capitol) = o cerere de integrare, cu un commit pe pas. Validarea proprietarului se face la poarta fazei.
- **Consecințe:** revizuirea „doi ochi diferiți” (24.4) se face pe fază: un model scrie, alt model revizuiește diferența față de specificație.

### D-003 (2026-11-11) — Unelte de lucru

- Manager de pachete: `uv`, cu `uv.lock` (versiuni exacte și hash-uri). Python 3.13 în imagini și CI (cerința este ≥ 3.12).
- Acces sincron la bază (SQLAlchemy 2 + psycopg 3): mai simplu de izolat pe client și compatibil cu biblioteca de workflow-uri.
- Scanarea repo-ului după chei scăpate: `detect-secrets`; vulnerabilități: `pip-audit`. Ambele rulează în CI, fixate în `uv.lock`.

### D-004 (2026-11-12) — Bugetele de modele pe client: consum din contoare proprii, P1 cu plafon

- **Context:** 8.5 cere bugete pe client și spune „P0 și P1 au cotă garantată; P2 și P3 se amână la epuizare; P0 continuă”, dar nu spune ce se întâmplă cu P1 peste buget.
- **Hotărâre (adoptată, D-007):** consumul se ține în contoare proprii (nu se citește din jurnal: jurnalul se scrie după apel, deci nu este corect la concurență). P0 nu este atins niciodată; P1 continuă până la 1,5 × bugetul (configurabil), apoi se amână; P2 și P3 se amână la atingerea bugetului. Valorile implicite de buget sunt de pornire, nemăsurate.
- **Consecințe:** `gateway.Amanat(pana_la)` cu momentul resetării (miezul nopții UTC, ora este setare). Se revizuiește după primele luni de consum real.

### D-005 (2026-11-12) — Trei compartimente adăugate Creierului în F4: `brief`, `insight_piata`, `strategie`

- **Context:** `docs/10` §10.1 are zece compartimente. Brieful de onboarding (F4.4), harta pieței și brieful de insight (F4.10) și strategia pe 90 de zile
  (F4.11) cer același regim ca restul Creierului: versiuni, sursă obligatorie, aprobare de om, citire „la o dată”, diferență între versiuni.
- **Hotărâre (adoptată, D-007):** se adaugă trei compartimente ca date (`app/creier/compartimente.py`), fără a le schimba pe cele zece. Nu se creează tabele paralele.
- **Consecințe:** ecranul „Creierul de brand” (F4.8) le arată împreună cu celelalte; `tests/unit/test_creier_compartimente.py` numără 13 și păstrează verificarea
  celor zece din 10.1. Documentul 10.1 se actualizează odată cu poarta F4 (propunere).


### D-006 (2026-11-13) — Faza F5: severitatea hotărăște unde merge un eșec; conținutul livrabilului provizoriu; reguli în TOML

- **Context:** `docs/09` spune „un eșec critic blochează” (9.2) și „un livrabil blocat critic intră în carantină” (9.8), iar 7.3 cere cel mult 2 reparații. Nu spune
  ce eșec merge la reparație și ce eșec la carantină. Nu există încă tabel de conținut (F6) și nici bibliotecă YAML în dependențele de rulare.
- **Hotărâre (adoptată, D-007):** (1) orice `esec` blochează și oprește cascada; severitatea `majora` = reparabil (autorul primește
  instrucțiunea, cel mult 2 runde, apoi om), `critica` = nu se repară prin rescriere (nișă refuzată, injecție) → carantină; avertismentele se numără în puncte (minoră 1,
  majoră 2), peste `AMA_VALIDARE_PRAG_AVERTISMENTE` (4, de pornire) livrabilul cere aprobarea unui om. (2) Până la F6, `livrabile_continut` ține versiunile de conținut ale
  livrabilului (text + câmpuri pe canal + active); F6 îl refolosește. (3) Pachetele de reguli (F5.4) sunt fișiere TOML (`tomllib`, bibliotecă standard), nu YAML:
  nicio dependență nouă.
- **Consecințe:** F5.10 construiește ieșirea din carantină; un eșec `critica` nu intră în bucla de reparație. O eventuală schimbare (eșecurile critice reparate
  întâi) se face într-un singur loc, `app/validare/agregare.py`, cu decizie nouă în acest fișier.

### D-007 (2026-11-13) — Agentul de cod decide; nimic nu rămâne „de confirmat de proprietar”

- **Context:** pașii lăsau hotărâri „de confirmat de proprietar” sau „rămâne la proprietar”, iar unii pași păreau să aștepte o aprobare
  care nu ține de cod.
- **Hotărâre (proprietar):** toate deciziile le ia agentul de cod: alege cea mai bună soluție, o aplică, o documentează aici sau în
  specificația pasului și continuă. Nu lasă nimic „de confirmat de proprietar” și nu sare peste pași. Singurele excepții sunt cele care
  cer tehnic resurse externe (chei de API, conturi de platformă, VPS): acestea stau la „De verificat la migrare” (`docs/specs/STARE.md`),
  iar tot ce depinde de ele se construiește și se testează cu simulări. Mecanismele pentru oamenii agenției (etichetare umană, promovarea
  exemplelor în setul de aur, aprobări) sunt funcții ale produsului: se construiesc complet, dar nu sunt condiții pentru a închide pașii.
- **Consecințe:** D-004, D-005 și D-006 sunt adoptate (nu mai sunt propuneri). În `docs/specs/STARE.md` starea fiecărui pas spune ce este
  verificat local și ce depinde de resurse externe, nu ce „așteaptă proprietarul”.

### D-009 (2026-11-14) — Colectorul de metrici: cititori separați, 10 minute, intervalul ratat rămâne ratat

- **Context:** `docs/07` §7.2 cere metrici la 1 oră, 24 de ore, 72 de ore, 7 și 28 de zile, dar nu spune ce se întâmplă când o citire
  întârzie sau lipsește, nici unde stă citirea față de conectorii de publicare. Două sesiuni lucrează în paralel (F9 și F10).
- **Hotărâre (D-007):** (1) citirea metricilor stă în cititori separați (`app/connectors/metrici/`), chemați prin ușa executorului;
  conectorii de publicare nu se modifică. (2) Jobul rulează la 10 minute, ca citirea de la 1 oră să întârzie cel mult 10 minute.
  (3) Un interval se citește doar cât e „deschis” (până la intervalul următor; ultimul, încă 7 zile [I]); după aceea rândul e `ratat`,
  fără cifre. (4) Cifra pe care platforma nu o dă nu se scrie (nu devine zero). (5) Canalele fără citire prin API primesc cifre
  introduse de om, marcate `manual`, care nu pot înlocui o citire prin API.
- **Consecințe:** rapoartele (F10.5) și învățarea (F11) pot avea încredere că o cifră de la „24 de ore” a fost citită în fereastra ei.
  Verificarea de completitudine (`colector.completitudine`) arată câte intervale lipsesc. Grația de 7 zile se revizuiește pe date reale.


### D-008 (2026-11-17) — Reclamele (F13): adaptoare peste platforme simulate, efectele prin „outbox”-ul de sistem

- **Context:** F13 cere conturi reale Meta și Google Ads, bugete reale, Claude ca Consiliu și o campanie reală de 14 zile.
  Nimic din acestea nu există încă (aprobări, carduri, conturi; D-001, D-007).
- **Hotărâre (D-007):** (1) fiecare platformă are un adaptor în `app/connectors/reclame/` (citire și scriere), chemat doar prin
  ușa executorului (`app/operare/efecte/reclame.py` pentru citire, efectele de sistem de tip `reclama` pentru scriere);
  testele rulează pe Marketing API și Google Ads API simulate (`tests/platforme/`), care vorbesc HTTP adevărat.
  (2) Scrierile la platformă refolosesc `efecte_sistem` (cheie de idempotență, încercări, oprirea pe client) plus oprirea
  `reclame`; nu se face un al doilea executor. (3) Banii se țin în subunități întregi (bani). (4) Planul media (I1), gardianul
  (I3), anomaliile (I6) și testele creative (I4) sunt reguli deterministe; modelul (prin gateway) scrie doar ipotezele
  Strategului și răspunsul Consiliului în modul API. (5) Campania reală de 14 zile și poarta pe campanie reală devin o simulare
  accelerată documentată (ceas controlat), cu tot ce e real trecut la „De verificat la migrare”.
- **Consecințe:** nicio schimbare nu ajunge la platformă fără gardian și fără executor; trecerea pe conturi reale înseamnă
  `AMA_RECLAME_CONECTORI`, tokenuri în `publicare_conturi` și verificarea formelor reale ale API-urilor.

### D-010 (2026-11-17) — Gardianul de buget: ce e scutit și cât de larg oprește urgența

- **Context:** `docs/16` §16.4–16.5 dau regulile, dar nu spun cum se tratează pauza, anularea, decizia directă a proprietarului
  sau cât de mult oprește o anomalie.
- **Hotărâre (D-007):** (1) plafoanele (pe campanie, zilnic, lunar proiectat) se aplică oricărei schimbări care pornește sau mărește
  cheltuiala, indiferent de sursă; peste plafon = refuz cu „cere aprobarea clientului”. (2) Regulile de ritm (20%/zi, 48 h de
  așteptare, 5 schimbări automate pe zi) se aplică surselor automate și Strategului/Consiliului; anularea și decizia directă a
  proprietarului în panou sunt scutite. (3) Pauza și scăderea de buget trec mereu, inclusiv sub oprire. (4) O anomalie pe orice
  cont pune oprirea globală `reclame` și pauza pe toate campaniile active (16.5: „totul pe pauză”); repornirea e manuală, campanie
  cu campanie. (5) Fără token nici pauza nu pleacă: anunțul critic cere oprirea manuală din managerul de reclame.
- **Consecințe:** o anomalie la un client oprește și campaniile celorlalți; se revizuiește când sunt mai mulți clienți cu reclame.

### D-012 (2026-11-17) — Consiliul: modul manual asistat, cu API-ul în spatele aceleiași uși

- **Context:** `docs/07` §7.6 dă patru moduri de conectare a lui Claude ca Consiliu și recomandă începutul manual.
- **Hotărâre (D-007):** modul implicit e **manual asistat** (`AMA_RECLAME_CONSILIU_MOD=manual`): dosarul (cifre, opțiuni cu
  acțiunile lor, întrebări, formatul JSON al răspunsului) se copiază în Claude, iar răspunsul se lipește în panou. Consiliul
  alege o opțiune; acțiunile sunt ale opțiunii, nu inventate de model. Importul făcut de om aprobă propunerile; în modul API
  (`intreaba_api`, prin gateway) propunerile așteaptă omul. Plafon: 8 dosare pe lună [I]; peste el dosarul se amână.
- **Consecințe:** Claude rămâne în afara căii critice (ADR-06); trecerea la API cere doar profilul real și creditul lunar.

### D-014 (2026-11-17) — Campania reală de 14 zile și poarta F13 devin o simulare accelerată

- **Context:** F13.10 cere o campanie reală pe contul agenției, cu buget mic, timp de două săptămâni; poarta F13 cere oprirea de
  urgență testată pe o campanie reală. Nu există încă cont de reclame aprobat, card sau acces la API (D-001, D-007).
- **Hotărâre (D-007):** amândouă rulează ca simulare accelerată (`tests/integration/lant_reclame.py`): platforma de reclame e
  simulată (HTTP real, cheltuială zilnică cu ritm variabil sub buget), restul e platforma reală (plan, verificare, executor, gardian,
  supraveghere, teste creative, Strateg, site-ul cu vizite și cereri de audit), cu ceasul controlat. Plafoanele de probă: 100 lei/zi,
  3.000 lei/lună, 80 lei pe campanie [I].
- **Consecințe:** criteriile se verifică în CI; campania reală, cu bani reali, rămâne la „De verificat la migrare”, cu același raport
  dublu și aceeași verificare de plafoane (`raport.depasiri`).

## D-C01 — Shopify simulat și date ale magazinului izolate (2026-11-17)

Sesiunea C: Shopify Admin API rămâne exclusiv contract HTTP local (MockTransport obligatoriu),
până la migrarea pe VPS. Datele cumpărătorilor sunt ale tenantului, nu se importă automat în CRM-ul
agenției din F12. Tokenul este criptat cu primitivele existente și AAD tenant + domeniu magazin.
Autorizarea consumă starea înainte de schimb; un răspuns întârziat nu înlocuiește autorizarea nouă.
Revizuirea autentificării/izolării de alt model rămâne condiție de integrare pentru sesiunea A.

## D-C02 — Atribuire Shopify deterministă (2026-11-17)

UTM are prioritate față de codurile de reducere mapate explicit de consumator; lipsa sursei este
„necunoscut”. Luna este UTC, monedele nu se adună. Anulările nu contribuie, rambursările reduc netul
până la zero. Atribuirea declară sursa observată, nu dovedește cauzalitate. Raportul lunar consumă API-ul
comerțului; modificarea F10 este lăsată sesiunii proprietare a modulului (cerere în COORDONARE).
### D-016 (2026-11-17) — Modul local pe PC-ul proprietarului

- **Context:** proprietarul vrea să încerce platforma pe calculatorul lui (Windows cu WSL2 sau Mac), înainte de VPS.
- **Hotărâre (D-007):** `infra/compose/local.yml` construiește imaginea din `Dockerfile` (fără registru, fără Caddy),
  publică aplicația doar pe `127.0.0.1:8000`, rulează cu `AMA_ENV=dev` și cu toți conectorii pe simulatoare. Imaginea
  aplicației nu are amprentă (e construită local), deci numele ei vine dintr-o variabilă (`${AMA_IMAGE_LOCAL}`), excepție
  admisă de `check_pins`; Postgres rămâne fixat pe amprentă. O singură cheie LLM opțională (OpenRouter); fără ea, mod simulat
  (gateway-ul refuză vizibil sarcinile cu model). Datele demo: `python -m app.demo.populare` (idempotentă, refuzată în
  staging/producție).
- **Consecințe:** `make local-up / local-down / local-reset`, runbook `docs/runbooks/rulare-locala.md`.


### D-018 (2026-11-17) — Trasabilitatea totală: un singur jurnal de urme, append-only

- **Context:** proprietarul cere ca orice componentă (agenți, Creier, gateway, porți, validare, efecte, conectori, aprobări,
  bugete) să lase o urmă cu cine/ce/de ce, cost, durată, rezultat și legătura cu fluxul-părinte, iar o analiză lunară să
  explice fiecare eșec până la evenimentul-sursă.
- **Hotărâre (D-007):** tabelul `urme` (migrarea `0076`), separat de `jurnal_audit`/`jurnal_evenimente` (care rămân):
  fir = `correlation_id` (HTTP, job, `corelare`), cauză = urma-părinte din context (`span`). Doar adăugare (drepturi +
  declanșator), RLS pe client. Scrierea nu strică niciodată acțiunea (punct de salvare sau tranzacție proprie, „cel mai bun
  efort”). Fără FK spre `clienti`. Rezumate mascate (secrete, email, telefon, CNP, IBAN, card).
- **Consecințe:** pașii FT.2–FT.5 leagă componentele, calculează indicatorii, analiza lunară și ecranul; retenția și
  partiționarea pe VPS rămân de stabilit la migrare.
- **Completare (poarta FT):** la ștergerea unui client (`app/db/stergere.py`), `urme` se păstrează ca `jurnal_audit`
  (rezumate deja mascate; urma de final a jobului de ștergere se scrie oricum după ștergere). Un fir fără context
  explicit nu se mai lipește de firul de execuție: `span` își pune firul doar cât ține, apoi îl scoate.
