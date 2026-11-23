"""Frete indisponível não cancela o pedido: abre uma nova rodada de cotação (D27).

O grupo de Pedidos não cancela o pedido quando o frete fica indisponível, porque a
venda já foi concluída e o estoque já teve baixa (ESP-PED-001, RN-22 e D-05). Ele
espera uma nova solicitacao_frete_criada. Aqui, uma carga refrigerada de 30 t não
recebe cotação (a única transportadora refrigerada não tem veículo para 30 t): o
prazo de 12 h vence, sai o frete_indisponivel e a rodada 2 abre na mesma hora.
"""

import time

from apoio import consultar, esperar, publicar_pedido


def rodadas(pedido_id: str) -> list[dict]:
    return consultar("SELECT id, rodada, status FROM logistica.solicitacao_frete WHERE pedido_id = %s ORDER BY rodada",
                     (pedido_id,))


def na_outbox(topico: str, pedido_id: str) -> list[dict]:
    return [l["envelope"] for l in consultar(
        "SELECT envelope FROM logistica.outbox WHERE topico = %s AND envelope->'payload'->>'pedidoId' = %s "
        "ORDER BY criado_em", (topico, pedido_id))]


def test_frete_indisponivel_abre_nova_rodada_sem_cancelar(api, entrar, relogio):
    pedido = publicar_pedido(tipoTransporte="REFRIGERADO", pesoKg=30000, quantidade=30000,
                             produtoNome="Carne congelada", valorTotal=450000.0)
    pedido_id = pedido["aggregateId"]
    esperar(lambda: [r for r in rodadas(pedido_id) if r["status"] == "SEM_COTACAO"],
            segundos=20, mensagem="a rodada 1 não terminou sem cotação")

    # O prazo de 12 h vence: frete indisponível na rodada 1 e rodada 2 aberta na mesma transação.
    resposta = api.post("/api/v1/logistica/admin/relogio", json={"fator": 1, "avancarHoras": 12},
                        headers=entrar("usr-admin"))
    resposta.raise_for_status()
    esperar(lambda: len(rodadas(pedido_id)) == 2, mensagem="a rodada 2 não abriu")
    primeira, segunda = rodadas(pedido_id)
    assert (primeira["rodada"], primeira["status"]) == (1, "INDISPONIVEL")
    assert segunda["rodada"] == 2 and segunda["status"] in ("ABERTA", "SEM_COTACAO")

    indisponivel = na_outbox("frete_indisponivel", pedido_id)
    assert len(indisponivel) == 1 and indisponivel[0]["payload"]["solicitacaoFreteId"] == primeira["id"]
    aberturas = na_outbox("solicitacao_frete_criada", pedido_id)
    assert [e["payload"]["rodada"] for e in aberturas] == [1, 2]
    assert aberturas[1]["aggregateId"] == segunda["id"]
    # O pedido continua o mesmo do começo ao fim: mesmo correlationId.
    assert {e["correlationId"] for e in indisponivel + aberturas} == {pedido["correlationId"]}

    # O pedidos-falso (papel do grupo de Pedidos) não cancela mais: a rodada 2 continua aberta.
    time.sleep(4)
    assert rodadas(pedido_id)[1]["status"] in ("ABERTA", "SEM_COTACAO")
