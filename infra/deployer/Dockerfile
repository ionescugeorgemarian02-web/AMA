# Serviciul intern de livrare (F1.8): Python (doar biblioteca standard) + clientul Docker și pluginul Compose.
# Clientul Docker și Compose vin din imaginea oficială docker:28-cli, fixată pe amprentă.
FROM docker:28-cli@sha256:625d9431a9f54c5a2bc90f24f0e1c3d55b1349fd857dd85035f98c2c9acbdd4d AS docker

FROM python:3.13-slim@sha256:e48f59cdba69a3cbd9ed2cf0f348d90d45a8d350d98134cf1070bc106ee9ed90
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
COPY --from=docker /usr/local/bin/docker /usr/local/bin/docker
COPY --from=docker /usr/local/libexec/docker/cli-plugins/docker-compose /usr/local/libexec/docker/cli-plugins/docker-compose
COPY deployer.py /app/deployer.py
RUN mkdir -p /var/lib/ama-deployer
WORKDIR /app
CMD ["python", "/app/deployer.py", "run"]
