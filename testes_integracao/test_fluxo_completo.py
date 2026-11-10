"""Fluxo completo, do pedido à entrega, conferindo cada evento no Kafka.

pedido_criado → solicitacao_frete_criada → cotacao_recebida (3) → comparação →
escolha do comprador → frete_selecionado → rastreio_atualizado (...) →
entrega_concluida, mais notificações, pontualidade e documentos.
"""

import uuid

from apoio import consultar, esperar, mensagens_do_topico, publicar_pedido


def test_do_pedido_a_entrega(api, entrar, relogio):
    comprador, fornecedor = entrar("usr-comprador-1"), entrar("usr-fornecedor-1")
    envelope = publicar_pedido()
    pedido_id = envelope["aggregateId"]

    # 1. Solicitação aberta e cotada pelas 3 transportadoras compatíveis
    solicitacao = esperar(lambda: consultar(
        "SELECT id, status FROM logistica.solicitacao_frete WHERE pedido_id = %s AND status = 'COTADA'", (pedido_id,)),
        mensagem="solicitação não ficou COTADA")[0]
    solicitacao_id = solicitacao["id"]
    criada = mensagens_do_topico("solicitacao_frete_criada", solicitacao_id)
    assert len(criada) == 1 and criada[0]["correlationId"] == envelope["correlationId"]
    esperar(lambda: len(mensagens_do_topico("cotacao_recebida", solicitacao_id)) == 3, segundos=15)

    # 2. Comparação e escolha pelo comprador (não a mais barata)
    comparacao = api.get(f"/api/v1/logistica/solicitacoes/{solicitacao_id}/comparacao", headers=comprador).json()
    assert comparacao["podeEscolher"] is True
    selos = {c["transportadora_id"]: c["selos"] for c in comparacao["cotacoes"]}
    assert "MAIS_RAPIDA" in selos["transp-expressa"] and "RECOMENDADA_PELA_REGRA" in selos["transp-economica"]
    expressa = next(c for c in comparacao["cotacoes"] if c["transportadora_id"] == "transp-expressa")
    resposta = api.post(f"/api/v1/logistica/solicitacoes/{solicitacao_id}/selecionar-frete",
                        json={"cotacaoId": expressa["id"]},
                        headers={**comprador, "Idempotency-Key": str(uuid.uuid4())})
    assert resposta.status_code == 200
    entrega_id = resposta.json()["entregaId"]
    frete = esperar(lambda: mensagens_do_topico("frete_selecionado", pedido_id), segundos=15)
    assert frete[0]["payload"]["criterio"] == "ESCOLHA_COMPRADOR"
    assert frete[0]["correlationId"] == envelope["correlationId"]  # o mesmo do começo ao fim

    # 3. Viagem até a entrega, com o relógio acelerado
    esperar(lambda: consultar("SELECT status FROM logistica.entrega WHERE id = %s",
                              (entrega_id,))[0]["status"] == "AGUARDANDO_COLETA", segundos=20)
    relogio(20000)
    esperar(lambda: consultar("SELECT status FROM logistica.entrega WHERE id = %s",
                              (entrega_id,))[0]["status"] == "ENTREGUE", segundos=240, intervalo=2)
    concluida = esperar(lambda: mensagens_do_topico("entrega_concluida", pedido_id), segundos=15)
    assert concluida[0]["payload"]["entregaId"] == entrega_id
    assert concluida[0]["correlationId"] == envelope["correlationId"]

    # 4. Efeitos: rastreio completo, notificações, pontualidade e documentos
    rastreio = api.get(f"/api/v1/logistica/entregas/{entrega_id}/rastreio", headers=comprador).json()
    assert rastreio["status"] == "ENTREGUE" and rastreio["progresso"] == 1.0 and len(rastreio["rota"]) == 60
    tipos = {n["tipo"] for n in api.get("/api/v1/logistica/notificacoes", headers=fornecedor,
                                        params={"size": 100}).json()["items"] if n["pedido_id"] == pedido_id}
    assert {"FRETE_ESCOLHIDO", "MOTORISTA_ESCALADO", "COLETA_REALIZADA", "ENTREGA_REALIZADA"} <= tipos
    assert consultar("SELECT entregas FROM logistica.desempenho_transportadora WHERE transportadora_id = %s",
                     ("transp-expressa",))[0]["entregas"] >= 1
    for tipo in ("cte", "romaneio", "nota-fiscal", "comprovante-coleta"):
        documento = api.get(f"/api/v1/logistica/entregas/{entrega_id}/documentos/{tipo}", headers=comprador)
        assert documento.status_code == 200 and documento.content.startswith(b"%PDF"), tipo
