"""Faz o papel do grupo de Pedidos na outra ponta do fluxo (decisão D23).

Enquanto o pedidos-service real não consome os nossos eventos, este processo
consome o que a logística publica e reage como o grupo de Pedidos deveria
reagir (ver docs/contratos/proposta-grupo-pedidos.md, seção 2):

    solicitacao_frete_criada        → pedido vai a AGUARDANDO_FRETE
    frete_selecionado               → pedido vai a FRETE_SELECIONADO
    entrega_concluida               → pedido vai a ENTREGUE
    frete_indisponivel              → pedido é CANCELADO e publica pedido_atualizado

Guarda o status dos pedidos só em memória e registra cada mudança no log.
Desligue-o quando o pedidos-service real estiver integrado.

    python -m comum.ferramentas.pedidos_falso
"""

import asyncio
import json
import logging

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

from comum.eventos import montar_envelope
from comum.kafka import servidores
from comum.logs import configurar_logs, correlacao

log = logging.getLogger("pedidos-falso")

SERVICO = "pedidos-falso"
TRANSICOES = {
    "solicitacao_frete_criada": "AGUARDANDO_FRETE",
    "frete_selecionado": "FRETE_SELECIONADO",
    "entrega_concluida": "ENTREGUE",
    "frete_indisponivel": "CANCELADO",
}


async def executar() -> None:
    consumidor = AIOKafkaConsumer(*TRANSICOES, bootstrap_servers=servidores(), group_id=SERVICO,
                                  client_id=SERVICO, auto_offset_reset="latest", enable_auto_commit=True)
    produtor = AIOKafkaProducer(bootstrap_servers=servidores(), acks="all", enable_idempotence=True)
    await consumidor.start()
    await produtor.start()
    status: dict[str, str] = {}
    log.info("Pedidos falso escutando", extra={"dados": {"topicos": list(TRANSICOES)}})
    try:
        async for mensagem in consumidor:
            envelope = json.loads(mensagem.value)
            payload = envelope.get("payload", {})
            pedido_id = payload.get("pedidoId")
            if not pedido_id:
                continue
            anterior = status.get(pedido_id)
            novo = TRANSICOES[mensagem.topic]
            status[pedido_id] = novo
            with correlacao(envelope.get("correlationId")):
                log.info("Pedido mudou de status", extra={"dados": {
                    "pedidoId": pedido_id, "evento": mensagem.topic, "statusAnterior": anterior, "novoStatus": novo,
                    "transportadoraId": payload.get("transportadoraId"), "criterio": payload.get("criterio")}})
                if novo == "CANCELADO":
                    cancelamento = montar_envelope("pedido_atualizado", SERVICO, pedido_id, {
                        "pedidoId": pedido_id, "statusAnterior": anterior, "novoStatus": "CANCELADO",
                        "motivo": payload.get("motivo"),
                    }, envelope.get("correlationId"))
                    await produtor.send_and_wait("pedido_atualizado", json.dumps(cancelamento).encode(),
                                                 key=pedido_id.encode())
                    log.info("pedido_atualizado CANCELADO publicado", extra={"dados": {"pedidoId": pedido_id}})
    finally:
        await consumidor.stop()
        await produtor.stop()


def main() -> None:
    configurar_logs(SERVICO)
    asyncio.run(executar())


if __name__ == "__main__":
    main()
