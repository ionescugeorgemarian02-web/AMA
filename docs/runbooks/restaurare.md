# Restaurarea din backup

Ținte (22.6): pierdere maximă 24 h, repunere în funcțiune în 4 h. Ai nevoie de cheia privată a proprietarului (`cheie-proprietar.key`) și de datele de acces la stocarea externă.

## A. Verificarea fără pagubă (săptămânal, automat; manual când vrei)
`docker exec ama-prod-backup-1 python3 /usr/local/bin/ama_backup.py restore-test` → JSON cu `"stare": "reusit"`. Rezultatul rămâne în `ultima-restaurare-test.json`.

## B. Restaurarea reală (server pierdut sau bază stricată)
1. Server nou: `docs/runbooks/instalare-vps.md`, pașii 1–3 (fișierele de mediu pot fi recuperate la pasul 4). Oprește aplicația: `docker compose -p ama-prod … stop app_blue app_green` (sau nu le porni încă).
2. Descarcă copia dorită (cea mai nouă este ultimul director):
   `rclone lsf --dirs-only <destinatie>` apoi `rclone copy <destinatie>/<ID> ./copie` (cu `RCLONE_CONFIG=/srv/ama/env/backup/rclone.conf`).
3. Verifică sumele: `sha256sum copie/*.age` față de `copie/manifest.json`. Nu folosi o copie care nu se potrivește; ia-o pe cea dinainte.
4. Decriptează: `age -d -i cheie-proprietar.key -o baza.dump copie/baza.dump.age` (la fel `media.tar.gz.age`, `configurare.tar.gz.age`).
5. Baza (stiva de producție pornită doar cu `postgres`, volum nou):
   `docker compose -p ama-prod … up -d --wait postgres`, apoi
   `docker exec -i ama-prod-postgres-1 pg_restore -U postgres -d ama --clean --if-exists --no-owner < baza.dump`
   și `docker exec ama-prod-postgres-1 psql -U postgres -d ama -c "ALTER DATABASE ama OWNER TO ama_owner"` dacă lipsesc drepturile; migrările se aplică ulterior de livrare.
6. Media: `docker run --rm -v ama-prod_media:/m -v $PWD:/c alpine tar -xzf /c/media.tar.gz -C /m`.
7. Configurarea: `tar -xzf configurare.tar.gz -P --transform 's|^/data/config/env|/srv/ama/env|; s|^/data/config/proxy|/tmp/proxy-vechi|'` pentru fișierele de mediu (`Caddyfile` vine oricum din repo).
8. Pornește versiunea din registru: `docker exec ama-edge-deployer-1 python /app/deployer.py deploy production <ghcr.io/…@sha256:…>`, apoi `infra/deploy/smoke.sh https://app.<domeniu> 60`.
9. Notează în jurnal: ID-ul copiei, durata, ce s-a pierdut (între ID și incident). Rulează un backup nou.

## C. Dacă restaurarea de test eșuează
Citește `eroare` din `ultima-restaurare-test.json`. „copie coruptă”: ia copia anterioară (`AMA_RESTORE_SNAPSHOT=<ID>`) și verifică destinația. „lipsește cheia”: restaurează `verificare.key`. Orice backup care nu trece testul se tratează ca inexistent până se repară.
