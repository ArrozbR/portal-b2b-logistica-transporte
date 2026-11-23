# Portal de desenvolvimento: telas estáticas + proxy para as APIs.
# Build a partir da raiz do repositório.
FROM nginx:1.27-alpine

# Modelo: a imagem oficial troca ${AUTH_URL} ao subir (envsubst, só variáveis definidas).
ENV AUTH_URL=http://usuarios-falso:8101
COPY infra/portal/nginx.conf /etc/nginx/templates/default.conf.template
COPY frontend/ /usr/share/nginx/html/
