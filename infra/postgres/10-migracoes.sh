#!/bin/bash
# Aplica as migrações dos dois serviços, em ordem, como o usuário portal_ddl.
# Roda só na primeira subida do Postgres (volume vazio). Para recriar o banco:
#   docker compose down -v && docker compose up -d --build
set -euo pipefail

for arquivo in /migracoes/logistica/*.sql /migracoes/transportadoras/*.sql; do
    echo "==> Aplicando $arquivo"
    { echo "SET ROLE portal_ddl;"; cat "$arquivo"; } \
        | psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB"
done
