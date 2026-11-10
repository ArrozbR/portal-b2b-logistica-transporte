"""Ponto de entrada do logistica-service.

Sobe a API e, no mesmo processo, três rotinas em segundo plano:

- consumidor: lê pedido_criado, cotacao_recebida e pedido_atualizado do Kafka;
- outbox:     publica no Kafka os eventos gravados no banco;
- prazos:     a cada segundo, fecha rodadas e aplica a escolha automática.

Rodar: uvicorn logistica.main:app --host 0.0.0.0 --port 8108
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from comum import config
from comum.consumidor import ConsumidorIdempotente
from comum.db import BancoDeDados, conninfo_do_ambiente
from comum.erros import registrar_tratadores
from comum.kafka import iniciar_produtor, verificar
from comum.logs import configurar_logs
from comum.outbox import PublicadorOutbox
from comum.relogio import Relogio
from comum.tarefas import iniciar, parar, repetir
from comum.web import instalar_middleware, rotas_de_saude

from . import SCHEMA, SERVICO, TOPICO_DLT
from .api import criar_rotas
from .servico import Logistica, Prazos

configurar_logs(SERVICO, config.texto("LOG_LEVEL", "INFO"))

db = BancoDeDados(conninfo_do_ambiente(), max_conexoes=config.inteiro("DB_POOL_MAX", 5))
relogio = Relogio(db, SCHEMA)
logistica = Logistica(relogio, Prazos(
    rodada_segundos=config.inteiro("RODADA_COTACAO_SEGUNDOS", 10),
    decisao_segundos=config.inteiro("PRAZO_DECISAO_SEGUNDOS", 12 * 3600),
))
kafka: dict = {"produtor": None}

consumidor = ConsumidorIdempotente(
    db=db, schema=SCHEMA, servico=SERVICO, grupo=SERVICO, topico_dlt=TOPICO_DLT,
    tratadores={
        "pedido_criado": logistica.abrir_solicitacao,
        "cotacao_recebida": logistica.registrar_cotacao,
        "pedido_atualizado": logistica.cancelar_pedido,
    },
)


async def rodar_outbox() -> None:
    if kafka["produtor"] is None:
        kafka["produtor"] = await iniciar_produtor(SERVICO)
    await PublicadorOutbox(db, SCHEMA, SERVICO, kafka["produtor"]).executar()


async def rodar_prazos() -> None:
    await repetir(1.0, lambda: logistica.verificar_prazos(db))


async def kafka_pronto() -> None:
    if kafka["produtor"] is None:
        raise RuntimeError("produtor Kafka ainda não conectado")
    await verificar(kafka["produtor"])


@asynccontextmanager
async def ciclo_de_vida(_: FastAPI):
    await db.abrir()
    tarefas = iniciar({"consumidor": consumidor.executar, "outbox": rodar_outbox, "prazos": rodar_prazos})
    yield
    await parar(tarefas)
    if kafka["produtor"] is not None:
        await kafka["produtor"].stop()
    await db.fechar()


app = FastAPI(
    title="Logística e Frete",
    version="0.1.0",
    description="Solicitação de frete, cotações, escolha do frete, entrega e rastreio. Grupo 5.",
    lifespan=ciclo_de_vida,
)
registrar_tratadores(app)
instalar_middleware(app, SERVICO)
app.include_router(rotas_de_saude(SERVICO, {"banco": db.verificar, "kafka": kafka_pronto}))
app.include_router(criar_rotas(db, logistica))
