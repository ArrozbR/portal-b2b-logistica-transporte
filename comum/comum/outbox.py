"""Outbox transacional (decisão D13).

Problema: o serviço precisa gravar no banco E publicar no Kafka. Se gravar e
cair antes de publicar, o evento se perde. Se publicar e o commit falhar, o
evento sai sem o dado existir.

Solução: o evento é gravado numa tabela `outbox`, na MESMA transação da
alteração de negócio. Ou os dois ficam gravados, ou nenhum. Depois, uma
rotina em segundo plano (PublicadorOutbox) lê a tabela e publica no Kafka.

Consequência: um evento pode ser publicado mais de uma vez (se o serviço cair
entre publicar e marcar como publicado). Por isso todos os consumidores são
idempotentes (ver consumidor.py). Isso se chama "entrega pelo menos uma vez".
"""

import asyncio
import json
import logging

from aiokafka import AIOKafkaProducer
from psycopg import AsyncConnection, sql
from psycopg.types.json import Jsonb

from .db import BancoDeDados, buscar_todos
from .eventos import montar_envelope
from .web import EVENTOS_PUBLICADOS

log = logging.getLogger(__name__)


async def gravar_evento(conn: AsyncConnection, schema: str, servico: str, topico: str,
                        chave: str, payload: dict, id_correlacao: str | None = None) -> dict:
    """Grava o evento na outbox, dentro da transação de `conn`."""
    envelope = montar_envelope(topico, servico, chave, payload, id_correlacao)
    await conn.execute(
        sql.SQL("INSERT INTO {}.outbox (event_id, topico, chave, envelope) VALUES (%s, %s, %s, %s)")
        .format(sql.Identifier(schema)),
        (envelope["eventId"], topico, chave, Jsonb(envelope)),
    )
    return envelope


class PublicadorOutbox:
    """Lê os eventos pendentes da outbox e publica no Kafka, em ordem.

    Com duas cópias do serviço rodando, só uma publica por vez: a que
    conseguir a trava `pg_try_advisory_xact_lock`. Assim os eventos saem na
    ordem em que foram gravados.
    """

    def __init__(self, db: BancoDeDados, schema: str, servico: str, produtor: AIOKafkaProducer,
                 intervalo: float = 0.2, lote: int = 100):
        self.db = db
        self.schema = schema
        self.servico = servico
        self.produtor = produtor
        self.intervalo = intervalo
        self.lote = lote

    async def executar(self) -> None:
        while True:
            publicados = await self.publicar_pendentes()
            if publicados < self.lote:
                await asyncio.sleep(self.intervalo)

    async def publicar_pendentes(self) -> int:
        async with self.db.transacao() as conn:
            trava = await (await conn.execute(
                "SELECT pg_try_advisory_xact_lock(hashtext(%s)) AS obtida", (f"outbox:{self.schema}",)
            )).fetchone()
            if not trava["obtida"]:
                return 0  # a outra cópia está publicando agora

            pendentes = await buscar_todos(
                conn,
                sql.SQL("SELECT seq, topico, chave, envelope FROM {}.outbox "
                        "WHERE publicado_em IS NULL ORDER BY seq LIMIT %s").format(sql.Identifier(self.schema)),
                (self.lote,),
            )
            for evento in pendentes:
                await self.produtor.send_and_wait(
                    evento["topico"],
                    value=json.dumps(evento["envelope"], ensure_ascii=False).encode("utf-8"),
                    key=evento["chave"].encode("utf-8"),
                )
                EVENTOS_PUBLICADOS.labels(self.servico, evento["topico"]).inc()

            if pendentes:
                await conn.execute(
                    sql.SQL("UPDATE {}.outbox SET publicado_em = now() WHERE seq = ANY(%s)")
                    .format(sql.Identifier(self.schema)),
                    ([e["seq"] for e in pendentes],),
                )
                log.info("Eventos publicados", extra={"dados": {
                    "quantidade": len(pendentes),
                    "topicos": sorted({e["topico"] for e in pendentes}),
                }})
            return len(pendentes)
