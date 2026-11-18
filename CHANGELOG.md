# Jurnalul de schimbări

Format: o intrare pe pas, cea mai nouă sus.

## Nelansat

### F16.5 — Generator video extern
- `app/media/video_extern.py` (adaptor oprit implicit, inserturi 3–6 s, drept comercial fără filigran, cost rezervat sub zăvor, plafon lunar pe client), migrarea `0107` (`video_generari`), setările `AMA_VIDEO_EXTERN_*`.

### F16.4 — Voce proprie antrenată
- `app/media/voce_proprie.py` (acord, antrenare o dată, adaptorul TTS `proprie`, revocare care blochează narațiunile), migrarea `0106` (`voce_consimtaminte`, `voce_modele`, RLS); `voce.sintetizeaza` cu profil dat.

### F16.3 — Localizare în engleză
- `app/localizare` (catalog, limba din cerere, `t` în șabloane), `POST /portal/limba`, portalul (meniu, Acasă) în engleză; `clienti.limba` (migrarea `0105`); instrucțiunea de limbă pentru autori; G1/G10 pe limba conținutului (`validare/limba_en.py`); editorul cu ghilimelele limbii.

### F16.2 — Canale noi: Pinterest, Google Business Profile, Threads
- `app/connectors/publicare/{pinterest,google_business,threads}.py` (contractul F9.1, SIMULATE), înregistrate în registru; migrarea `0104` (aprobările `in_test`); sloturi, domenii asistate, limite G1.

### F16.1 — Formatul C, grafică animată
- `app/media/formatul_c.py` (scene ofertă/cifră/anunț în culorile brandului, cadre Pillow + FFmpeg local, HTML-ul scenei pentru HyperFrames SIMULAT), formatul `C` în lista de montaj.

### Poarta F12 — CRM, email, inbox
- `tests/integration/test_poarta_f12.py`, `docs/specs/F12-poarta.md` (audit → secvență → calificare → apel programat, cap-coadă pe simulare); anularea programării cere CSRF dublu-trimis; ordinea livrării nu mai contează în testele secvenței.

### F12.10 — Asistentul de suport din portal
- `app/portal/suport.py` + `/portal/suport` (răspunsuri D din livrabile, cont și exportul Shopify `comert.vanzari.pentru_crm`; escaladare), ecranul `/crm/suport`, migrarea `0103` (`portal_suport`, RLS pe tenant).

### F12.9 — Lista de conturi-țintă
- `app/crm/conturi_tinta.py` (sursă publică SIMULATĂ, filtrul de date personale, mini-audit, argumente), ecranul `/crm/tinta`, migrarea `0102`.

### F12.8 — Răspunsuri și escaladare
- `app/crm/raspunsuri.py` (tabelul 17.8, ferestrele, dezvăluirea AI, escaladarea, ascunderea doar a spamului), efectul de sistem `mesaj_social`, răspunsurile din `/crm/inbox`, migrarea `0101`.

### F12.7 — Inboxul social
- `app/crm/inbox.py` (canale aprobate, citire prin `app/operare/efecte/inbox.py`, clasificare pe reguli, jobul `crm.inbox`), `app/connectors/inbox` (SIMULAT), ecranul `/crm/inbox`, migrarea `0100`.

### F12.6 — Generatorul de oferte
- `app/crm/oferte.py` (compunere din audit și planuri, verificări, aprobare/respingere), ecranul `/crm/oferte` și butonul de pe fișă, `site.audit.raport_pentru_lead`, migrarea `0099` (`crm_oferte`).

### F12.5 — Programări
- `app/crm/programari.py` (grila de sloturi, rezervarea, invitația .ics, reamintirile `crm.reamintiri`, anularea), `app/site/programare_web.py` + șabloanele `site/programare*.html`, migrarea `0098` (`crm_programari`), atașamente în conectorul de email.

### F12.4 — Calificare și scor
- `app/crm/calificare.py` (4 întrebări, regula de scor, grupele, lead mare → om, urme), migrarea `0097` (`crm_calificari`, tipuri noi de activitate), grupa pe fișa din `/crm`.

### F12.3 — Secvența de după audit
- `app/crm/secventa.py` (înscriere la confirmarea auditului, 4 pași prin `crm.email.trimite`, jobul orar `crm.secventa`, urme), migrarea `0096` (`crm_secvente`), `tests/integration/utile_crm.py` (ordinea comună de curățare).

### Poarta F15 — Întărire și lansare
- `tests/integration/test_poarta_f15.py`, `docs/specs/F15-poarta.md` (cap-coadă pe simulare: avarie, restaurare, pilot, studii, lista 25.5).

### F15.6 — Lansarea comercială
- Lista de go-live din docs/25 §25.5 (`app/lansare/golive.py`, ecranul `/lansare/go-live`), calculată din bază, urme și fișiere unde se poate; studiile de caz (`app/lansare/studii.py`, șablonul `docs/sabloane/studiu-de-caz.md`, `/site/studii-de-caz`); rezultatul avariei pe staging (`app/lansare/cli.py`); urma zilnică `resurse / verifica`; migrarea `0083`.

### F15.5 — Pilotul cu trei clienți
- `app/lansare/` (înscrierea la L1 cu preț de pilot, feedback săptămânal, aprobarea din prima și incidentele critice din urme, poarta, raportul săptămânal `lansare.pilot_saptamanal`), ecranul `/lansare/pilot`, migrarea `0082`.

### F15.4 — Juridic (ciorne)
- `docs/juridic/` (contract de servicii, acord de prelucrare, termeni, confidențialitate, cookie-uri), paginile `/site/legal/...` generate din ele cu marcajul „necesită revizuirea avocatului”, pagina nouă `/site/legal/contract`.

### F15.3 — Exercițiul de restaurare completă
- `scripts/exercitiu_restaurare.py` (backup -> mediu curat -> restaurare -> verificare, cronometrat față de 4 h), `tests/avarie/test_restaurare.py` (scenariul A14), runbook-ul `restaurare.md` secțiunea D.

### F15.2 — Revizuire de securitate
- Revizie pe alt model (Sonnet, doar citire), `docs/specs/F15.2-revizie.txt`. Reparate: plafonul de reclame la aprobări concurente (gardianul reaplicat sub încuietoare), încuietoarea pe efectele de sistem, SSRF pe pagina reclamei (`app/reclame/pagina.py`), oprirea pe cont la pagina căzută, antetele proxy doar din rețeaua `edge`, plățile sosite în altă ordine și deduplicarea atomică, parola la ștergerea datelor, credențialele proprietarului doar în worker. Colecția `tests/atacuri/`.

### F15.1 — Teste de avarie
- `tests/avarie/` (catalogul scenariilor din docs/25 §25.3, raportul pe scenarii, teste noi: baza repornită, disc 85%, memorie la limită, randarea reluată, P0 pe culoare ocupate, webhook dublu, politica de repornire), `scripts/avarie.sh`. `app/operare/resurse.py` și jobul `operare.resurse` (la 5 minute); randarea amânată la disc plin / memorie la limită și cu director de lucru propriu, curățat la reluare. D-022.

### Poarta F14 — Învățare, a doua treaptă
- `tests/integration/test_poarta_f14.py`, `docs/specs/F14-poarta.md`; clientul intern al evaluărilor se creează într-o tranzacție proprie (consumul gateway-ului se scrie separat); verdictul testului formal spune câte observații a folosit (`n_folosit`); gărzile contextului de agenție cunosc modulele F14.

### F14.6 — Consolidarea nocturnă a memoriei
- `app/invatare/consolidare.py` (unirea lecțiilor duplicate, scoaterea din rotație după 90 de zile fără folosire, jobul nocturn `invatare.consolidare`). Fără migrare.

### F14.5 — Scorul de lead și riscul de plecare, ca modele
- `app/invatare/modele_client.py` (exemplele din CRM, regulile simple ca referință, modelul folosit doar dacă le bate, jobul săptămânal `invatare.modele_client`). Fără migrare.

### F14.4 — Teste A/B formale
- `app/invatare/teste_ab.py` (declarare cu mărimea eșantionului, eșantion fix, Welch, p, interval, jobul `invatare.teste_ab`), `teste_ab`, `teste_ab_observatii`, `promovari.test_ab_id` (migrarea `0081`); producția unei promovări se măsoară cu un test formal față de control.

### F14.3 — Predictorul de performanță
- `app/invatare/predictiv.py` (gradient boosting cu cioturi, AUC, bootstrap pereche, pragul de date), `app/invatare/predictor.py` (șansa de succes pe client și canal, jobul săptămânal `invatare.predictor`), `modele_predictive` (migrarea `0080`).

