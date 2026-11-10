"""Consumidor de eventos idempotente, com retentativas e DLT.

Três garantias:

1. Idempotência. O Kafka pode entregar a mesma mensagem mais de uma vez
   (e a nossa outbox também pode publicar duas vezes). Antes de processar,
   o consumidor grava o eventId na tabela `processed_events`, NA MESMA
   TRANSAÇÃO da alteração de negócio. Se o eventId já estiver lá, a
   mensagem é ignorada. Como é uma transação só, não existe o caso
   "processou mas não marcou" nem "marcou mas não processou".

2. Retentativas. Se o processamento falhar (ex.: banco fora do ar), tenta de
   novo depois de 1 s, 2 s e 4 s.

3. DLT (dead letter topic). Se continuar falhando, ou se a mensagem for
   inválida (EventoInvalido), ela vai para `<servico>.dlt` com o motivo, e o
   consumidor segue para a próxima. Uma mensagem ruim nunca trava a fila.
   O payload da DLT usa os campos da biblioteca comum do kit
   (`services/common/consumer.py`): originalEvent, error, stackTrace e
   failedAtAttempt, mais originalTopic (o tópico de onde a mensagem veio).

O offset só é confirmado (commit) depois de a mensagem ser processada ou ir
para a DLT. Se o serviço cair no meio, a mensagem é entregue de novo e a
idempotência evita o efeito duplicado.
"""

import asyncio
import json
import logging
import traceback
from typing import Awaitable, Callable

from aiokafka import AIOKafkaConsumer
from psycopg import AsyncConnection, sql

from .db import BancoDeDados
from .eventos import EventoInvalido, validar_envelope
from .kafka import servidores
from .logs import correlation_id
from .outbox import gravar_evento
from .web import EVENTOS_CONSUMIDOS

log = logging.getLogger(__name__)

Tratador = Callable[[AsyncConnection, dict], Awaitable[None]]

ESPERAS_PADRAO = (1, 2, 4)


class ConsumidorIdempotente:
    def __init__(self, db: BancoDeDados, schema: str, servico: str, grupo: str,
                 tratadores: dict[str, Tratador], topico_dlt: str,
                 esperas: tuple[float, ...] = ESPERAS_PADRAO):
        self.db = db
        self.schema = schema
        self.servico = servico
        self.grupo = grupo
        self.tratadores = tratadores
        self.topico_dlt = topico_dlt
        self.esperas = esperas

    async def executar(self) -> None:
        consumidor = AIOKafkaConsumer(
            *self.tratadores.keys(),
            bootstrap_servers=servidores(),
            group_id=self.grupo,
            client_id=self.servico,
            enable_auto_commit=False,
            auto_offset_reset="earliest",
        )
        await consumidor.start()
        log.info("Consumidor iniciado", extra={"dados": {"topicos": list(self.tratadores), "grupo": self.grupo}})
        try:
            async for mensagem in consumidor:
                await self.processar(mensagem.topic, mensagem.value)
                await consumidor.commit()
        finally:
            await consumidor.stop()

    async def processar(self, topico: str, valor: bytes) -> str:
        """Processa uma mensagem. Devolve "processado", "duplicado" ou "dlt"."""
        try:
            envelope = validar_envelope(json.loads(valor))
        except (ValueError, EventoInvalido) as exc:
            await self._enviar_dlt(topico, None, valor, str(exc), tentativa=1, pilha=traceback.format_exc())
            return "dlt"

        token = correlation_id.set(envelope.get("correlationId"))
        try:
            return await self._processar_com_retentativas(topico, envelope)
        finally:
            correlation_id.reset(token)

    async def _processar_com_retentativas(self, topico: str, envelope: dict) -> str:
        tratador = self.tratadores[topico]
        esperas = list(self.esperas)
        tentativa = 0
        while True:
            tentativa += 1
            try:
                async with self.db.transacao() as conn:
                    marcado = await conn.execute(
                        sql.SQL("INSERT INTO {}.processed_events (event_id, topico) VALUES (%s, %s) "
                                "ON CONFLICT (event_id) DO NOTHING").format(sql.Identifier(self.schema)),
                        (envelope["eventId"], topico),
                    )
                    if marcado.rowcount == 0:
                        log.info("Evento já processado, ignorado",
                                 extra={"dados": {"eventId": envelope["eventId"], "topico": topico}})
                        EVENTOS_CONSUMIDOS.labels(self.servico, topico, "duplicado").inc()
                        return "duplicado"
                    await tratador(conn, envelope)
                EVENTOS_CONSUMIDOS.labels(self.servico, topico, "processado").inc()
                return "processado"
            except EventoInvalido as exc:
                log.warning("Evento inválido, enviado para a DLT",
                            extra={"dados": {"eventId": envelope["eventId"], "topico": topico, "erro": str(exc)}})
                await self._enviar_dlt(topico, envelope, None, str(exc), tentativa=tentativa,
                                       pilha=traceback.format_exc())
                return "dlt"
            except Exception as exc:
                if not esperas:
                    log.exception("Falha permanente, evento enviado para a DLT",
                                  extra={"dados": {"eventId": envelope["eventId"], "topico": topico}})
                    await self._enviar_dlt(topico, envelope, None, repr(exc), tentativa=tentativa,
                                           pilha=traceback.format_exc())
                    return "dlt"
                espera = esperas.pop(0)
                log.warning("Falha ao processar evento, nova tentativa",
                            extra={"dados": {"eventId": envelope["eventId"], "topico": topico,
                                             "tentativa": tentativa, "esperaSegundos": espera, "erro": repr(exc)}})
                await asyncio.sleep(espera)

    async def _enviar_dlt(self, topico: str, envelope: dict | None, valor_bruto: bytes | None,
                          erro: str, tentativa: int, pilha: str) -> None:
        payload = montar_payload_dlt(topico, envelope, valor_bruto, erro, tentativa, pilha)
        chave = (envelope or {}).get("aggregateId") or "desconhecido"
        id_correlacao = (envelope or {}).get("correlationId")
        while True:  # a DLT também passa pela outbox; insiste até o banco aceitar
            try:
                async with self.db.transacao() as conn:
                    if envelope is not None:
                        # marca como processado para não mandar duas vezes para a DLT
                        await conn.execute(
                            sql.SQL("INSERT INTO {}.processed_events (event_id, topico) VALUES (%s, %s) "
                                    "ON CONFLICT (event_id) DO NOTHING").format(sql.Identifier(self.schema)),
                            (envelope["eventId"], topico),
                        )
                    await gravar_evento(conn, self.schema, self.servico, self.topico_dlt, chave, payload, id_correlacao)
                EVENTOS_CONSUMIDOS.labels(self.servico, topico, "dlt").inc()
                return
            except Exception:
                log.exception("Não foi possível gravar na DLT, tentando de novo")
                await asyncio.sleep(2)


def montar_payload_dlt(topico: str, envelope: dict | None, valor_bruto: bytes | None,
                       erro: str, tentativa: int, pilha: str) -> dict:
    """Payload da DLT no formato do kit, mais o tópico de origem.

    Se a mensagem nem era JSON, `originalEvent` leva o texto recebido.
    """
    return {
        "originalEvent": envelope if envelope is not None else (valor_bruto or b"").decode("utf-8", "replace"),
        "error": erro,
        "stackTrace": pilha,
        "failedAtAttempt": tentativa,
        "originalTopic": topico,
    }
