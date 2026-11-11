# Revenirea la versiunea anterioară

Deployer-ul păstrează versiunea veche (container oprit, imagine pe disc). Revenirea durează câteva secunde și nu atinge baza de date: migrările sunt compatibile cu versiunea anterioară (AGENTS.md), deci versiunea veche rulează pe schema nouă.

## Automat
Dacă versiunea nouă devine nesănătoasă în fereastra de după mutare, deployer-ul revine singur și raportează `revenita`. Dacă nu devine sănătoasă deloc, traficul nu se mută și raportează `esuata`.

## Din panou (după F2.9)
„Revenire” pe producție creează o cerere `tip: revenire`; deployer-ul o preia în cel mult un minut.

## De mână (panoul nu răspunde)
```bash
ssh ama@<ip>; export DOCKER_HOST=unix:///run/user/$(id -u)/docker.sock
docker exec ama-edge-deployer-1 python /app/deployer.py status      # vezi active/previous
docker exec ama-edge-deployer-1 python /app/deployer.py rollback production    # sau staging
infra/deploy/smoke.sh https://app.<domeniu> 60
```
Dacă nu există `previous`, comanda eșuează și nu schimbă nimic: promovează o amprentă cunoscută bună cu `deploy production <ghcr.io/…@sha256:…>`.

## După revenire
1. Versiunea stricată nu se reia singură pe staging mai mult de 3 ori; staging așteaptă o versiune nouă.
2. Dacă migrarea nouă nu e compatibilă înapoi, oprește producția și restaurează (`restaurare.md`); apoi repară migrarea într-o versiune nouă.
3. Notează cauza și deschide corecția.