### F14.2 — Umbră, canar, promovare, revenire
- `app/invatare/promovare.py` (rutarea deterministă, umbra pe 20 de livrabile, canar 10%, producție 90% cu control 10%, câștigul măsurat față de control, revenirea dintr-o atingere și automată), jobul zilnic `invatare.promovari`, `promovari` și `promovari_observatii` (migrarea `0079`).

### F14.1 — Optimizatorul de prompturi
- `app/invatare/optimizator.py` (set de aur, antrenare/test, scor compus calitate × conformitate, căutare reflexivă, candidat ca ciornă în registru, raport), promptul `invatare.reflectie`, setul `evaluare/optimizare/continut.hookuri.jsonl`, jobul nocturn `invatare.optimizator`, `optimizari` (migrarea `0078`). CI: `timeout-minutes` 45 la jobul `check`.

### Poarta FT — Trasabilitate totală
- `tests/integration/test_poarta_ft.py` (o lună simulată prin motor, conector HTTP, producție și poarta Creierului), `docs/specs/FT-poarta.md`; cauza probabilă include amânările (429); firul nu mai rămâne agățat în contextul firului de execuție; `urme` se păstrează la ștergerea unui client (D-018). Fără migrare.

### FT.5 — Ecranul „Urme” și exportul
- `/urme` (raportul lunii, generarea, firul), exporturile `/urme/export.json` și `/urme/export.csv`, legătura din meniu (proprietar). Fără migrare.

### FT.4 — Analiza lunară automată
- `app/operare/urme/analiza.py` (bine/prost, regresii, costuri, porți picate, motive de respingere, lanțul fiecărui eșec până la sursă), `urme_rapoarte`, jobul lunar `urme.analiza_lunara`. Migrarea `0077`.

### FT.3 — Indicatorii pe componentă
- `app/operare/urme/indicatori.py`: volum, rezultate, rata de eșec, cost pe unitate, durate p50/p95, coduri frecvente, pe interval și client. Fără migrare.

### FT.2 — Firul de corelare și urmele componentelor
- firul trece din cerere în job și în joburile-copil (motor), urme pentru gateway, porțile cascadei și ale Creierului, conectori HTTP, aprobări, gardianul de buget, oglinda evenimentelor de domeniu. Fără migrare.

### FT.1 — Jurnalul unic de urme
- `app/operare/urme` (`emite`, `inregistreaza`, `span`, `corelare`, rezumatul fără secrete și date personale), tabelul `urme` doar cu adăugare, RLS, D-018. Migrarea `0076`.

### Modul local
- `infra/compose/local.yml`, `infra/env/local.env.example`, `make local-up/local-down/local-reset`, `app/demo` (popularea cu „Cafeneaua Zorilor”), runbook `docs/runbooks/rulare-locala.md`, D-016. Fără migrare.

### Poarta F13
- `tests/integration/test_poarta_f13.py`, `docs/specs/F13-poarta.md`; fișierele reclamelor intră în lista locurilor cu scop de agenție (`tests/unit/test_garzi_db.py`). Fără migrare.

### F13.10 — Campania de probă (simulare accelerată)
- `app/reclame/raport.py` (raportul dublu platformă/site, verificarea plafoanelor), ecranul `/reclame/cont/<id>/raport`, simularea de 14 zile, D-014. Fără migrare.

### F13.9 — Testarea creativurilor
- `app/reclame/teste.py` (probabilitatea de a fi cea mai bună, date minime, oprirea pierzătoarelor, câștigătoarea în scalare), propunerea `adauga_anunt`. Migrarea `0075`.

### F13.8 — Verificarea reclamelor înainte de lansare
- `app/reclame/verificare.py`, pachetul `rulepacks/reclame.toml`, blocarea la construcție și reverificarea la activare. Fără migrare.

### F13.7 — Consiliul
- `app/reclame/consiliu.py` (dosarul, importul deciziei, plafonul lunar, modul API), ecranul `/reclame/consiliu`, promptul `reclame.consiliu.v1`, D-012. Migrarea `0074`.

### F13.6 — Strategul și înregistrările de decizie
- `app/reclame/strateg.py` (reguli pentru cele patru ieșiri, ipotezele prin gateway, propunerea de pauză), promptul `reclame.strateg.v1`, jobul `reclame.strateg`. Migrarea `0073`.

### F13.5 — Gardianul de buget și oprirea de urgență
- `app/reclame/{gardian,urgenta}.py` (plafoane, ritm, anomalii, oprirea globală cu pauza tuturor campaniilor și anunț critic), supravegherea după fiecare citire. D-010. Fără migrare.

### F13.4 — Constructorul de campanii, propunerile de schimbare și executorul
- `app/reclame/{constructor,propuneri}.py`, scrierea în adaptoarele Meta și Google, executantul efectelor `reclama` (în `efecte/sistem.py`, prin adăugare), panoul cu activare, aprobare și anulare. Migrarea `0072`.

### F13.3 — Planificatorul media
- `app/reclame/plan.py` (planul determinist, verificarea, decizia), secțiunea „Planuri media” din `/reclame/cont/<id>`. Migrarea `0071`.

### F13.2 — Citirea rezultatelor Google Ads
- Adaptorul `app/connectors/reclame/google.py` (GAQL `searchStream`), setările Google Ads, Google Ads API simulat. Fără migrare.

### F13.1 — Citirea rezultatelor Meta
- `app/reclame` (conturi de reclame cu plafoane, rezultate zilnice, citire orară `reclame.citire`), conectorul `app/connectors/reclame/meta.py` prin ușa `app/operare/efecte/reclame.py`, ecranul `/reclame`. Migrarea `0070`.

### F12.2 — Email către abonați
- `app/crm/email.py` (ușa de trimitere: suprimare, matrice pe țări, consimțământ, praguri, limită zilnică, domeniu), dezabonarea dintr-un clic (`/site/dezabonare/<jeton>`), verificarea suprimării în executorul de efecte, ecranul `/crm/email`. Migrarea `0095`.

### F12.1 — CRM-ul minimal
- `app/crm` (firme, contacte, lead-uri pe etape, istoricul consimțământului, unirea duplicatelor, sarcini de urmărire, export), ecranul `/crm`, jobul `crm.igiena`; lead-ul confirmat din formularul de audit intră în CRM. Migrarea `0094`.

### F11.6 — Ecranul „Învățare” și poarta F11
- Ecranul `/invatare` (lecții de curatoriat cu dovezi, aprobare, respingere, anularea promovării, înghețare, registrul de experimente, alegerea adaptivă); `curator.istoric`. Poarta F11: `docs/specs/F11-poarta.md`. Fără migrare.

### F11.5 — Constituția
- `invatare.constitutie` (fluxul de învățare marcat, o promovare pe săptămână, înghețarea, indicatorii de gardă), declanșatorul `ama_fara_invatare`, garda `scripts/check_invatare.py` în `make guards`. Migrarea `0093`.

### F11.4 — Registrul de experimente
- `invatare.experimente` (declarare, regula de oprire, evaluare zilnică, oprire de către om), jobul `invatare.experimente`. Migrarea `0092`.

### F11.3 — Alegerea adaptivă
- `invatare.alegere` (bandit Thompson: explorare 15%, uitare în 90 de zile, pornire de la media nișei), preferința de tipar la alegerea hook-ului (`continut.scriere.inregistreaza_preferinta_tipar`).

### F11.2 — Curatorul și playbook-ul
- `invatare.curator` (aprobare, respingere, retragere, contoare, limita de 40, retragere automată), lecțiile active în promptul autorului (`continut.scriere.inregistreaza_adaos_context`), `lectii_folosite`. Migrarea `0091`.

### F11.1 — Reflectorul
- `invatare.reflector` (lotul închis, propuneri de lecții cu dovezi din rezultate, verdicte și decizii), tabelele `loturi_reflectie` și `lectii`. Migrarea `0090`.

### F10.8 — Analistul de reclame ale concurenței
- `cercetare.reclame_concurenta` (Meta Ad Library, unghiuri pe reguli, harta unghiurilor, reclamele de durată, spații libere), statutul de sursă `meta_ad_library` (G7 blochează textele apropiate), jobul săptămânal `cercetare.reclame`, ecranul `/analiza/concurenta`, setarea `AMA_META_AD_LIBRARY_TOKEN`. Migrarea `0061`.

### F10.7 — Cercetătorul de tendințe
- `cercetare.tendinte` (surse oficiale, profil de nișă, fișe cu dovezi, inbox → fișă și propunere de calendar), jobul zilnic `cercetare.tendinte`, ecranul `/analiza/tendinte`, setarea `AMA_YOUTUBE_API_KEY`. Migrarea `0060`.

