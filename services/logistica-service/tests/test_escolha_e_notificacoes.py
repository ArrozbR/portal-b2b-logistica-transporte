from datetime import datetime, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from logistica.api import AjusteDoRelogio, NovaOcorrencia, PedidoDeEscolha
from logistica.notificacoes import (texto_cotacoes_disponiveis, texto_frete_escolhido, texto_frete_indisponivel,
                                    texto_ocorrencia, texto_sem_cotacao)

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


@pytest.mark.parametrize("descricao, aceita", [
    ("Carga molhada", True), ("  Carga molhada  ", True), ("a", True), ("  abc  ", True), ("x" * 500, True),
    ("     ", False), ("", False), ("x" * 501, False), ("  " + "x" * 501 + "  ", False),
])
def test_descricao_da_ocorrencia_conta_sem_os_espacos_das_pontas(descricao, aceita):
    # "     " passava no mínimo e era gravada como texto vazio. Vale de 1 a 500, como no UX (UX-RAS-08).
    if aceita:
        assert NovaOcorrencia(descricao=descricao).descricao == descricao.strip()
    else:
        with pytest.raises(ValidationError):
            NovaOcorrencia(descricao=descricao)


def test_tipo_da_ocorrencia_e_opcional_e_vale_outro():
    assert NovaOcorrencia(descricao="Carga molhada").tipo == "OUTRO"
    assert NovaOcorrencia(descricao="Carga molhada", tipo="AVARIA").tipo == "AVARIA"
    with pytest.raises(ValidationError):
        NovaOcorrencia(descricao="Carga molhada", tipo="Avaria na carga")  # o nome não vale, só o código


def test_texto_da_ocorrencia_traz_o_tipo():
    titulo, mensagem = texto_ocorrencia("ped-1", "comprador", "Lona rasgada", "AVARIA")
    assert titulo == "Ocorrência na entrega"
    assert mensagem.startswith("O comprador reportou uma ocorrência (avaria na carga) na entrega do pedido ped-1")
    assert "(" not in texto_ocorrencia("ped-1", "fornecedor", "Outra coisa")[1]  # OUTRO não aparece


def test_textos_das_notificacoes():
    titulo, mensagem = texto_cotacoes_disponiveis("ped-1", PRAZO)
    assert titulo == "Cotações de frete disponíveis"
    assert "ped-1" in mensagem and "10/11/2026 09:00" in mensagem

    # Frete indisponível não cancela o pedido (D27): abre uma nova cotação.
    assert "nova cotação" in texto_sem_cotacao("ped-1", PRAZO)[1]
    assert "nova cotação" in texto_frete_indisponivel("ped-1")[1]
    assert "cancelado" not in texto_frete_indisponivel("ped-1")[1]

    _, automatico = texto_frete_escolhido("ped-1", "Econômica Transportes", Decimal("6156.86"), 8, automatico=True)
    assert "regra automática" in automatico and "R$ 6.156,86" in automatico and "8 dias úteis" in automatico
    _, manual = texto_frete_escolhido("ped-1", "Expressa", Decimal("9026.18"), 4, automatico=False)
    assert "pelo comprador" in manual


def test_chave_de_idempotencia_tem_tamanho_fixo_e_inclui_a_solicitacao():
    from logistica.api import chave_de_idempotencia

    usuario = "019a0000-0000-7000-8000-000000000001"          # id do Identity-Service (UUID)
    longa = chave_de_idempotencia(usuario, "sol-1", "k" * 100)
    assert len(longa) == 64                                    # cabe em VARCHAR(128); antes passava e dava 500
    assert chave_de_idempotencia(usuario, "sol-1", "k") != chave_de_idempotencia(usuario, "sol-2", "k")
    assert chave_de_idempotencia(usuario, "sol-1", "k") == chave_de_idempotencia(usuario, "sol-1", "k")
