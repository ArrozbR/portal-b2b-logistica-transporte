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
