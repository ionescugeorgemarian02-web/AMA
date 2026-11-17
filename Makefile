.PHONY: check lint types guards test fmt pg-start pg-stop audit local-env local-up local-down local-reset

check: lint types guards test

lint:
	uv run ruff check .
	uv run ruff format --check .

fmt:
	uv run ruff check --fix .
	uv run ruff format .

types:
	uv run mypy

guards:
	uv lock --check
	uv run python scripts/check_pins.py
	uv run python scripts/check_motor.py
	uv run python scripts/check_efecte.py
	uv run python scripts/check_gateway.py
	uv run python scripts/check_invatare.py
	uv run detect-secrets-hook --baseline .secrets.baseline $$(git ls-files)

# Vulnerabilități cunoscute în dependențe. Are nevoie de rețea; rulează în CI.
audit:
	uv export --locked --no-emit-project --format requirements-txt -o /tmp/ama-req.txt -q
	uv run pip-audit --require-hashes --disable-pip -r /tmp/ama-req.txt

pg-start:
	@scripts/pg_test.sh start

pg-stop:
	@scripts/pg_test.sh stop

# Local: pornește un Postgres de test dacă AMA_TEST_DATABASE_ADMIN_URL nu este setată.
test:
	@if [ -z "$$AMA_TEST_DATABASE_ADMIN_URL" ]; then export AMA_TEST_DATABASE_ADMIN_URL="$$(scripts/pg_test.sh start)"; fi; \
	uv run pytest

# Modul local (docs/runbooks/rulare-locala.md): Docker Desktop, aplicația pe http://localhost:8000.
LOCAL_ENV := infra/env/local.env
LOCAL := docker compose -p ama-local --env-file $(LOCAL_ENV) -f infra/compose/local.yml

local-env:
	@if [ ! -f $(LOCAL_ENV) ]; then \
	  awk '/^#/ { print; next } { while (index($$0, "GENEREAZA_LA_PORNIRE")) { c = "openssl rand -hex 24"; c | getline r; close(c); \
	    sub(/GENEREAZA_LA_PORNIRE/, r) } print }' infra/env/local.env.example > $(LOCAL_ENV); \
	  chmod 600 $(LOCAL_ENV); echo "Creat $(LOCAL_ENV) (parole generate)."; fi

local-up: local-env
	$(LOCAL) up -d --build --wait
	$(LOCAL) exec -T app python -m app.demo.populare
	@echo "Gata: http://localhost:8000  (cont: vezi AMA_DEMO_EMAIL / AMA_DEMO_PAROLA în $(LOCAL_ENV))"

local-down:
	$(LOCAL) down

# Șterge baza și media locale (volumele), apoi pornește din nou, cu datele demo.
local-reset: local-env
	$(LOCAL) down -v
	$(MAKE) local-up
