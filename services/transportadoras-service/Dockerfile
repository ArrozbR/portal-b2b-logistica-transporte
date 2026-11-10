# Build a partir da RAIZ do repositório (precisa do pacote comum/):
#   docker build -f services/transportadoras-service/Dockerfile .
FROM python:3.12.7-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY comum/ /opt/comum/
RUN pip install /opt/comum

COPY services/transportadoras-service/transportadoras/ ./transportadoras/

RUN useradd --uid 1000 --create-home appuser
USER appuser

EXPOSE 8109
CMD ["uvicorn", "transportadoras.main:app", "--host", "0.0.0.0", "--port", "8109"]
