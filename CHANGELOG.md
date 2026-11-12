# Jurnalul de schimbări

Format: o intrare pe pas, cea mai nouă sus.

## Nelansat

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
