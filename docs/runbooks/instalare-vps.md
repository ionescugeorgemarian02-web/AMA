# Instalarea de la zero pe VPS

Nu a fost rulat pe un server real (D-001): la migrare, urmărește pașii și notează abaterile în `docs/registre/masurare-vps.md`.
Simboluri: `<ip>` adresa serverului, `<domeniu>` domeniul tău, `<proprietar>` contul GitHub.

## 1. Înainte de server
1. DNS: patru înregistrări A către `<ip>`: `<domeniu>`, `app.<domeniu>`, `media.<domeniu>`, `staging.<domeniu>`.
2. GitHub, **Settings → Actions → General → Workflow permissions**: „Read repository contents” (livrarea cere `packages: write` pe cont propriu). După prima publicare, în **Packages → ama → Package settings** lasă pachetul privat sau public după preferință.
3. Cheile de backup (pe laptopul tău, nu pe server):
   `age-keygen -o cheie-proprietar.key` (păstrează fișierul în două locuri sigure) și `age-keygen -o verificare.key`. Notează cele două chei publice (`age1…`).
4. Un spațiu de stocare extern compatibil rclone și datele lui de acces (punct deschis în 26).

## 2. Pregătirea serverului (ca root, o singură dată)
```bash
ssh root@<ip>
apt-get update && apt-get install -y git
git clone https://github.com/<proprietar>/<depozit>.git /root/ama && cd /root/ama
AMA_ADMIN_SSH_PUBKEY="$(cat cheia-ta-publica.pub)" AMA_REPO_URL=https://github.com/<proprietar>/<depozit>.git bash infra/vps/bootstrap.sh
```
Deschide un al doilea terminal și verifică `ssh ama@<ip>` ÎNAINTE de a închide sesiunea root (autentificarea cu parolă a fost oprită).

## 3. Fișierele de mediu (ca `ama`, în `/srv/ama/env`, mod 600, în afara repo-ului)
```bash
ssh ama@<ip>
export DOCKER_HOST=unix:///run/user/$(id -u)/docker.sock
cd /srv/ama/repo/infra/env
for f in staging production edge; do cp $f.env.example /srv/ama/env/$f.env; done
cp rclone.conf.example /srv/ama/env/backup/rclone.conf
chmod 600 /srv/ama/env/*.env /srv/ama/env/backup/*
```
Completează fiecare `CHANGE_ME`: parole și chei cu `openssl rand -hex 24` (diferite în staging și producție); `AMA_DEPLOY_TOKEN` identic în `production.env` și `edge.env`, minim 32 de caractere; `DOCKER_SOCK` în `edge.env` cu `id -u` al lui `ama`; domeniile; `AMA_DEPLOYER_REPO=ghcr.io/<proprietar>/<depozit>` (litere mici); hash-ul parolei de staging din `docker run --rm caddy:2-alpine caddy hash-password` (între ghilimele simple). În `production.env`: `AMA_BACKUP_AGE_RECIPIENTS` = cele două chei publice. Cheia privată de verificare: `/srv/ama/env/backup/verificare.key`, mod 600. Pentru pachet privat: `DOCKER_CONFIG=/srv/ama/env/docker docker login ghcr.io -u <utilizator>` cu un token cu drept doar de citire pachete, aceleași valori în `edge.env` (`AMA_DEPLOYER_REGISTRY_*`).

## 4. Pornirea (ca `ama`)
Prima imagine trebuie să existe în GHCR: împinge pe `main` și așteaptă ca fluxul „Livrare” să termine; copiază din rezumatul lui adresa `ghcr.io/…@sha256:…` (`$IMG`).
```bash
cd /srv/ama/repo/infra/compose
docker compose -p ama-edge --env-file /srv/ama/env/edge.env -f edge.yml up -d --build
docker compose -p ama-staging --env-file /srv/ama/env/staging.env -f base.yml -f staging.yml up -d --wait postgres
docker compose -p ama-prod --env-file /srv/ama/env/production.env -f base.yml -f production.yml up -d --wait postgres
docker compose -p ama-prod --env-file /srv/ama/env/production.env -f base.yml -f production.yml up -d --build backup
```
Prima versiune în fiecare stivă o pornește deployer-ul (rulează migrările, pornește slotul, verifică `/readyz`) și o înregistrează în starea lui:
```bash
docker exec ama-edge-deployer-1 python /app/deployer.py deploy staging $IMG
docker exec ama-edge-deployer-1 python /app/deployer.py deploy production $IMG
```
Verifică: `infra/deploy/smoke.sh https://app.<domeniu> 60`; staging: `AMA_SMOKE_USER=ama AMA_SMOKE_PASSWORD=… infra/deploy/smoke.sh https://staging.<domeniu> 60`.

## 5. Verificări finale
- `ufw status` (22, 80, 443); `ss -tlnp` nu arată Postgres pe adrese publice.
- Repornește serverul: toate serviciile revin singure.
- Pornește un backup acum: `docker exec ama-prod-backup-1 python3 /usr/local/bin/ama_backup.py backup`, apoi `... restore-test` (vezi `restaurare.md`).
- De acum, o schimbare pe `main` ajunge singură pe staging; producția doar din panou.