### F10.6 — Analiza de trafic proprie
- `analiza.trafic` (pâlnia vizite cu acord → cereri de audit → clienți), ecranul `/analiza/trafic`.

### F10.5 — Raportul lunar complet
- `analiza.raport_cifre` (cifrele lunii, frazele deterministe, controlul „G2 pe cifre”); `raport_lunar` și șablonul din portal arată cifrele măsurate.

### F10.4 — Tablouri de bord și scor de sănătate
- `analiza.sanatate` (semnalele de risc din 4.10, scorul, indicatorii din 4.13), ecranul `/analiza/clienti`.

### F10.3 — Legarea de etichete
- `analiza.etichete` (tipar de hook, format, pilon, unghi, slot local, recompensa de la 72 de ore; grupare și sortare), ecranul `/analiza/etichete`. Migrarea `0059`.

### F10.2 — Curba de retenție YouTube
- `analiza.retentie` (validare, rezumat, linia SVG, o curbă pe clip, citită la 72 de ore, 7 și 28 de zile), cititorul `CititorRetentieYoutube` (YouTube Analytics), ecranul „Rapoarte și analiză” (`/analiza`, `/analiza/livrabil/<id>`: cifrele pe intervale, curba, introducerea manuală a cifrelor). Migrarea `0058`.

### F10.1 — Colectorul de metrici
- `analiza.colector` (citiri la 1 oră, 24 de ore, 72 de ore, 7 și 28 de zile; intervale ratate și indisponibile; cifre introduse de om; verificarea de completitudine), jobul `analiza.colector` la 10 minute, cititorii `connectors.metrici` (Facebook, Instagram, YouTube, LinkedIn, TikTok, fals), ușa `efecte.metrici`, tipul `contract.Metrici`. Migrarea `0057`.

### Coordonare — două sesiuni de cod în paralel
- `docs/specs/COORDONARE.md`: repartizarea fazelor, migrările rezervate, regulile pentru fișierele comune, reluarea după limita de utilizare.
### Poarta F9
- Testul de poartă `tests/integration/test_poarta_f9.py`: o postare publică, o singură dată, pe fiecare canal aprobat; canalul neaprobat rămâne pe asistat.

### F9.10 — Ecranul „Publicare”
- `/publicare/canale` (aprobările API, conturile, modul, coada, trecerea pe asistat, reautorizarea) și întoarcerea OAuth `/publicare/autorizare`.

### F9.9 — Site și blog
- `publicare.blog` (articolul F7.10 ca livrabil cu aprobare), `connectors.publicare.blog` (blogul găzduit și WordPress); `seo.articole.scrie(publica=)`.

### F9.8 — Gardianul sănătății conturilor
- `publicare.sanatate` (expirarea tokenurilor, seria de erori → pauză, limitele citite), jobul orar `publicare.sanatate`, `efecte.autorizare.pune_pe_pauza`.

### F9.7 — Planificarea, alegerea canalelor și zilele blocate
- `publicare.programare` (sloturi, frecvență, zile blocate, `publicare.tic` la minut, alegerea drumului API / asistat, trecerea pe asistat); `asistata.pregateste(din_programat=)`. Migrarea `0056`.

### F9.6 — TikTok
- `connectors.publicare.tiktok` (ciornă / postare directă), `publicare.consimtamant`, ecranul de previzualizare și consimțământ `/publicare/api/tiktok/<livrabil>`. Migrarea `0055`.

### F9.5 — LinkedIn
- `connectors.publicare.linkedin` (Posts API, profil pe `linkedin`, pagină de companie pe `linkedin_pagina`, după aprobare).

### F9.4 — YouTube
- `connectors.publicare.youtube` (OAuth Google, încărcare reluabilă, câmpul de conținut sintetic, vizibilitatea după audit, costul în unități), `publicare.cote`. Migrarea `0054`.

### F9.3 — Instagram
- `connectors.publicare.instagram` (container, procesarea clipului, `media_publish`, limita din endpoint), `publicare.linkuri` (linkuri semnate care expiră) și ruta publică `/publicare/fisier/<jeton>`.

### F9.2 — Facebook, pagini
- `connectors.publicare.facebook` (Graph API: OAuth, pagină, publicare, verificare, limite din antete), `publicare.aprobari` (cererile de aprobare cu înregistrarea fluxului), încărcarea la cerere a conectorilor reali (`AMA_PUBLICARE_CONECTORI`). Platformele simulate în `tests/platforme/`.

### F9.1 — Interfața comună de conector
- `connectors.publicare` (contractul, clientul HTTP comun, clasificarea erorilor, conectorul fals), `publicare.canale` (conturi, token criptat, modul efectiv), `operare.efecte.autorizare`. Migrarea `0053`.

### Poarta F8
- Testul de poartă `tests/integration/test_poarta_f8.py`: zece video consecutive, de la script la fișierul final, trec G6, G5 și G11 fără intervenție.

### F8.12 — Formatul E, om real
- Prompterul din portal (`/portal/prompter/<livrabil>`), `media.formatul_e` (tăierea pauzelor, subtitrări, nivel) ca job durabil.

### F8.11 — Proveniență și dezvăluire AI (G11)
- `media.provenienta`: pașaportul fiecărui fișier final, eticheta pe canal, marcajul în fișier, G11. Migrarea `0052`.

### F8.10 — Șabloane grafice și Compozitorul
- `media.sabloane` (identitatea din Creier sau propusă, șase șabloane ca date) și `media.compozitor` (randare cu diacritice corecte, încadrarea textului). Migrarea `0051`.

### F8.9 — Testul de capacitate
- `media.fluxuri` (randarea ca job durabil pe coada `greu`) și `media.capacitate` (raportul față de bugete).

### F8.8 — Controlul media (G6) și auditorul vizual (G5)
- `media.control` (G6 dintr-o singură decodare + ffprobe) și `media.vizual` (G5 din pixeli); montajul respinge videoul care nu trece G6.

### F8.7 — Subtitrări și sunet
- `media.subtitrari` (ecrane de 2–4 cuvinte, evidențiere, zone sigure pe canal, ASS + SRT) și `media.sunet` (muzica atenuată sub voce, −14 LUFS, limitator); muzica simulată cu licență.

### F8.6 — Montajul pentru formatele A și B
- `media.randare` (lista -> graful FFmpeg) și `media.montaj` (pregătire, randare, înregistrare cu licența componentelor). Migrarea `0050`.

### F8.5 — Lista de decizii de montaj și Regizorul
- `media.lista` (schema și validarea listei de montaj) și `media.regizor` (alegerile modelului pe bătăi, momentele din vocea reală); promptul `media.regizor@1`.

### F8.4 — Furnizorul de imagini și biblioteca de active
- `media.licente` (licențe complete pe tip, folosirea doar cu licență, consemnată și impusă de bază), `media.furnizori` (stock și generare în spatele adaptoarelor, simulați), `media.ffmpeg`; EXIF eliminat la încărcare. Dependență nouă: `pillow==12.0.0`. ffmpeg în CI și în imagine. Migrarea `0049`.

### F8.3 — Transcrierea inversă și timpii pe cuvânt
- `media.transcriere`: adaptorul transcriptorului (whisper.cpp, simulat), alinierea cu scriptul, WER pe frază, resinteza o dată și semnalarea.

### F8.2 — Normalizarea textului românesc
- `media.normalizare` (numere, date, ore, sume, procente, unități, abrevieri, web, telefoane, diacritice) și `media.pronuntie` (dicționarul de pronunție pe client). Migrarea `0048`.

### F8.1 — Vocea și licența ei
- `media.voce`: adaptorul motorului de voce (Piper, simulat), profilurile cu licență, narațiunea frază cu frază salvată ca activ `audio` cu statutul licenței; `media.audio` (WAV). Migrarea `0047`.

### Poarta F7
- Testul de poartă `tests/integration/test_poarta_f7.py`: un client de test de la audit la plată și la prima aprobare, prin site, procesator (simulat) și portal.

### F7.10 — Cercetarea SEO și articolele
- Modulul `app/seo`: grupuri de cuvinte-cheie pe intenție, brief SEO, articol în trei pași, lista on-page deterministă, validare și publicare pe blog cu surse.

### F7.9 — Oferta, pâlnia și paginile de captare
- Modulul `app/oferta`: arhitectul de ofertă (D2) și copywriterul de conversie (E3), validarea G2/G3/G9 + un singur apel la acțiune, pagina găzduită `/site/p/<slug>`; `validare.independent` pentru texte care nu sunt livrabile. Migrarea `0046`.

