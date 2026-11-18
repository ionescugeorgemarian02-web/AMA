#!/usr/bin/env bash
# Testele de avarie (F15.1, docs/25 §25.3), pe scenarii. Local: pornește singur Postgres-ul de test.
# Pe staging: AMA_TEST_DATABASE_ADMIN_URL spre Postgres-ul de staging (o bază de test separată se creează și
# se șterge de teste), rulat din containerul aplicației sau de pe VPS cu repo-ul la versiunea livrată.
# Ieșire: raportul în $AMA_AVARIE_DIR (implicit ./avarie-raport): junit.xml, raport.json; cod 0 = toate trec.
set -euo pipefail
cd "$(dirname "$0")/.."
OUT="${AMA_AVARIE_DIR:-avarie-raport}"
mkdir -p "$OUT"
if [ -z "${AMA_TEST_DATABASE_ADMIN_URL:-}" ]; then
  AMA_TEST_DATABASE_ADMIN_URL="$(scripts/pg_test.sh start)"
  export AMA_TEST_DATABASE_ADMIN_URL
fi
mapfile -t NODURI < <(uv run python -m tests.avarie.catalog)
set +e
uv run pytest -q -p no:cacheprovider --junitxml="$OUT/junit.xml" -o junit_family=xunit1 tests/avarie "${NODURI[@]}"
set -e
uv run python -m tests.avarie.raport "$OUT/junit.xml" "$OUT/raport.json"
