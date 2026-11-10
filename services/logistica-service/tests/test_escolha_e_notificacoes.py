from datetime import datetime, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from logistica.api import AjusteDoRelogio, PedidoDeEscolha
from logistica.notificacoes import (texto_cotacoes_disponiveis, texto_frete_escolhido, texto_frete_indisponivel,
                                    texto_sem_cotacao)

PRAZO = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)  # 09:00 em Brasília


def test_escolha_por_cotacao_ou_automatica():
    assert PedidoDeEscolha(cotacaoId="cot-1").modo is None
    assert PedidoDeEscolha(modo="AUTOMATICO").cotacaoId is None


@pytest.mark.parametrize("corpo", [{}, {"cotacaoId": "cot-1", "modo": "AUTOMATICO"}, {"modo": "MANUAL"}])
def test_escolha_precisa_de_exatamente_uma_opcao(corpo):
    with pytest.raises(ValidationError):
        PedidoDeEscolha(**corpo)


def test_fator_do_relogio_precisa_ser_positivo():
    assert AjusteDoRelogio(fator=360).avancarHoras == 0
    with pytest.raises(ValidationError):
        AjusteDoRelogio(fator=0)


@pytest.mark.parametrize("corpo, aceito", [
    ('{"fator": 0.07}', True), ('{"fator": 100000}', True),
    ('{"fator": 0.001}', False), ('{"fator": 1.234}', False), ('{"fator": 100000.01}', False),
])
def test_fator_do_relogio_tem_no_maximo_duas_casas(corpo, aceito):
    # O banco guarda o fator como NUMERIC(10,2): 0.001 virava 0.00 (500) e 1.234 era lido como 1.23.
    if aceito:
        assert AjusteDoRelogio.model_validate_json(corpo).fator == Decimal(corpo.split(": ")[1].rstrip("}"))
    else:
        with pytest.raises(ValidationError):
            AjusteDoRelogio.model_validate_json(corpo)


def test_textos_das_notificacoes():
    titulo, mensagem = texto_cotacoes_disponiveis("ped-1", PRAZO)
    assert titulo == "Cotações de frete disponíveis"
    assert "ped-1" in mensagem and "10/11/2026 09:00" in mensagem

    assert "será cancelado" in texto_sem_cotacao("ped-1", PRAZO)[1]
    assert "será cancelado" in texto_frete_indisponivel("ped-1")[1]

    _, automatico = texto_frete_escolhido("ped-1", "Econômica Transportes", Decimal("6156.86"), 8, automatico=True)
    assert "regra automática" in automatico and "R$ 6.156,86" in automatico and "8 dias úteis" in automatico
    _, manual = texto_frete_escolhido("ped-1", "Expressa", Decimal("9026.18"), 4, automatico=False)
    assert "pelo comprador" in manual