### F7.8 — Raportul lunar, prima formă
- `analiza.raport_lunar`: raportul lunar, prima formă (livrabile și stare, fără metrici), în portal. Migrarea `0045`.

### F7.7 — Export și ștergere
- Exportul complet (ZIP) și ștergerea la cerere a datelor clientului (`portal.date`, `db.stergere`, job durabil), din portal. Migrarea `0044`.

### F7.6 — Facturare
- Modulul `finante.abonamente`: abonamente prin procesator (adaptor, mediu de probă simulat), webhook-uri semnate, perioada de grație și suspendarea; înscrierea din site; abonamentul și facturile în portal. Migrarea `0043`.

### F7.5 — Portalul: materiale și inboxul de tendințe
- Modulul `app/media`: biblioteca de active (verificare după conținut, disc local, sursă) și inboxul de tendințe; ecranul Materiale din portal. Migrarea `0042`.

### F7.4 — Portalul: Creier, calendar, aprobări
- Portalul: Creierul (aprobarea propunerilor de titular), calendarul, aprobările cu previzualizare reală și „Aprobă tot lotul”. `productie.aprobari.cere` alege decidentul: clientul, dacă are un utilizator care aprobă.

### F7.3 — Portalul: cont și onboarding
- Modulul `app/portal`: activarea contului din invitație, Acasă cu bara de progres, interviul din portal; invitația din ecranul de onboarding al agenției; `client_titular` completează onboardingul; clientul care intră pe `/` ajunge în portal. Migrarea `0041`.

### F7.2 — Formularul de audit
- Modulul `site.audit`: auditul gratuit cu opt-in dublu, anti-spam, raport de la motorul de audit (adaptor), lead; ecranul „Leaduri din site”. Efectele externe de sistem (`app/operare/efecte/sistem.py`, tabelul `efecte_sistem`): email și plăți prin aceeași disciplină de outbox. Migrarea `0040`.

### F7.1 — Site-ul complet
- Modulul `app/site`: paginile publice din 19.1 ca date, randate pe server fără JavaScript, banner de acord pentru cookie-uri, analiză de trafic proprie anonimă (doar cu acord), blog, hartă a site-ului, robots, adrese canonice și date structurate. Planurile agenției în `app/finante/planuri.py`. Migrarea `0039` (`site_vizite`, `site_articole`).

### Poarta F6
- Testul de poartă `tests/integration/test_poarta_f6.py`: lanțul complet al producției de text și al publicării asistate, cu acțiunile omului prin panou, și proba accelerată de 14 zile pe două branduri, fără incident critic. Detalii și condițiile rămase în `docs/specs/F6-poarta.md`.

### F6.8 — Proba de două săptămâni (simulată)
- `continut.proba`: proba zi cu zi pe ceasul calendarului, pentru mai multe branduri (producție, decizia omului, publicare asistată), cu verificarea incidentelor critice și rata de aprobare din prima; raportul intră în audit. Rulată accelerat pe două branduri fictive: 14 zile, 0 incidente critice.

### F6.7 — Capturarea feedbackului
- Respingerile (cu motivul standard și fraza omului) devin exemple negative, aprobările (cu ciorna, dacă omul a editat) exemple de aur, automat, în aceeași tranzacție cu decizia; pachetul de context primește exemplele aceluiași tip și canal (`creier.context.construieste(..., exemple=(tip, canal))`), iar brieful și autorii le văd în prompt.

### F6.6 — Publicarea asistată
- Modulul `app/publicare`: pachetul de publicare asistată se pregătește la aprobare (text final cu hashtag-uri, ora recomandată, dezvăluirea AI, pașii obligatorii, cheia de idempotență din 7.3), ecranul `/publicare` cu butonul „Partajează” (Web Share sau copiere) și formularul pentru linkul postării, verificat pe domeniul canalului; livrabilul trece `programat → publicat`. Tabelul `publicari_asistate` (migrarea `0038`).
- `productie.aprobari`: punctul de extensie după decizie (`inregistreaza_dupa_decizie`).

### F6.5 — Adaptorul pe platformă
- Adaptorul pe platformă (E10): din postarea validată, câte un livrabil nou pe canal (Instagram, LinkedIn, TikTok, Facebook), cu lungimi-țintă native verificate determinist împreună cu G1, o cerere de corectură, apoi validarea obișnuită. Tabelul `adaptari` (migrarea `0037`), prompt `continut.adapteaza@1`.

### F6.4 — Scripturi video
- Scenaristul video (E2): scriptul scurt pe bătăi (voce, text pe ecran, vizual, apel la acțiune) pe hook-ul ales de E1 cu limita video de 7 cuvinte; durata estimată determinist din cuvinte, încadrarea la ±15% din țintă, o singură cerere de scurtare / lungire, altfel coada de erori. Prompt `continut.script@1`.

### F6.3 — Hook-uri și postări
- Generatorul de hook-uri (E1, 3–5 variante pe tipare, alegere deterministă, tabelul `variante_hook`, migrarea `0036`), autorul de postări (E4) în lume închisă, editorul determinist (E8, `date/editor.toml`), lanțul `continut.pipeline` și fluxul durabil `continut.produ` (brief → scriere → validare cu ≤ 2 reparații → aprobare după nivelul de autonomie).
- `validare`: sursele de autori de reparații (`autor.inregistreaza_sursa`), punctul de extensie după validare (`ciclu.inregistreaza_dupa_validare`) și nucleele exportate (`probleme_hook`, `probleme_structura`, `extrage_afirmatii`, `corecteaza_sedila`, `propozitii`).

### F6.2 — Autorul de brief
- Autorul de brief (D5): pentru fiecare slot aprobat, pachetul de context la data publicării, faptele permise alese de model doar dintre cele din pachet (aliasuri F1, F2, … rezolvate la intrarea și versiunea din Creier), restul din slot. Tabelul `briefuri` (migrarea `0035`), prompt `continut.brief@1`, fluxul durabil `continut.briefuri`; livrabilul trece `planificat → briefat`.

### F6.1 — Strategul de conținut și calendarul
- Modulul nou `app/continut`: strategul de conținut (D3) propune piloni, formate pe canal și idei din strategia aprobată (prompt `continut.calendar@1`, profilul `strategie`, flux durabil `continut.calendar`); nucleul determinist `calendar.planifica` așază sloturile pe 30 de zile; aprobarea unui om transformă sloturile în livrabile `planificat`. Tabelele `calendare` și `calendar_intrari` (migrarea `0034`, RLS), ecranul `/calendar/{client}`.

### Poarta F5
- Testul de poartă `tests/integration/test_poarta_f5.py`: pe seturile înghețate, cu validatorii deterministe și fără niciun model, 107 / 107 materiale greșite blocate și 3 / 63 bune respinse pe nedrept; cifrele pe validator în `docs/specs/F5-poarta.md`.

### F5.9 — Biroul de aprobări
- Ecranul `/aprobari` complet, întâi pentru telefon: ordine după urgență, termen și prioritate; card cu previzualizarea pe canal, verdicte și dovezi, pachetul de context, istoricul versiunilor cu diferențe și întrebările către client; respingere cu motiv standard și frază opțională, statistica motivelor; editare pe loc (versiune nouă validată din nou, perechea `asteapta_aprobare → in_validare`, migrarea `0033`); nicio aprobare pe o versiune nevalidată.

### F5.10 — Carantina și contestațiile
- Ecranele `/validatoare/carantina` (listă, detaliu cu dovezi, eliberare cu motiv spre validare / reparație, respingere definitivă), `/validatoare/verdicte/{id}` (contestă orice verdict) și `/validatoare/exemple` (promovarea exemplelor propuse în setul de aur); statistica contestațiilor pe validator.

### F5.8 — Calibrarea judecătorilor (G14)
- Eșantion săptămânal programat de verdicte V3 / V4 la om, coada de etichetare `/validatoare/calibrare`, acordul pe judecător (procent, kappa, interval Wilson), alertă sub 85% și la derivă, etichetele „greșit” devin exemple propuse; tabelul `calibrare_etichete` (migrarea `0032`).

### F5.7 — Seturile de aur și bancul de evaluare (K4)
- Seturi de aur înghețate în `evaluare/aur/` (8 validatoare, 107 materiale greșite, 63 bune), bancul `python -m app.validare.banc` și butonul din ecranul „Validatoare” (job durabil `validare.banc`), scoruri pe validator (matrice, precizie, recall, respingeri pe nedrept) salvate în `banc_rulari`; exemple propuse pentru setul de aur (`exemple_propuse`), migrarea `0031`.
- `db.restrans_la_client` (îngustare într-un punct de salvare anulat) în locul comutării libere de context; validatorii îmbunătățiți (limbă străină, linkuri, etichete de ordine, tipare G3, registrul G4, „încearcă”, promisiuni negate). Workerul importă acum `app.validare.fluxuri`.

