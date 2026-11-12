#!/usr/bin/env bash
# Test de fum (F1.8): verifică /healthz și /readyz ale unei adrese de bază.
#   infra/deploy/smoke.sh http://staging-blue:8000 [secunde_de_așteptare]
# Cod de ieșire 0 = ambele răspund corect. Cu AMA_SMOKE_USER/AMA_SMOKE_PASSWORD folosește autentificare basic
# (pentru staging prin proxy). Nu afișează parole.
set -euo pipefail

base="${1:-}"
wait_s="${2:-0}"
[ -n "$base" ] || { echo "folosire: $0 <adresa-de-baza> [secunde]" >&2; exit 2; }
base="${base%/}"

auth=()
if [ -n "${AMA_SMOKE_USER:-}" ]; then
  auth=(--user "${AMA_SMOKE_USER}:${AMA_SMOKE_PASSWORD:-}")
fi

get() { # $1 = cale; scrie corpul în $body și întoarce codul HTTP
  curl -sS --max-time 5 -o "$body" -w '%{http_code}' "${auth[@]}" "${base}$1" 2>/dev/null || true
}

body="$(mktemp)"
trap 'rm -f "$body"' EXIT
deadline=$(( $(date +%s) + wait_s ))
while :; do
  health="$(get /healthz)"
  health_ok=0
  if [ "$health" = "200" ] && grep -q '"status" *: *"ok"' "$body"; then health_ok=1; fi
  ready="$(get /readyz)"
  if [ "$health_ok" = 1 ] && [ "$ready" = "200" ]; then
    echo "OK  /healthz=$health /readyz=$ready ($base)"
    exit 0
  fi
  if [ "$(date +%s)" -ge "$deadline" ]; then
    echo "ESEC /healthz=$health (ok=$health_ok) /readyz=$ready ($base)" >&2
    exit 1
  fi
  sleep 2
done
