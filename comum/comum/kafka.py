"""Conexão com o Redpanda (API do Kafka).

Um único produtor por processo, criado na subida do serviço (o kit criava e
destruía um produtor a cada evento, K6). Configurado com acks=all e
idempotência, para a mensagem só contar como enviada quando as réplicas
confirmarem.
"""

import asyncio
import logging

from aiokafka import AIOKafkaProducer

from . import config

log = logging.getLogger(__name__)


def servidores() -> str:
    return config.texto("KAFKA_BOOTSTRAP_SERVERS", "localhost:19092")


async def iniciar_produtor(cliente: str) -> AIOKafkaProducer:
    """Cria o produtor, tentando de novo enquanto o Redpanda não responde."""
    espera = 1.0
    while True:
        produtor = AIOKafkaProducer(
            bootstrap_servers=servidores(),
            client_id=cliente,
            acks="all",
            enable_idempotence=True,
        )
        try:
            await produtor.start()
            log.info("Produtor Kafka conectado", extra={"dados": {"bootstrap": servidores()}})
            return produtor
        except Exception as exc:
            await produtor.stop()
            log.warning("Redpanda indisponível, tentando de novo",
                        extra={"dados": {"erro": str(exc), "esperaSegundos": espera}})
            await asyncio.sleep(espera)
            espera = min(espera * 2, 15)


async def verificar(produtor: AIOKafkaProducer) -> None:
    """Usado pelo /health/ready: pede ao broker os metadados de um tópico."""
    await produtor.partitions_for("pedido_criado")
