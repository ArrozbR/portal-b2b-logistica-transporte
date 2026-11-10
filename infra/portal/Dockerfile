# Portal de desenvolvimento: telas estáticas + proxy para as APIs.
# Build a partir da raiz do repositório.
FROM nginx:1.27-alpine

COPY infra/portal/nginx.conf /etc/nginx/conf.d/default.conf
COPY frontend/ /usr/share/nginx/html/
