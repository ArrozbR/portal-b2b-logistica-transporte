"""Peças web comuns: correlação, métricas, saúde e paginação.

- Middleware de X-Correlation-Id: lê o cabeçalho (ou gera um UUID), coloca
  nos logs e devolve na resposta.
- Métricas Prometheus reais em /metrics (o kit devolvia um número fixo, K10).
- /health (o processo está vivo) e /health/ready (banco e Redpanda
  respondem de verdade; 503 se não).
- Paginação padrão ?page=&size=, com size > 100 devolvendo 422.
"""

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass
from typing import Awaitable, Callable

from fastapi import APIRouter, FastAPI, Query, Request, Response
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

from .erros import resposta_problema
from .logs import agora_iso, correlation_id

log = logging.getLogger(__name__)

REQUISICOES = Counter(
    "http_requests_total", "Requisições HTTP recebidas", ["service", "method", "route", "status"]
)
DURACAO = Histogram(
    "http_request_duration_seconds", "Tempo de resposta HTTP", ["service", "method", "route"]
)
EVENTOS_CONSUMIDOS = Counter(
    "eventos_consumidos_total", "Eventos consumidos do Kafka", ["service", "topic", "resultado"]
)
EVENTOS_PUBLICADOS = Counter(
    "eventos_publicados_total", "Eventos publicados no Kafka pela outbox", ["service", "topic"]
)


def instalar_middleware(app: FastAPI, servico: str) -> None:
    @app.middleware("http")
    async def correlacao_e_metricas(request: Request, call_next):
        cid = request.headers.get("X-Correlation-Id") or str(uuid.uuid4())
        request.state.correlation_id = cid
        token = correlation_id.set(cid)
        inicio = time.perf_counter()
        try:
            resposta = await call_next(request)
        except Exception:
            log.exception("Erro não tratado na requisição")
            resposta = resposta_problema(request, 500, "ERRO_INTERNO", "Erro interno",
                                         "Ocorreu um erro inesperado. Informe o correlationId ao suporte.")
        finally:
            correlation_id.reset(token)

        rota = getattr(request.scope.get("route"), "path", "desconhecida")
        REQUISICOES.labels(servico, request.method, rota, str(resposta.status_code)).inc()
        DURACAO.labels(servico, request.method, rota).observe(time.perf_counter() - inicio)
        resposta.headers["X-Correlation-Id"] = cid
        resposta.headers["X-Service-Name"] = servico
        return resposta


Verificacao = Callable[[], Awaitable[None]]


def rotas_de_saude(servico: str, verificacoes: dict[str, Verificacao]) -> APIRouter:
    """Cria /health, /health/ready e /metrics.

    `verificacoes` mapeia um nome ("banco", "kafka") para uma função que
    levanta exceção se a dependência não responder.
    """
    rotas = APIRouter(tags=["saúde"])

    @rotas.get("/health")
    async def health():
        return {"status": "UP", "service": servico, "timestamp": agora_iso()}

    @rotas.get("/health/ready")
    async def ready():
        resultado, tudo_ok = {}, True
        for nome, verificar in verificacoes.items():
            try:
                await asyncio.wait_for(verificar(), timeout=3)
                resultado[nome] = "UP"
            except Exception as exc:  # qualquer falha deixa o serviço "não pronto"
                resultado[nome] = f"DOWN: {type(exc).__name__}"
                tudo_ok = False
        corpo = {"status": "READY" if tudo_ok else "NOT_READY", "service": servico,
                 "checks": resultado, "timestamp": agora_iso()}
        return JSONResponse(corpo, status_code=200 if tudo_ok else 503)

    @rotas.get("/metrics")
    async def metrics():
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    return rotas


@dataclass(frozen=True)
class Pagina:
    page: int
    size: int

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.size


def paginacao(
    page: int = Query(1, ge=1, description="Número da página, a partir de 1"),
    size: int = Query(10, ge=1, le=100, description="Itens por página (máximo 100)"),
) -> Pagina:
    return Pagina(page=page, size=size)


def resposta_paginada(itens: list, pagina: Pagina, total: int) -> dict:
    return {"items": itens, "page": pagina.page, "size": pagina.size, "total": total}
