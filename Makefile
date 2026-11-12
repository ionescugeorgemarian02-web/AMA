.PHONY: check lint types guards test fmt pg-start pg-stop audit

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
