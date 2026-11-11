#!/usr/bin/env bash
# Pornește un Postgres local, de unică folosință, pentru teste (fără Docker).
# Folosire: scripts/pg_test.sh start|stop|url
# În CI nu se folosește: acolo Postgres vine ca serviciu, iar AMA_TEST_DATABASE_ADMIN_URL este setată.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PGDIR="${AMA_PGTEST_DIR:-$ROOT/.pgtest}"
PORT="${AMA_PGTEST_PORT:-54329}"
BIN="$(dirname "$(command -v pg_ctl 2>/dev/null || ls /usr/lib/postgresql/*/bin/pg_ctl | sort -V | tail -1)")"

run() { # initdb/postgres refuză să ruleze ca root
  if [ "$(id -u)" = "0" ]; then
    local q; q="$(printf '%q ' "$@")"
    su postgres -s /bin/bash -c "$q"
  else "$@"; fi
}

case "${1:-}" in
  start)
    if [ ! -f "$PGDIR/PG_VERSION" ]; then
      mkdir -p "$PGDIR"
      [ "$(id -u)" = "0" ] && chown postgres "$PGDIR"
      run "$BIN/initdb" -D "$PGDIR" -U postgres --auth=trust -E UTF8 --locale=C.UTF-8 >/dev/null
    fi
    if ! run "$BIN/pg_ctl" -D "$PGDIR" status >/dev/null 2>&1; then
      run "$BIN/pg_ctl" -D "$PGDIR" -o "-p $PORT -c listen_addresses=127.0.0.1 -c unix_socket_directories=$PGDIR -c fsync=off" -l "$PGDIR/log" -w start >/dev/null
    fi
    ;;
  stop) run "$BIN/pg_ctl" -D "$PGDIR" -m fast stop >/dev/null 2>&1 || true ;;
  url) ;;
  *) echo "folosire: $0 start|stop|url" >&2; exit 2 ;;
esac
echo "postgresql+psycopg://postgres@127.0.0.1:$PORT/postgres"
