"""Pedido de leilão (D26): o pedido nasce sem comprador nem destino e o fechamento completa.

Segundo o professor (12/11/2026), o pedido é criado na abertura do leilão, e o
comprador só é definido quando ele fecha. A solicitação de frete só pode abrir
depois do fechamento, que chega num pedido_atualizado com comprador e destino.
O pedido_criado e o pedido_atualizado vêm de tópicos diferentes: o fechamento
pode chegar antes do pedido.
"""

import time
import uuid

from apoio import consultar, esperar, publicar, publicar_pedido

# Nome provisório: o grupo de Pedidos ainda não definiu o status do fechamento (Q-13).
FECHAMENTO = {"novoStatus": "LEILAO_FECHADO", "statusAnterior": "CRIADO", "compradorId": "emp-comprador-1",
              "destino": {"cidade": "Santos", "uf": "SP"}, "valorTotal": 195000.0}


def solicitacao(pedido_id: str) -> dict | None:
    linhas = consultar("SELECT id, comprador_id, destino_cidade, valor_carga, status FROM logistica.solicitacao_frete "
                       "WHERE pedido_id = %s", (pedido_id,))
    return linhas[0] if linhas else None


def aguardando(pedido_id: str) -> bool:
    return bool(consultar("SELECT 1 FROM logistica.pedido_aguardando WHERE pedido_id = %s", (pedido_id,)))


def evento_de_abertura(solicitacao_id: str) -> dict:
    return consultar("SELECT envelope FROM logistica.outbox WHERE topico = 'solicitacao_frete_criada' AND chave = %s",
                     (solicitacao_id,))[0]["envelope"]


def test_leilao_so_abre_o_frete_no_fechamento():
    pedido = publicar_pedido(compradorId=None, destino=None)
    pedido_id = pedido["aggregateId"]

    # Sem comprador e destino, nada de frete: o pedido fica esperando.
    esperar(lambda: aguardando(pedido_id), mensagem="pedido de leilão não foi guardado")
    time.sleep(2)
    assert solicitacao(pedido_id) is None

    publicar("pedido_atualizado", {"pedidoId": pedido_id, **FECHAMENTO}, pedido_id)
    aberta = esperar(lambda: solicitacao(pedido_id), mensagem="solicitação não abriu no fechamento")
    assert aberta["comprador_id"] == "emp-comprador-1"
    assert aberta["destino_cidade"] == "Santos"
    assert float(aberta["valor_carga"]) == 195000.0     # o lance vencedor
    assert not aguardando(pedido_id)
    # O correlationId continua o do pedido_criado, do começo ao fim.
    envelope = evento_de_abertura(aberta["id"])
    assert envelope["correlationId"] == pedido["correlationId"]
    assert envelope["payload"]["compradorId"] == "emp-comprador-1"


def test_fechamento_que_chega_antes_do_pedido():
    pedido_id = f"ped-it-{uuid.uuid4().hex[:8]}"
    publicar("pedido_atualizado", {"pedidoId": pedido_id, **FECHAMENTO}, pedido_id)
    esperar(lambda: aguardando(pedido_id), mensagem="fechamento não foi guardado")
    assert solicitacao(pedido_id) is None

    # O pedido_criado chega depois, com o comprador nulo: o nulo não apaga o comprador do fechamento.
    pedido = publicar_pedido(pedido_id, compradorId=None, destino=None)
    aberta = esperar(lambda: solicitacao(pedido_id), mensagem="solicitação não abriu")
    assert aberta["comprador_id"] == "emp-comprador-1" and float(aberta["valor_carga"]) == 195000.0
    assert evento_de_abertura(aberta["id"])["correlationId"] == pedido["correlationId"]


def test_leilao_cancelado_antes_de_fechar_nao_abre_frete():
    pedido_id = publicar_pedido(compradorId=None, destino=None)["aggregateId"]
    esperar(lambda: aguardando(pedido_id), mensagem="pedido de leilão não foi guardado")
    publicar("pedido_atualizado", {"pedidoId": pedido_id, "novoStatus": "CANCELADO"}, pedido_id)
    esperar(lambda: not aguardando(pedido_id), mensagem="cancelamento não tirou o pedido da espera")

    publicar("pedido_atualizado", {"pedidoId": pedido_id, **FECHAMENTO}, pedido_id)
    time.sleep(3)
    assert solicitacao(pedido_id) is None
    assert not aguardando(pedido_id)
