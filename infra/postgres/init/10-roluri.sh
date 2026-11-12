#!/bin/bash
# Rulează o singură dată, la prima pornire a volumului Postgres (mecanismul docker-entrypoint-initdb.d).
# Creează rolurile platformei; parolele vin din variabile de mediu (niciodată din repo).
#   ama_owner  - proprietarul bazei `ama`; rulează migrările
#   ama_app    - rolul de rulare al aplicației: NOSUPERUSER NOBYPASSRLS, fără drept de a crea obiecte
#   ama_backup - citește tot (inclusiv peste RLS) pentru pg_dump; poate crea baze de probă pentru testul de restaurare
set -euo pipefail

: "${AMA_OWNER_DB_PASSWORD:?}" "${AMA_APP_DB_PASSWORD:?}" "${AMA_BACKUP_DB_PASSWORD:?}"
DB="${POSTGRES_DB:-ama}"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres \
  -v owner_pw="$AMA_OWNER_DB_PASSWORD" -v app_pw="$AMA_APP_DB_PASSWORD" -v backup_pw="$AMA_BACKUP_DB_PASSWORD" \
  -v db="$DB" <<'SQL'
CREATE ROLE ama_owner LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS PASSWORD :'owner_pw';
CREATE ROLE ama_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS PASSWORD :'app_pw';
CREATE ROLE ama_backup LOGIN NOSUPERUSER CREATEDB NOCREATEROLE BYPASSRLS PASSWORD :'backup_pw';
GRANT pg_read_all_data TO ama_backup;
ALTER DATABASE :"db" OWNER TO ama_owner;
REVOKE ALL ON DATABASE :"db" FROM PUBLIC;
GRANT CONNECT ON DATABASE :"db" TO ama_app, ama_backup;
SQL

# Extensia vector: creată de superutilizator, în bază și în template1 (bazele de probă ale testului de restaurare
# pornesc din template1, deci o au deja când pg_restore ajunge la ea).
for target in "$DB" template1; do
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$target" -c 'CREATE EXTENSION IF NOT EXISTS vector;'
done

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$DB" <<'SQL'
-- Schema public: proprietarul creează obiecte, aplicația doar le folosește.
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO ama_app, ama_backup;
GRANT CREATE ON SCHEMA public TO ama_owner;
-- Tot ce creează ama_owner (migrările) devine utilizabil de aplicație, fără drept de DDL.
ALTER DEFAULT PRIVILEGES FOR ROLE ama_owner IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO ama_app;
ALTER DEFAULT PRIVILEGES FOR ROLE ama_owner IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO ama_app;
ALTER DEFAULT PRIVILEGES FOR ROLE ama_owner IN SCHEMA public
  GRANT EXECUTE ON FUNCTIONS TO ama_app;
SQL
