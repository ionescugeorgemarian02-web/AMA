# Rularea locală (PC-ul proprietarului)

Platforma întreagă pe calculatorul tău, cu Docker Desktop: Postgres (cu pgvector), migrările, aplicația pe
<http://localhost:8000> și workerul. Toți conectorii externi (plăți, email, audit, publicare, reclame) sunt **simulați**:
nimic nu pleacă în afară. Datele rămân în volumele Docker până la `make local-reset`. Decizia: D-016.

## 1. Pregătire, o singură dată

### Windows (WSL2)
1. Instalează WSL2: în PowerShell ca administrator, `wsl --install -d Ubuntu`, repornește, alege un utilizator.
2. Instalează [Docker Desktop](https://www.docker.com/products/docker-desktop/); în *Settings → General* bifează
   „Use the WSL 2 based engine”, iar în *Resources → WSL Integration* activează distribuția Ubuntu.
3. În Ubuntu (meniul Start → Ubuntu): `sudo apt update && sudo apt install -y git make openssl`.
4. Clonează proiectul **în sistemul de fișiere Linux** (nu în `/mnt/c/…`, e mult mai lent):
   `cd ~ && git clone <adresa-repo> AMA && cd AMA`.

### Mac (Intel sau Apple Silicon)
1. Instalează [Docker Desktop](https://www.docker.com/products/docker-desktop/) și pornește-l o dată.
2. În Terminal: `xcode-select --install` (aduce `git` și `make`; `openssl` există deja).
3. `cd ~ && git clone <adresa-repo> AMA && cd AMA`.

Docker Desktop: dă-i cel puțin 4 GB de memorie (*Settings → Resources*).

## 2. Pornire

```bash
make local-up
```

Prima dată: creează `infra/env/local.env` din `infra/env/local.env.example` cu parole generate (fișierul e ignorat de
git), construiește imaginea din `Dockerfile` (câteva minute), pornește baza, rulează migrările, apoi aplicația și
workerul, și populează datele demo: contul de proprietar și brandul fictiv **„Cafeneaua Zorilor”**, cu brieful aprobat.
Popularea e idempotentă: la fiecare `make local-up` completează doar ce lipsește.

## 3. Prima autentificare

1. Deschide <http://localhost:8000/login>.
2. Emailul și parola: `AMA_DEMO_EMAIL` și `AMA_DEMO_PAROLA` din `infra/env/local.env` (`grep DEMO infra/env/local.env`).
3. Proprietarul are obligatoriu al doilea factor: scanează codul QR cu o aplicație de autentificare (Google
   Authenticator, Aegis, 1Password) și păstrează codurile de recuperare.

## 4. Cheia LLM (opțional)

Fără cheie, platforma rulează în **mod simulat**: sarcinile care cer un model sunt refuzate vizibil de gateway
(„fără cheie”), restul merge. Pentru modele reale gratuite: creează o cheie pe <https://openrouter.ai>, pune-o la
`AMA_CHEIE_OPENROUTER=` în `infra/env/local.env`, rulează din nou `make local-up`, apoi în panou, la *Gateway* (`/gateway`),
activează furnizorul OpenRouter.

## 5. Oprire, ștergere, depanare

| Ce | Comandă |
| --- | --- |
| Oprește (datele rămân) | `make local-down` |
| Șterge baza și media, pornește de la zero cu datele demo | `make local-reset` |
| Jurnalele aplicației / workerului | `docker compose -p ama-local -f infra/compose/local.yml logs -f app worker` |
| Starea serviciilor | `docker compose -p ama-local -f infra/compose/local.yml ps` |

- **Portul 8000 e ocupat:** oprește programul care îl folosește (aplicația ascultă doar pe `127.0.0.1`).
- **„Cannot connect to the Docker daemon”:** pornește Docker Desktop; pe Windows, verifică integrarea WSL (pasul 1.2).
- **După `git pull`:** `make local-up` reconstruiește imaginea și aplică migrările noi.

NEVERIFICAT: pornirea efectivă cu Docker Desktop pe Windows/Mac (în CI se verifică doar `docker compose config` și
popularea demo pe Postgres real).
