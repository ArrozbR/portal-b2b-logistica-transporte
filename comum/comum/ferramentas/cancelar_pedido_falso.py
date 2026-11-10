"""Publica um pedido_atualizado com status CANCELADO, como o grupo de Pedidos faria.

    python -m comum.ferramentas.cancelar_pedido_falso --pedido-id ped-123
"""

import argparse
import asyncio
import json

from aiokafka import AIOKafkaProducer

from comum.eventos import montar_envelope
from comum.kafka import servidores


async def publicar(envelope: dict) -> None:
    produtor = AIOKafkaProducer(bootstrap_servers=servidores(), acks="all", enable_idempotence=True)
    await produtor.start()
    try:
        await produtor.send_and_wait("pedido_atualizado", json.dumps(envelope).encode("utf-8"),
                                     key=envelope["aggregateId"].encode("utf-8"))
    finally:
        await produtor.stop()


def main() -> None:
    parser = argparse.ArgumentParser(description="Cancela um pedido (pedido_atualizado CANCELADO).")
    parser.add_argument("--pedido-id", required=True)
    args = parser.parse_args()

    envelope = montar_envelope("pedido_atualizado", "pedidos-falso", args.pedido_id, {
        "pedidoId": args.pedido_id, "statusAnterior": None, "novoStatus": "CANCELADO"})
    asyncio.run(publicar(envelope))
    print(json.dumps({"publicado": "pedido_atualizado", "pedidoId": args.pedido_id, "novoStatus": "CANCELADO",
                      "eventId": envelope["eventId"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