### F5.6 — G7 Originalitate și G9 Juridic
- G7: suprapunere de shingle-uri cu sursele colectate (concurența blochează, materialele clientului doar avertizează), parafraze prin vectori, active fără licență. G9: reducerea cere ofertă cu preț de referință egal cu cel mai mic preț din ultimele 30 de zile (din versiunile aprobate ale ofertei; lipsa istoricului se semnalează explicit), promisiuni de rezultat, mențiuni obligatorii (pachetul `juridic`), judecător puternic opțional (V4).

### F5.5 — G4 Ton și G8 Lizibilitate și conversie
- G4: vocabularul interzis / preferat al ghidului de brand APROBAT (V1), similaritatea cu exemplele aprobate prin vectori (V2, prag [I] dependent de model), rubrica de ton doar la semnal, cu dovadă literală (V3). Fără ghid aprobat nu trece tăcut.
- G8: un singur apel la acțiune (grupe de forme imperative în română; mai multe grupe → respins), hook (prima frază), lizibilitate (indice ILA documentat, praguri [I]), rubrica «hook clar» doar la semnal. Date în `date/ton.toml` și `date/conversie.toml`.

### F5.4 — Pachetele de reguli și G3 Politici
- `rulepacks/`: 25 de reguli de început în 10 pachete TOML (generale; Meta, TikTok, LinkedIn, email; nișe refuzate: jocuri de noroc, adulți, politică, scheme financiare; nișa sănătate), fiecare cu sursă, severitate, marcaj [I], data scrierii și exemple blocate / care trec, rulate automat; încărcare cu validare de schemă; garda interzice scrierea în `rulepacks/` din cod. Regulile pe client în bază (`reguli_client`, migrarea `0030`): autor uman obligatoriu, doar adăugare, aceleași exemple verificate la scriere.
- G3 (V1) aplică pachetele potrivite livrabilului (generale + canal + nișe + client) și păstrează în verdict versiunea și amprenta pachetelor; G3 (V3, opțional) pentru promisiuni formulate liber. Nișele refuzate merg în carantină. Dockerfile copiază `rulepacks/`.

### F5.3 — G2 Verificatorul de fapte
- Extragerea deterministă a afirmațiilor verificabile (prețuri cu monedă, procente, termene, date, ore, cifre, superlative, comparații, promisiuni) cu fragmentul exact, potrivirea EXACTĂ cu registrul (fapte aprobate și valabile la data publicării, oferte, reducere calculată din prețul de referință, citate din surse verificate literal), blocare la preț diferit sau afirmație neacoperită; V3 opțional pentru afirmațiile nestructurate, cu verificare deterministă a răspunsului.
- Fapt lipsă → livrabilul se oprește cu o ÎNTREBARE către client (`validari_intrebari`, migrarea `0029`, vizibilă în urma livrabilului), nu cu o presupunere.

### F5.2 — G1 Structură și G10 Limbă
- G1 (V0): câmpuri obligatorii pe cele 12 tipuri de livrabil, liste cu limite, lungimi pe canal [I], limba română (determinist, fără model), linkuri bine formate (fără rețea), toate într-un singur verdict. G10 (V1): diacritice lipsă (dicționar + raportul literelor), ș / ț cu sedilă, „î” / „â”, ghilimele, cratimă, repetiții; G10 (V3, opțional): acord și registru, prin judecător cu rubrică da / nu, dovadă literală și model diferit de autor.
- Date în `app/validare/date/*.toml`; infrastructura comună a judecătorilor (`judecator.py`) și a problemelor (`probleme.py`) pentru F5.3–F5.6; prompt versionat `validare.g10_limba`.

### F5.1 — Cadrul de validare
- Forma verdictului (validator + versiune, treaptă, trece / avertisment / eșec, severitate, scor, dovezi cu fragmentul exact și regula, instrucțiune, cost), cascada V0 → V5 (oprire după treapta cu eșec; la treptele cu cost, la primul eșec), agregarea (eșec critic → carantină, eșec major → reparație, avertismente în puncte, peste prag la om) și unirea instrucțiunilor într-un singur mesaj pentru autor. Registrul de validatori ca date (cod G, treaptă, tipuri și canale).
- Bucla `în validare` → `în reparație` → `în validare` peste mașina de stări (limita de 2 runde rămâne a `productie.muta`), fluxul durabil `validare.livrabil`, punctul de extensie pentru autorii reparațiilor (F6).
- Tabele `livrabile_continut` (versiuni de conținut ale livrabilului, provizoriu până la F6), `validari_rulari`, `validari_verdicte` (doar adăugare, RLS), migrarea `0028`; secțiunea „Validare” în urma livrabilului din ecranul Producție. DECIZII D-006.

### Poarta F4 — lanțul verificat local
- Test cap-coadă cu brandul fictiv (colectare → fapte → interviu → brief → ghid → citate și public → insight → strategie → aprobări → pachet de context) și comanda `python -m app.creier.pregatire --client <nume>` care creează clientul și sursele unui brand propriu. Poarta propriu-zisă (CariereAI și BigBrain) rămâne deschisă până la materialele și aprobarea proprietarului.

### F4.8 — Ecranul „Creierul de brand”
- Pe client: compartimentele cu intrările lor, versiunea aprobată și propunerile în așteptare, diferența între versiuni, editare (creează propunere nouă, nu suprascrie; trece prin schema și poarta compartimentului), aprobare / respingere / retragere cu motiv, sursele, concurenții și pașii de pregătire; faptele rămân pe `/creier/fapte` (legate, nu dublate). Întâi pentru telefon: carduri și formulare, fără tabele. `creier.rezumat_pe_compartimente`, `creier.propuneri_in_asteptare`.

### F4.11 — Strategia pe 90 de zile, prima formă
- Strategia (ipoteză, plan pe 30 și 90 de zile, indicator principal, prag minim, fereastră de măsurare, criteriu de oprire — toate obligatorii, schemă strictă și poartă) propusă prin gateway pe profilul `strategie` (se amână, nu se degradează) din pachetul de context al clientului (brief, ghid, fapte, public, insight aprobate), versionată și aprobată de un om. Ecranul „Campanii” (`/campanii`): lista pe client, detaliu, aprobă / respinge cu motiv.
- Constructorul de context: secțiuni la cerere `brief`, `public`, `insight`, `strategie` (`sectiuni_extra`); implicit pachetele nu se schimbă.

### F4.10 — Harta pieței și brieful de insight
- Concurenți ca surse (3–5 pe client, citire cu colectorul existent, text lipit altfel; textul lor nu se reutilizează), afirmațiile lor (ofertă, preț, mesaj) extrase pe pasaje cu citat verificat literal în `insight_piata`, brief de insight pe o pagină cu trimitere la sursă pe fiecare afirmație (profilul `strategie`, se amână), poarta care blochează afirmațiile fără trimitere, trimiterile fără sursă și sondajul de citate picat; sondaj cu eșantion determinist (`sondaj.esantion`).

### F4.9 — Profilul de public și vocea clientului
- Citate reale din recenzii, comentarii și întrebări (flux durabil pe pasaje, gateway cu schemă strictă): fiecare citat verificat LITERAL în pasaj, fără date personale (garda din F3.9) și fără numele autorului, cu sursă și poziție, în `insight_public` (aprobat de sistem). Profilul clientului ideal (segmente, nevoi, obiecții, declanșatori, canale, limbaj, dovezi) propus din brief și citate, cu poartă (≥ 20 de citate aprobate, dovezi reale) și aprobat doar de un om.
- `gateway.detecteaza_date_personale` (export). Mecanism comun de extragere pe pasaje (`onboarding.extractie`).

### F4.5 — Profilul de brand
- Trei variante de ton propuse prin gateway din brieful aprobat și din materiale (descriere, reguli da / nu, vocabular preferat / interzis, ≥ 3 exemple pe ≥ 3 canale, fără vocabular interzis în exemple — verificate determinist); omul alege, combină sau corectează (versiune nouă, nu suprascriere); ghidul aprobat intră în `profil_brand` și este preluat de constructorul de context. Migrarea `0027`, ecranul `/onboarding/{client}/ghid`.
- Creier: randare pe compartiment (`inregistreaza_randare`) și intrări aprobate doar de om într-un compartiment cu aprobare automată (`inregistreaza_cere_om`).

