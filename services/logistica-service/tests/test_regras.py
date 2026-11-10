from decimal import Decimal

import pytest

from logistica.regras import CotacaoCandidata, escolher_automaticamente


def cotacao(id_, transportadora, preco, prazo):
    return CotacaoCandidata(id_, transportadora, Decimal(str(preco)), prazo)


def test_menor_preco_vence():
    cotacoes = [cotacao("c1", "expressa", 9025.80, 4), cotacao("c2", "economica", 6156.60, 8),
                cotacao("c3", "graneleira", 7113.00, 5)]
    assert escolher_automaticamente(cotacoes).id == "c2"


def test_empate_de_preco_vai_para_o_menor_prazo():
    cotacoes = [cotacao("c1", "a", 5000, 6), cotacao("c2", "b", 5000, 4)]
    assert escolher_automaticamente(cotacoes).id == "c2"


def test_empate_de_preco_e_prazo_vai_para_a_mais_pontual():
    cotacoes = [cotacao("c1", "a", 5000, 4), cotacao("c2", "b", 5000, 4)]
    assert escolher_automaticamente(cotacoes, {"a": 0.70, "b": 0.95}).id == "c2"


def test_transportadora_sem_historico_conta_como_zero():
    cotacoes = [cotacao("c1", "nova", 5000, 4), cotacao("c2", "antiga", 5000, 4)]
    assert escolher_automaticamente(cotacoes, {"antiga": 0.5}).id == "c2"


def test_empate_total_e_decidido_pelo_id_da_transportadora():
    cotacoes = [cotacao("c1", "zeta", 5000, 4), cotacao("c2", "alfa", 5000, 4)]
    assert escolher_automaticamente(cotacoes).id == "c2"
    assert escolher_automaticamente(list(reversed(cotacoes))).id == "c2"  # ordem de chegada não importa


def test_sem_cotacao_nao_ha_o_que_escolher():
    with pytest.raises(ValueError):
        escolher_automaticamente([])
