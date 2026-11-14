# Imaginea aplicației AMA (F1.8). Toate imaginile de bază sunt fixate pe amprentă (garda scripts/check_pins.py).
# Construire: docker build --build-arg AMA_VERSION=$(git rev-parse --short HEAD) -t ama:local .

# Etapa de construcție: instalează dependențele exact din uv.lock (cu hash-uri), fără pachetele de dezvoltare.
FROM python:3.13-slim@sha256:e48f59cdba69a3cbd9ed2cf0f348d90d45a8d350d98134cf1070bc106ee9ed90 AS build
# uv se instalează din PyPI, cu versiune și hash-uri fixate (infra/docker/uv.requirements.txt).
COPY infra/docker/uv.requirements.txt /tmp/uv.requirements.txt
RUN pip install --no-cache-dir --require-hashes -r /tmp/uv.requirements.txt
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never UV_NO_CACHE=1
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project
COPY app ./app
# alembic.ini poate lipsi cât timp migrările nu există; glob-ul nu pică dacă pyproject.toml se potrivește.
COPY pyproject.toml alembic.ini* ./
COPY migrations ./migrations
COPY prompts ./prompts
COPY rulepacks ./rulepacks
COPY evaluare ./evaluare

# Etapa de rulare: fără uv, fără compilator, utilizator fără drepturi, sistem de fișiere compatibil cu read-only.
FROM python:3.13-slim@sha256:e48f59cdba69a3cbd9ed2cf0f348d90d45a8d350d98134cf1070bc106ee9ed90 AS runtime
ARG AMA_VERSION=dev
ENV AMA_VERSION=${AMA_VERSION} \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UVICORN_WORKERS=2
# Media (F8): ffmpeg (randare, control G6) și fontul cu toate diacriticele românești (subtitrări, șabloane).
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*
RUN groupadd --system --gid 10001 ama \
    && useradd --system --uid 10001 --gid ama --no-create-home --shell /usr/sbin/nologin ama
WORKDIR /app
COPY --from=build --chown=root:root /app /app
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import sys,urllib.request as u; sys.exit(0 if u.urlopen('http://127.0.0.1:8000/healthz', timeout=2).status == 200 else 1)"]
# Rulează în spatele proxy-ului din rețeaua Docker; portul nu se publică pe gazdă.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]
