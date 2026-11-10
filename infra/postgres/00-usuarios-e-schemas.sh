#!/bin/bash
# Cria os usuários e os schemas do grupo, no mesmo padrão do kit:
#   portal_ddl            dono dos schemas; roda as migrações
#   svc_logistica         usado pelo logistica-service (só DML no schema logistica)
#   svc_transportadoras   usado pelo transportadoras-service (só DML no schema transportadoras)
# As senhas vêm das variáveis de ambiente do docker-compose (arquivo .env).
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
    -v ddl_senha="$PORTAL_DDL_SENHA" \
    -v logistica_senha="$SVC_LOGISTICA_SENHA" \
    -v transportadoras_senha="$SVC_TRANSPORTADORAS_SENHA" <<'SQL'
CREATE ROLE portal_ddl WITH LOGIN PASSWORD :'ddl_senha';
CREATE ROLE svc_logistica WITH LOGIN PASSWORD :'logistica_senha' CONNECTION LIMIT 12;
CREATE ROLE svc_transportadoras WITH LOGIN PASSWORD :'transportadoras_senha' CONNECTION LIMIT 12;

REVOKE CREATE ON SCHEMA public FROM PUBLIC;

CREATE SCHEMA logistica AUTHORIZATION portal_ddl;
CREATE SCHEMA transportadoras AUTHORIZATION portal_ddl;

GRANT USAGE ON SCHEMA logistica TO svc_logistica;
GRANT USAGE ON SCHEMA transportadoras TO svc_transportadoras;
SQL
