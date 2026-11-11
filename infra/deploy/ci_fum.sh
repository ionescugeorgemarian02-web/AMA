#!/usr/bin/env bash
# Test de fum al imaginii, cu o bază reală (F1.8): Postgres cu scriptul de roluri din infra/, migrările rulate
# ca proprietar, aplicația pornită ca `ama_app`, apoi /healthz și /readyz. Folosit în CI și local:
#   infra/deploy/ci_fum.sh ama:ci
# Parolele se generează la rulare; nimic nu rămâne în urmă.
set -euo pipefail

image="${1:?folosire: $0 <imagine>}"
root="$(cd "$(dirname "$0")/../.." && pwd)"
pg_image="pgvector/pgvector:pg16@sha256:0dd3149a06e4579a0d70d8fef9945636cd514005e7237deb27f9b67886f8dc4f"
net="ama-fum-$$"
port="${AMA_FUM_PORT:-8000}"
rand() { od -An -N24 -tx1 /dev/urandom | tr -d ' \n'; }
pw_super="$(rand)"; pw_owner="$(rand)"; pw_app="$(rand)"; pw_backup="$(rand)"

cleanup() {
  docker rm -f "$net-app" "$net-pg" >/dev/null 2>&1 || true
  docker network rm "$net" >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker network create "$net" >/dev/null
docker run -d --name "$net-pg" --network "$net" --network-alias postgres \
  -e POSTGRES_PASSWORD="$pw_super" -e POSTGRES_DB=ama \
  -e AMA_OWNER_DB_PASSWORD="$pw_owner" -e AMA_APP_DB_PASSWORD="$pw_app" -e AMA_BACKUP_DB_PASSWORD="$pw_backup" \
  -v "$root/infra/postgres/init:/docker-entrypoint-initdb.d:ro" "$pg_image" >/dev/null

# Gata abia când rolurile există și serverul ascultă pe rețea (scriptul de inițializare rulează pe un server temporar).
for _ in $(seq 1 60); do
  if docker run --rm --network "$net" -e PGPASSWORD="$pw_app" "$pg_image" \
      psql -h postgres -U ama_app -d ama -Atc 'SELECT 1' >/dev/null 2>&1; then ok=1; break; fi
  sleep 1
done
[ "${ok:-0}" = 1 ] || { echo "ESEC: Postgres nu a pornit" >&2; docker logs "$net-pg" 2>&1 | tail -30 >&2; exit 1; }

owner_url="postgresql+psycopg://ama_owner:${pw_owner}@postgres:5432/ama"
docker run --rm --network "$net" --read-only --tmpfs /tmp -e AMA_ENV=test \
  -e AMA_DATABASE_OWNER_URL="$owner_url" -e AMA_DATABASE_URL="$owner_url" "$image" alembic upgrade head

docker run -d --name "$net-app" --network "$net" --read-only --tmpfs /tmp -p "127.0.0.1:$port:8000" \
  -e AMA_ENV=test -e AMA_DATABASE_URL="postgresql+psycopg://ama_app:${pw_app}@postgres:5432/ama" \
  -e AMA_SECRET_KEY="$(rand)" -e AMA_MASTER_KEY="$(rand)" "$image" >/dev/null

if ! "$root/infra/deploy/smoke.sh" "http://127.0.0.1:$port" 60; then
  docker logs "$net-app" 2>&1 | tail -40 >&2
  exit 1
fi