### F4.4 — Asistentul de onboarding
- Interviul din 19.3 ca date (5 secțiuni, 11 întrebări), sesiune persistentă și reluabilă (`onboarding_sesiuni`, `onboarding_intrebari`, migrarea `0026`), întrebări de clarificare generate prin gateway și limitate (2 pe întrebare, 6 pe sesiune), brief cu 11 câmpuri obligatorii (schemă Pydantic) compus ca flux durabil din răspunsuri + materialele colectate, cu sursă și citat verificat literal pe fiecare câmp.
- Poarta de aprobare a Creierului (`creier.inregistreaza_poarta`): un brief cu câmpuri goale nu poate deveni „propus” sau „aprobat” pe nicio cale. Compartimente noi `brief`, `insight_piata`, `strategie` (DECIZII D-005). Permisiunea `onboarding.completeaza` (operator, proprietar). Ecranul `/onboarding`.

### F4.7 — Constructorul de context
- Pachetul de context al unei sarcini (client, tip, canal, întrebare, livrabil): reguli și interdicții (obligatorii), fapte aprobate și valabile relevante (doar prin `fapte.pentru_context`), oferte valabile, ghidul de brand aprobat (lipsa lui e spusă explicit) și pasaje din materialele clientului prin căutarea hibridă (doar din surse reutilizabile; în prompt doar marcate ca externe). Fiecare element poartă identificatorul și versiunea sursei.
- Buget de tokeni cu priorități între secțiuni și trunchiere deterministă (un element intră întreg sau deloc; regulile intră mereu); aceleași intrări dau aceeași amprentă.
- Pachetul se salvează (`pachete_context`, migrarea `0025`, RLS, doar adăugări) și se leagă de livrabil: apare în secțiunea „Pachetul de context” de pe `/productie/{id}`.
- Corecție la F4.6: valoarea numerică a unui fapt nu se mai stochează în notație științifică (`50` devenea „5E+1”). `cautare.cauta` primește `surse=[…]`.

### F4.6 — Registrul de fapte și catalogul de oferte
- Fapte (tip, afirmație atomică, valoare structurată cu număr exact, sursă obligatorie: pasaj / document / URL / declarația clientului, stare propus / aprobat / respins / expirat, valabilitate, cine a aprobat) și catalog de oferte (preț, monedă, condiții, valabilitate, legate de fapte), peste depozitul versionat. Singura citire pentru context, `pentru_context`, întoarce doar ce a aprobat un om și e valabil la data cerută; o gardă statică o impune și constructorului de context.
- Extragere din materiale ca flux durabil: pasajele trec prin gateway cu schemă strictă (`prompts/creier.extrage_fapte.v1.md`), fiecare fapt păstrează citatul exact, iar un verificator determinist respinge propunerile al căror citat nu apare literal în pasaj sau ale căror cifre nu apar în citat. Expirare automată (job zilnic) cu anunț; punct minim în panou (`/creier/fapte`: aprobă / respinge cu CSRF, permisiune, audit).
- Migrarea `0024` (`creier_extrageri`, RLS). `Dockerfile`: `COPY prompts`.

### F4.3 — Vectori și căutare hibridă
- Materialele colectate se taie în pasaje (paragrafe întregi, suprapunere, legătură pasaj → document → sursă → URL / poziție), se vectorizează în loturi prin gateway (flux durabil `creier.indexeaza_sursa`, cu reprogramare la `Amanat`; pornește singur după fiecare colectare) și se caută hibrid: vectori (pgvector) + text fără diacritice + trigrame, combinate prin fuziune de ranguri, cu filtrare pe client (RLS) și opțional pe sursă / compartiment. Fiecare vector poartă modelul care l-a produs: la schimbarea modelului pasajele se re-vectorizează.
- Migrarea `0023` (`pasaje`, RLS). Gateway: `vectorizeaza_cu_model`, `model_vectori`. Setări: `AMA_VECTORI_PREFIX_PASAJ`, `AMA_VECTORI_PREFIX_INTREBARE`.

### F4.2 — Colectorul de surse
- `app/cercetare`: crawl politicos al site-urilor (robots.txt cu `Crawl-delay`, User-Agent propriu, o cerere odată pe gazdă cu pauză, doar același domeniu înregistrat, sitemap, fără formulare și fără autentificare), cu apărare SSRF (doar http / https, adrese private / loopback / link-local / metadate refuzate la fiecare redirecționare, limită de octeți în flux, tipuri permise) și limite de pagini, adâncime, octeți, timp, capcane de linkuri. Text extras cu parserul din biblioteca standard; originalul pe disc (`AMA_MEDIA_DIR`) cu hash; deduplicare; re-colectare incrementală; flux durabil pe coada `io` cu stare vizibilă (găsite / citite / sărite și de ce).
- Statutul surselor din 12.1 ca date; materiale manuale (text lipit, `.txt`, `.md`; PDF amânat); `ca_continut_extern` pentru prompturi.
- Migrarea `0022`: `surse`, `colectari`, `colectari_pagini`, `documente_colectate` (RLS). Setări noi: `AMA_MEDIA_DIR`, `AMA_COLECTOR_USER_AGENT`.

### F4.1 — Modelul Creierului
- `app/creier`: cele zece compartimente din 10.1 ca date, intrări cu versiuni (`ciornă → propus → aprobat → retras`), sursă obligatorie, valabilitate, cine și când a aprobat, nivelurile de cunoaștere din 10.2. API: `creeaza_intrare`, `propune_schimbare`, `aproba`, `retrage`, `citeste`, `la_data`, `istoric`, `diferenta_versiuni`.
- Migrarea `0021` (`creier_intrari`, `creier_versiuni`, RLS): conținutul unei versiuni nu se mai poate schimba (declanșator în bază), cel mult o versiune aprobată pe intrare.

### Poarta F3 — Gateway de modele
- Test cap-coadă cu furnizori falși (`tests/integration/test_poarta_f3.py`): testul comparativ rulat pe modelele de text din configurarea de probă, iar cu fiecare dintre cei cinci furnizori oprit pe rând un flux de probă pe fiecare profil se termină (degradare marcată la modelul local pe coada `greu`, trecere pe alt furnizor sau amânare curată, fără eșecuri). Testul comparativ pe modele reale rămâne deschis până la migrare.

### F3.11 — Planificatorul de capacitate (A4)
- Planificatorul zilnic (și la cerere) compară munca planificată (costuri pe tip de livrabil, ca date) cu cotele rămase pe profil și cu timpul de CPU al culoarelor grele; ce nu încape se amână, termenul cel mai îndepărtat întâi, iar P0 și termenele sub 48 de ore rămân neatinse. Decizia se scrie (`planificare_planuri`, `planificare_decizii`, migrarea `0020`) și o alertă spune ce nu a încăput.
- `productie.amana` / `productie.elibereaza` și câmpul `livrabile.nu_inainte_de`: `productie.muta` refuză pornirea unui livrabil amânat până la acel moment (cod `amanat`, în istoric).

### F3.10 — Ecranul „Modele și cote”
- `/gateway/registru` arată cota rămasă pe fiecare furnizor și model (minut și zi, cu resetare), starea întrerupătoarelor și blocajele, scorurile pe profil și rulările testului comparativ, viteza modelelor locale, consumul pe client față de buget. Proprietarul editează limitele, termenii și bugetele (implicite și pe client), pornește testul comparativ și importă note, cu CSRF, verificare de rol și audit.

### F3.6 — Testul comparativ pe română
- Set de 72 de sarcini în română (`evaluare/sarcini/`, 12 pe fiecare profil din 8.2) cu criterii automate (schemă, lungime, cuvinte obligatorii / interzise, răspuns exact, diacritice), hamul de rulare prin gateway (P3, un model pe rulare, cote și bugete respectate, continuare după amânare), scorul pe (model, profil) scris în `gateway_modele.scor` și folosit de rutare, nota umană importată din CSV, istoric de rulări (migrarea `0019`), flux și job lunar, comandă `python -m app.gateway.evaluare`.

### F3.5 — Modelul local și modelul de embeddings
- Adaptorul `local` (server compatibil OpenAI separat, fără cheie, ieșire structurată prin schemă); modelul local se apelează doar din joburi de pe coada `greu` (în afara ei: `ApelRefuzat("local_doar_pe_coada_greu")`); `motor.coada_curenta()`. Sămânța în registru (3 mărimi + model de vectori de 384 dimensiuni, inactive, neverificate; migrarea `0018`) și serviciile `local-llm` / `embeddings` în compose (profil, fără digest: NEVERIFICAT).
- `gateway.vectorizeaza(texte, tenant_id=…)` și `gateway.dimensiune_vectori`: vectori fără coada `greu`, dimensiunea ca dată în registru. `python -m app.gateway.masurare`: viteza (tokeni/s) a modelelor locale, scrisă în registru. `gateway.apeleaza(…, model=…)` pentru un singur model (evaluare).

