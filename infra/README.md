# Infrastructură (F1.8 livrare, F1.9 backup)

Totul se validează în repo și în CI (D-001); VPS-ul vine la final. Specificații: `docs/specs/F1.8.md`, `docs/specs/F1.9.md`. Instalare: `docs/runbooks/`.

| Director | Ce conține |
| --- | --- |
| `compose/` | `base.yml` (postgres, migrate, `worker`, sloturile `app_blue`/`app_green`), `staging.yml`, `production.yml` (+ `backup`), `edge.yml` (`proxy`, `deployer`) |
| `proxy/Caddyfile` | trei nume publice + staging cu parolă, certificate automate, antete, `/intern/*` blocat |
| `postgres/init/` | rolurile `ama_owner`, `ama_app`, `ama_backup` și extensia `vector` |
| `deployer/` | serviciul intern de livrare (stdlib) |
| `backup/` | scriptul de backup/restaurare și imaginea lui |
| `deploy/smoke.sh` | test de fum pe `/healthz` și `/readyz` |
| `vps/bootstrap.sh` | instalarea inițială a serverului (o singură dată, ca root) |
| `env/*.example` | modele pentru fișierele de mediu (copiate în `/srv/ama/env`, în afara repo-ului) |
| `docker/uv.requirements.txt` | uv fixat cu hash-uri, folosit de `Dockerfile` |

## Reguli
- Doar `proxy` publică porturi (80/443). Postgres stă pe o rețea internă fără ieșire; aplicația și serviciile interne sunt vizibile doar în rețeaua `ama-edge`.
- Fiecare imagine din fișierele Compose și din Dockerfile este fixată pe amprentă (`scripts/check_pins.py`). Imaginile aplicației vin din registru, după amprentă (`AMA_IMAGE_*` setate de deployer).
- Secretele vin din `/srv/ama/env/*.env` (mod 600), niciodată din repo. Modelele folosesc `CHANGE_ME`.

## Servicii viitoare (se adaugă în `base.yml`/`production.yml` în fazele lor)
Limitele rezervate vin din tabelul 6.4 (24 GB, 8 nuclee). Totalul curent (proxy 0,1 + app 1 + postgres 3,5 + staging 1,5) lasă loc pentru ele.

| Serviciu | Rol | Limită de memorie | Faza |
| --- | --- | --- | --- |
| worker-light | Apeluri LLM, conectori, validatori ușori, embeddings (24 joburi). Din F2.1 există serviciul `worker` (`python -m app.worker`, `restart: unless-stopped`, mutat de deployer odată cu aplicația); celelalte capabilități se adaugă în F3 | 2 GB | F2.1 |
| worker-heavy | Randare, voce, transcriere, OCR (2 culoare grele) | 5 GB | F3 |
| local-llm | Model local de text, încărcat permanent | 6,5 GB | F3.5 |
| browser | Chromium headless, 3 pagini în paralel | 1,5 GB | F4 |

## Servicii adăugate de F1.8/F1.9, în afara tabelului 6.4
`deployer` 128 MB, `backup` 256 MB, `migrate` 512 MB (doar în timpul unei implementări); un al doilea slot de aplicație rulează scurt la implementare (+1 GB în producție). Toate încap în rezerva de 3 GB.

## Comenzi utile (în repo)
```bash
docker compose -p ama-staging --env-file <staging.env> -f compose/base.yml -f compose/staging.yml config -q
python3 infra/deployer/deployer.py status   # cu AMA_DEPLOYER_REPO și AMA_DEPLOY_TOKEN setate
```
