# Postgres do ambiente de desenvolvimento, com os scripts de inicialização e as
# migrações dos dois serviços DENTRO da imagem (sem montar pastas do host, que
# não funciona quando o repositório está num drive virtual, como o Google Drive).
# Build a partir da raiz do repositório.
FROM postgres:16.4

COPY infra/postgres/*.sh /docker-entrypoint-initdb.d/
COPY services/logistica-service/migracoes/ /migracoes/logistica/
COPY services/transportadoras-service/migracoes/ /migracoes/transportadoras/

# Garante quebra de linha LF mesmo se o arquivo veio do Windows com CRLF.
RUN sed -i 's/\r$//' /docker-entrypoint-initdb.d/*.sh /migracoes/*/*.sql