### F3.9 — Garda de date personale și garda de injecții
- Mascare deterministă înainte de orice apel (email, IBAN, CNP cu cifră de control, card cu Luhn, telefon românesc, IP; CUI doar la cerere), cu marcaje stabile `[EMAIL_1]`, demascare opțională a răspunsului, jurnal și conținut păstrat în varianta mascată. `date_confidentiale` ajunge în rutare; fără model permis, apelul este refuzat.
- `gateway.marcheaza_extern(text, sursa=…)`: funcția unică pentru orice text venit din afară (delimitatori cu id aleator, delimitatori falși neutralizați, caractere invizibile eliminate) și instrucțiunea „date, nu instrucțiuni” în mesajul de sistem; detecție euristică de tentative de injecție ca semnal în jurnalul de apeluri (migrarea `0017`), fără blocare. Garda `check_gateway` interzice `eval`/`exec`/`subprocess` în gateway.

### F3.8 — Bugete și priorități
- Bugete pe client (apeluri, tokeni, preț-umbră; pe zi și pe lună; valori implicite + suprascrieri per client; migrarea `0016`), aplicate de interceptorul `buget_client`: la depășire, P2 și P3 primesc `Amanat` cu momentul resetării, P1 continuă până la 1,5 × buget, P0 nu este atins. Consumul se ține în contoare proprii, rezervate atomic (corect la concurență). Avertizare la 80%, o singură dată pe fereastră. Decizia D-004.

### F3.7 — Registrul de prompturi și jurnalul de apeluri
- `gateway.apeleaza(db, prompt=…, variabile=…, schema=…, tenant_id=…, componenta=…, prioritate=…)`: API-ul public unic. Prompturile sunt versionate (`gateway_prompturi`, migrarea `0015`; ciornă / activ / retras; versiunea activă nu se modifică, impus în bază; o singură versiune activă pe nume) și pot veni din fișiere `prompts/<nume>.v<N>.md`. Variabilele trebuie să se potrivească exact cu locurile din șablon; un secret al aplicației nu poate intra într-un prompt.
- Jurnalul de apeluri (`gateway_apeluri`, cu `tenant_id` și RLS): cine, prompt și versiune, model ales și de ce, tokeni, durată, reparații, preț-umbră, traseul încercărilor; scris și pentru apelurile amânate, refuzate sau eșuate. Conținutul (mesajele trimise, răspunsul) stă separat, cu RLS, 30 de zile (`gateway_apeluri_continut`, ștergere zilnică); nu intră în tabelele motorului sau în jurnalele aplicației. Fiecare apel se contorizează în bugetul livrabilului.
- Panoul: `/gateway/apeluri` (listă cu filtre pe client, model și rezultat) și detaliul unui apel, cu izolare pe client și urmă în audit la deschiderea conținutului.

### F3.4 — Rutarea și lanțurile de rezervă
- Profilurile de sarcină din 8.2 ca date (`gateway_profiluri`, migrarea `0014`): nivel minim, capabilități, lanț ordonat de modele, ce se întâmplă când lanțul s-a epuizat (`amana` / `degradeaza` / `amana_sau_provizoriu`), lanț de degradare. Alegerea modelului (nucleu pur): furnizor oprit, fără cheie, fără uz comercial, antrenare pe date, capabilități, nivel minim, întrerupător deschis, T4 pe calea critică (ADR-06), apeluri plătite oprite, „alt model decât autorul”; ordine după scor (gol până la F3.6) și lanț.
- Reacțiile din 7.5: 429 → alt furnizor; eroare de server → 3 reîncercări cu pauză crescătoare, apoi alt furnizor; ieșire în afara schemei → o reparație, apoi alt model; autentificare → furnizor pe pauză cu audit și alertă. Întrerupător pe furnizor (3 eșecuri la rând → scos 120 s, apoi cerere de probă). Strategia se amână, nu se degradează; clasificarea și rescrierea degradează la modelul local.
- Interceptori înainte și după apel (`gateway.adauga_interceptor`), punctul de extensie pentru bugete (F3.8) și gărzile de date (F3.9).

### F3.3 — Limitatoarele de cotă
- Contoare persistente în Postgres (`gateway_contoare`, `gateway_blocaje`, migrarea `0013`) pe (model sau cont de furnizor, minut / zi), cu rezervare atomică înainte de apel (o instrucțiune SQL sub plafon, corectă la concurență), regularizare cu tokenii reali, antetele furnizorului ca sursă de adevăr (`x-ratelimit-*`, `retry-after`), blocaj după 429 și rezerva de 10% din limita zilnică pentru P0.
- Cota epuizată devine `Amanat(pana_la)`; un flux durabil se reprogramează prin motor cu `gateway.reprogrameaza` pentru momentul resetării (fără `sleep`).

### F3.2 — Clientul unificat
- Un singur mod de a apela orice furnizor, cu `httpx` și transport injectabil (fără SDK-uri): adaptoare pe tip de API (compatibil OpenAI, Gemini, Anthropic), erori clasificate după 7.5, citirea antetelor de limită, ieșiri structurate (schemă JSON nativă sau instrucțiune, validare Pydantic, o singură reparație, apoi eroare tipizată). Cheia nu apare în erori sau jurnale (testat).
- Garda `scripts/check_gateway.py` în `make guards`: niciun import intern al gateway-ului și nicio adresă de furnizor în afara `app/gateway`; fără SDK-uri de furnizori. Furnizorul fals pentru teste (`tests/furnizor_fals.py`, SIMULAT).

### F3.1 — Registrul de furnizori și modele
- Tabelele `gateway_furnizori` și `gateway_modele` (migrarea `0012`), la nivel de agenție, cu RLS: furnizor (tip de API, adresă `https`, stare, termeni: uz comercial, antrenare pe date, regiuni; marcaj `V`/`S`/`I` și dată de verificare; limite pe minut și pe zi) și model (nivel T1–T4/local, context, capabilități, limite, preț-umbră, scor pe profil). Cheia de API nu stă în bază: doar numele variabilei de mediu `AMA_CHEIE_*` (baza refuză alt nume). Un furnizor fără uz comercial confirmat nu poate fi activat (impus și în bază).
- Sămânța din `app/gateway/inventar.py` (OpenRouter, Groq, Gemini, Cloudflare, Claude), totul `inactiv`. Ecranul `/gateway/registru` (limite, termeni, „cheie configurată / lipsește”), cu activare / dezactivare de către proprietar (CSRF, audit).

### Poarta F2 — Motorul
- Test cap-coadă cu procese reale (`tests/chaos/test_poarta_f2.py`): un livrabil de probă parcurge toate stările normale, supraviețuiește la două SIGKILL (la mijloc și în jurul publicării) și produce un singur efect la conectorul fals, fără tranziții dublate.

### F2.9 — Ecranele Producție și Operare
- Producție: lista livrabilelor (filtre pe client, stare și excepții, paginare) și „urma” fiecăruia: mutările inclusiv refuzurile, pașii fluxului durabil cu stare, durată și eroare, cererile de aprobare, efectele externe, contoarele de limite. Acțiuni cu CSRF, permisiune, motiv și audit: reia livrabilul din coada de erori (și efectul extern eșuat), reia un pas eșuat, anulează. Operare, motorul: workerii și cozile (adâncime, în lucru), joburile programate (pauză, reluare, „rulează acum”), efectele în așteptare sau oprite și canalele pe pauză, întrerupătorul și opririle. Un operator vede doar clientul la care are acces.

### F2.5 — Executorul de efecte externe
- Outbox tranzacțional (`efecte_de_trimis`): efectul se scrie în aceeași tranzacție cu mutarea care îl cere, cu cheie de idempotență unică (client, livrabil, canal, versiune, tip); a doua cerere întoarce primul rând. Fluxul durabil `efecte.executa` îl trimite pe coada canalului; o încercare notează `în trimitere` înainte de conector și rezultatul după, iar după orice eroare sau rezultat necunoscut începe cu `verifica` (7.3). Erori clasificate (7.5): temporare cu pauză crescătoare, autentificare cu pauză pe conector și alertă de reautorizare, definitive în coada de erori. Oprirea globală a publicării și oprirea pe client se verifică chiar înainte de trimitere; efectul rămâne în așteptare și pleacă după repornire doar dacă mai e valabil. Contractul și registrul conectorilor (`app/connectors`), conector fals în teste, garda `scripts/check_efecte.py`. Migrarea `0011`.

