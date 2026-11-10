# Imagem que só cria os tópicos e termina. Build a partir da raiz do repositório.
FROM docker.redpanda.com/redpandadata/redpanda:v24.2.7

COPY infra/redpanda/criar-topicos.sh /scripts/criar-topicos.sh
USER root
RUN sed -i 's/\r$//' /scripts/criar-topicos.sh
USER redpanda

ENTRYPOINT ["/bin/bash", "/scripts/criar-topicos.sh"]
