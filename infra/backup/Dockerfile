# Serviciul de backup (F1.9): pg_dump 16, age, rclone, Python (doar biblioteca standard).
# Ubuntu 24.04 are aceleași versiuni ca runnerul CI (ubuntu-24.04), deci testul de integrare rulează cu aceleași unelte.
FROM ubuntu:24.04@sha256:fe81560990fae86dc4743202b2cb4d3df98d0bcf949173cecef15ce1127ef852
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
# NEVERIFICAT: pachetele apt nu sunt fixate pe versiune (doar imaginea de bază e fixată pe amprentă).
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates postgresql-client-16 age rclone python3 \
    && rm -rf /var/lib/apt/lists/*
COPY ama_backup.py /usr/local/bin/ama_backup.py
RUN mkdir -p /var/lib/ama-backup/work /var/lib/ama-backup/status
VOLUME ["/var/lib/ama-backup/work", "/var/lib/ama-backup/status"]
CMD ["python3", "/usr/local/bin/ama_backup.py", "serve"]