### F2.10 — Nivelurile de autonomie
- Matricea pe client × cinci clase de acțiuni, niveluri L0–L4, implicit L1; funcția pură de decizie „cere aprobare?” (umbră / aprobare / automat) cu eșantion determinist la L2 și L3; canalele cu consimțământ per postare (TikTok) rămân la L1, ca date; schimbarea nivelului doar de proprietar (permisiunea `autonomie.seteaza`, motiv, audit); retrogradare cu un nivel la incident critic; poarta din `productie.muta` recalculează decizia (L0 produce, nu publică). Migrarea `0010`.

### F2.8 — Cererile de aprobare
- Obiectul de aprobare (client, livrabil și versiunea lui, clasa de acțiune, decident operator/client, termen de 48 h, reamintire la 24 h, stare, decident, moment); decizia se leagă de versiune (o aprobare pe o versiune veche nu aprobă versiunea nouă); poarta „fără aprobare automată” în `productie.muta`; expirare prin jobul programat (o cerere neprimită la timp devine `expirat`, nu se publică); notificări la creare și înainte de termen; punctul minim din panou (listă, „Aprobă”, „Respinge” cu motiv, CSRF, permisiune, audit). Migrarea `0009`.

### F2.4 — Limite anti-buclă
- Cel mult 2 runde de reparație (a treia merge la om), cel mult 12 predări, buget per livrabil (apeluri la modele și timp), toate în `productie.muta`/`inregistreaza_consum`; la depășire livrabilul trece în coada de erori cu diagnostic și anunț, iar un om îl reia (`reia_de_om`). Întrerupătorul global (rata de eșec peste 30% pe oră, minim 10 rezultate) oprește producția nouă (`Oprire.PRODUCTIE`, buton în panou și comandă în Telegram); repornirea e doar a omului, auditată. Pragurile se configurează. Migrarea `0008`.

### F2.3 — Mașina de stări a livrabilului
- Cele 22 de stări din 7.2 (16 normale + 6 de excepție) și tabelul de tranziții ca date; tabelele `livrabile` și `livrabile_tranzitii` (istoric doar-adăugare); o singură funcție, `productie.muta`, schimbă starea (blocare pe rând, stare așteptată, versiune opțională), cu declanșator în bază care refuză orice altă cale. Tranziția nepermisă este refuzată și înregistrată într-o tranzacție separată, deci rămâne după rollback-ul apelantului. Migrarea `0007`.

### F2.7 — Watchdog și coada de erori
- Workerul bate în `worker_semnale`; căderile și repornirile se văd (a treia într-o oră anunță); un job blocat se oprește și se reîncearcă o dată; joburile eșuate, epuizate sau blocate intră în coada de erori cu context complet, grupate pe cauză și triate (minor / major). Ecranul Alerte din panou: listă, detaliu, „Reia” (de la pasul eșuat sau ales) și „Închide” (cu motiv), cu CSRF și audit; numărul alertelor și starea workerului pe Acasă. Migrarea `0006`, permisiunea `alerte.gestioneaza`, healthcheck pe serviciul `worker`.

### F2.6 — Planificatorul de timp
- Joburi recurente (cron cu 5 câmpuri = la minut, fus orar `Europe/Bucharest`, recuperarea ticurilor ratate) și sloturi (un job la un moment dat, idempotent, supraviețuiește repornirilor), peste planificatorul bibliotecii. Programările se declară în cod și se aplică la pornirea workerului.

### F2.2 — Cozile
- Cozile din 7.5: `urgent`, `greu` (câte un job pe culoar, `AMA_CULOARE_GREU`, implicit 2), `io` (24), `invatare` (1); fabrica de cozi pe furnizor și pe platformă cu limită de rată; priorități P0–P3 cu termenul codificat în prioritatea bibliotecii (nu are termene). Configurarea cozilor se scrie în bază înainte de lansare.

### F2.1 — Execuția durabilă
- Biblioteca de workflow-uri DBOS Transact (`dbos==3.5.0`) în aceeași bază, schema `dbos`, ascunsă în `app/operare/motor/` (garda `scripts/check_motor.py`); decoratorii `flux` și `pas`, `trimite` din procesul web, procesul `worker` cu oprire curată, schema creată de `ama_owner` (`python -m app.operare.motor.migrare`), drepturi minime pentru `ama_app`, serviciul `worker` în compose, mutat de deployer odată cu aplicația. Un flux oprit forțat reia de la ultimul pas.

### F1.10 — Botul Telegram și butoanele de oprire
- Webhook păzit de secret și de lista conversațiilor permise; comenzile `/stare`, `/opreste…`, `/porneste…` (repornirea cere cod de confirmare, o singură încercare), alerte critice. Steagurile de oprire există, dar modulele care le citesc apar din F2.

### F1.7 — Coaja panoului
- Panou instalabil (PWA) cu bara de jos, ecranul Acasă, temă luminoasă/întunecată, service worker și notificări push; HTMX și Alpine (build CSP) vendorizate.
- Pagina Operare: promovare în producție și revenire cu confirmare, starea backupului.

### F1.8–F1.9 — Livrare și backup (infrastructură)
- Imagine Docker, compose pentru staging și producție, proxy Caddy, instalarea VPS-ului, deployer cu revenire, backup criptat cu test de restaurare.

### F1.6 — Jurnalul de audit și de evenimente
- Două jurnale doar cu adăugare, impuse în bază; fiecare acțiune sensibilă este înregistrată cu utilizator, moment și identificator de corelare.

### F1.5 — Autentificare
- Parolă (argon2id), al doilea factor TOTP obligatoriu pentru agenție, coduri de recuperare, sesiuni pe server, CSRF, limitarea încercărilor, antete de securitate.

### F1.4 — Clienți, utilizatori, roluri
- Modelul de conturi, cele șase roluri, izolare la nivel de rând forțată pe toate tabelele cu date de client.

### F1.3 — Baza de date și migrările
- Postgres cu `pg_trgm`, `citext`, `vector`; Alembic; roluri separate pentru migrări și pentru aplicație.

### F1.1 — Aplicația de bază
- Aplicație FastAPI modulară, `/healthz`, configurare din variabile de mediu, jurnale JSON cu identificator de corelare.

### F0.2 — Repo și reguli
- `AGENTS.md`, `DECIZII.md`, structura de directoare, documentul de arhitectură împărțit pe secțiuni în `docs/`, cele 16 ADR-uri, șablonul de cerere de integrare, CI.

## 2026-11-17 — FS.1 (sesiunea C)

- Autorizare Shopify simulată prin HTTP local, stare unică expirabilă, HMAC callback și token AES-GCM legat de tenant/magazin.
- Migrare 0120 din 0075, RLS forțat; teste de izolare și criptare.

## 2026-11-17 — FS.2 (sesiunea C)

- Catalog Shopify minimal tenant, upsert fără dubluri, ignorarea versiunilor vechi și ștergere logică.
- HMAC webhook verificat pe corpul brut; contract HTTP local paginat, fără trafic real. Migrare 0121.

## 2026-11-17 — FS.3 (sesiunea C)

- Import local comenzi și clienți Shopify, versiuni monotone, email criptat și consimțământ explicit pentru CRM tenant.
- Migrare 0122 cu RLS; nicio scriere în CRM-ul agenției.

## 2026-11-17 — FS.4 (sesiunea C)

- API raport lunar vânzări atribuite UTM/cod, net după anulări/rambursări, fără conversii valutare.

## 2026-11-17 — FS.5 (sesiunea C)

- Ecran Shopify în meniu, izolat pe tenant activ, cifre lunare și stare sincronizare.
- Sincronizator cu token decriptat la citire și cititori injectați; păstrează ultima reușită după eroare. Migrare 0123.

## 2026-11-17 — FS.6 (sesiunea C)

- Poarta Shopify cap-coadă pe HTTP local, 19 teste proprii trecute; catalog completat cu câmpuri comerciale, migrare 0124.
- make check unic: 3132 passed, 4 failed (media), 1 skipped; rezultatul și operațiile reale rămase în STARE.

### Revizuire PR #12 — 2026-11-18
- Shopify: import Decimal cu exponenți ISO 4217 și continuare după rânduri invalide,
  creata_la timestamptz, magazin unic per tenant, ștergere webhook doar cu id.
- OAuth pe query brut, HMAC comparat în bytes și expirare callback la 5 minute.
- Panoul folosește maparea persistentă a codurilor de reducere per magazin.
