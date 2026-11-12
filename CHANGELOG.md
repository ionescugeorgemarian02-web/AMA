# Jurnalul de schimbări

Format: o intrare pe pas, cea mai nouă sus.

## Nelansat

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
