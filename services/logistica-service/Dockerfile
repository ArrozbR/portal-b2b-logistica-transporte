# Build a partir da RAIZ do repositório (precisa do pacote comum/):
#   docker build -f services/logistica-service/Dockerfile .
# O kit usava o contexto da pasta do serviço e o import de `common` falhava (K4).
FROM python:3.12.7-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY comum/ /opt/comum/
RUN pip install /opt/comum

COPY services/logistica-service/logistica/ ./logistica/

RUN useradd --uid 1000 --create-home appuser
USER appuser

EXPOSE 8108
CMD ["uvicorn", "logistica.main:app", "--host", "0.0.0.0", "--port", "8108"]
