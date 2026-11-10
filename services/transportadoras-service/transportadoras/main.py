"""Ponto de entrada do transportadoras-service.

Sobe a API e, no mesmo processo, duas rotinas em segundo plano:

- consumidor: lê solicitacao_frete_criada (emite as cotações simuladas) e
  relogio_ajustado (sincroniza o relógio do módulo);
- outbox:     publica no Kafka os eventos gravados no banco.

Rodar: uvicorn transportadoras.main:app --host 0.0.0.0 --port 8109
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
from comum.tarefas import iniciar, parar
from comum.web import instalar_middleware, rotas_de_saude

from . import SCHEMA, SERVICO, TOPICO_DLT
from .api import criar_rotas
from .servico import Transportadoras

configurar_logs(SERVICO, config.texto("LOG_LEVEL", "INFO"))

db = BancoDeDados(conninfo_do_ambiente(), max_conexoes=config.inteiro("DB_POOL_MAX", 5))
relogio = Relogio(db, SCHEMA)
transportadoras = Transportadoras(relogio)
kafka: dict = {"produtor": None}

consumidor = ConsumidorIdempotente(
    db=db, schema=SCHEMA, servico=SERVICO, grupo=SERVICO, topico_dlt=TOPICO_DLT,
    tratadores={
        "solicitacao_frete_criada": transportadoras.cotar_automaticamente,
        "relogio_ajustado": transportadoras.sincronizar_relogio,
    },
)


async def rodar_outbox() -> None:
    if kafka["produtor"] is None:
        kafka["produtor"] = await iniciar_produtor(SERVICO)
    await PublicadorOutbox(db, SCHEMA, SERVICO, kafka["produtor"]).executar()


async def kafka_pronto() -> None:
    if kafka["produtor"] is None:
        raise RuntimeError("produtor Kafka ainda não conectado")
    await verificar(kafka["produtor"])


@asynccontextmanager
async def ciclo_de_vida(_: FastAPI):
    await db.abrir()
    tarefas = iniciar({"consumidor": consumidor.executar, "outbox": rodar_outbox})
    yield
    await parar(tarefas)
    if kafka["produtor"] is not None:
        await kafka["produtor"].stop()
    await db.fechar()


app = FastAPI(
    title="Transportadoras",
    version="0.1.0",
    description="Transportadoras homologadas, cotações, motoristas, veículos e viagens. Grupo 5.",
    lifespan=ciclo_de_vida,
)
registrar_tratadores(app)
instalar_middleware(app, SERVICO)
app.include_router(rotas_de_saude(SERVICO, {"banco": db.verificar, "kafka": kafka_pronto}))
app.include_router(criar_rotas(db))
