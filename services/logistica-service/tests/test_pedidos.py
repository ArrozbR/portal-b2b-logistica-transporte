"""Pedido de leilão: o pedido chega sem comprador e o fechamento completa (D26)."""

from logistica.pedidos import dados_do_fechamento, faltando_para_o_frete, mesclar

PEDIDO_DE_LEILAO = {
    "pedidoId": "ped-1", "compradorId": None, "fornecedorId": "emp-34", "produtoId": "prod-1",
    "produtoNome": "Soja em grão", "quantidade": 24000, "unidade": "KG", "pesoKg": 24000,
    "tipoTransporte": "GRANEL", "valorTotal": 192000.0, "origem": {"cidade": "Sorriso", "uf": "MT"},
}
FECHAMENTO = {"pedidoId": "ped-1", "statusAnterior": "CRIADO", "novoStatus": "LEILAO_FECHADO",
              "compradorId": "emp-12", "destino": {"cidade": "Santos", "uf": "SP"}, "valorTotal": 195000.0}


def test_sem_comprador_ou_destino_falta_para_o_frete():
    assert faltando_para_o_frete(PEDIDO_DE_LEILAO) == ["compradorId", "destino"]
    assert faltando_para_o_frete({**PEDIDO_DE_LEILAO, "compradorId": "emp-12"}) == ["destino"]
    assert faltando_para_o_frete({**PEDIDO_DE_LEILAO, "compradorId": "", "destino": {}}) == ["compradorId", "destino"]


def test_fechamento_so_leva_os_campos_do_fechamento():
    assert dados_do_fechamento(FECHAMENTO) == {
        "compradorId": "emp-12", "destino": {"cidade": "Santos", "uf": "SP"}, "valorTotal": 195000.0}
    assert dados_do_fechamento({"pedidoId": "ped-1", "novoStatus": "EM_SEPARACAO", "compradorId": None}) == {}


def test_fechamento_completa_o_pedido_e_vence_no_valor():
    dados = mesclar(PEDIDO_DE_LEILAO, dados_do_fechamento(FECHAMENTO))
    assert faltando_para_o_frete(dados) == []
    assert dados["compradorId"] == "emp-12"
    assert dados["valorTotal"] == 195000.0      # o lance vencedor
    assert dados["produtoNome"] == "Soja em grão"


def test_nulo_nunca_apaga_um_valor():
    # O pedido_criado (comprador nulo) chegou DEPOIS do fechamento: o comprador continua.
    assert mesclar({"compradorId": "emp-12"}, {"compradorId": None}) == {"compradorId": "emp-12"}


def test_sequencia_real_do_grupo_de_pedidos():
    """ESP-PED-001 v2.1: o comprador vem no VENDA_CONCLUIDA (sem destino) e o destino no AGUARDANDO_FRETE."""
    venda = {"pedidoId": "ped-1", "status": "VENDA_CONCLUIDA", "statusAnterior": "CRIADO",
             "compradorId": "emp-12", "valorTotal": 650.0, "destino": None}
    aguardando_frete = {"pedidoId": "ped-1", "status": "AGUARDANDO_FRETE", "statusAnterior": "VENDA_CONCLUIDA",
                        "compradorId": "emp-12", "destino": {"cidade": "Anápolis", "uf": "GO"}, "pesoKg": 5000}
    depois_da_venda = mesclar(PEDIDO_DE_LEILAO, dados_do_fechamento(venda))
    assert faltando_para_o_frete(depois_da_venda) == ["destino"]   # ainda não abre
    completo = mesclar(depois_da_venda, dados_do_fechamento(aguardando_frete))
    assert faltando_para_o_frete(completo) == []
    assert completo["destino"] == {"cidade": "Anápolis", "uf": "GO"} and completo["valorTotal"] == 650.0


def test_nova_rodada_repete_a_carga_da_solicitacao():
    """Frete indisponível (D27): a próxima rodada abre com a mesma carga da solicitação anterior."""
    from datetime import date
    from decimal import Decimal

    from comum.geo import buscar_cidade
    from logistica.servico import pedido_da_solicitacao

    linha = {"pedido_id": "ped-1", "produto_id": "prod-1", "produto_nome": "Soja em grão",
             "valor_carga": Decimal("192000.00"), "comprador_id": "emp-12", "fornecedor_id": "emp-34",
             "tipo_carga": "GRANEL", "peso_kg": Decimal("24000.000"), "origem_cidade": "Sorriso", "origem_uf": "MT",
             "destino_cidade": "Anápolis", "destino_uf": "GO", "data_entrega_desejada": date(2026, 12, 1),
             "rodada": 1, "status": "INDISPONIVEL"}
    pedido = pedido_da_solicitacao(linha)
    assert pedido["pedidoId"] == "ped-1" and pedido["compradorId"] == "emp-12"
    assert pedido["tipoTransporte"] == "GRANEL" and pedido["pesoKg"] == Decimal("24000.000")
    assert pedido["dataEntregaDesejada"] == date(2026, 12, 1)
    assert buscar_cidade(pedido["destino"]["cidade"], pedido["destino"]["uf"]) is not None   # continua na lista
