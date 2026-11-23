from datetime import date, datetime, timedelta, timezone

import pytest

from comum.geo import dias_uteis_entre, somar_dias_uteis
from transportadoras.api import situacao_da_carga

AGORA = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)


def carga(**mudancas):
    base = dict(minha_cotacao_id=None, transportadora_vencedora_id=None, cancelada=False, status="ABERTA",
                prazo_decisao_em=AGORA + timedelta(hours=5))
    base.update(mudancas)
    return base


@pytest.mark.parametrize("mudancas, esperado", [
    ({}, "ACEITANDO_COTACOES"),
    ({"minha_cotacao_id": "c1"}, "COTACAO_ENVIADA"),
    ({"minha_cotacao_id": "c1", "status": "ENCERRADA", "transportadora_vencedora_id": "eu"}, "VENCEU"),
    ({"minha_cotacao_id": "c1", "status": "ENCERRADA", "transportadora_vencedora_id": "outra"}, "OUTRA_VENCEU"),
    ({"status": "ENCERRADA", "transportadora_vencedora_id": "outra"}, "ENCERRADA"),
    ({"status": "ENCERRADA", "cancelada": True}, "CANCELADA"),
    # cancelado depois da escolha: não aparece como "Você venceu"
    ({"minha_cotacao_id": "c1", "status": "ENCERRADA", "transportadora_vencedora_id": "eu", "cancelada": True},
     "CANCELADA"),
    ({"prazo_decisao_em": AGORA - timedelta(minutes=1)}, "ENCERRADA"),
])
def test_situacao_da_carga_para_a_transportadora(mudancas, esperado):
    assert situacao_da_carga(carga(**mudancas), "eu", AGORA) == esperado


def test_dias_uteis_entre_e_o_inverso_de_somar():
    coleta = date(2026, 11, 13)  # sexta
    for dias in range(1, 12):
        assert dias_uteis_entre(coleta, somar_dias_uteis(coleta, dias)) == dias
    assert dias_uteis_entre(coleta, coleta) == 0
    assert dias_uteis_entre(coleta, date(2026, 11, 15)) == 0  # só fim de semana


@pytest.mark.parametrize("valor, aceito", [
    ("0.01", True), ("1234.5", True), ("10000000", True),
    ("0.004", False), ("0", False), ("1234.567", False), ("10000000.01", False),
])
def test_valor_da_cotacao_digitada_tem_no_maximo_duas_casas(valor, aceito):
    # 0.004 passava, virava 0,00 na logística, violava preco > 0 e a cotação ia para a DLT.
    from pydantic import ValidationError

    from transportadoras.api import DadosCotacao
    corpo = '{"valor": %s, "dataEntregaPrevista": "2026-12-01", "validaAte": "2026-11-30T12:00:00Z"}' % valor
    if aceito:
        assert str(DadosCotacao.model_validate_json(corpo).valor) == valor
    else:
        with pytest.raises(ValidationError):
            DadosCotacao.model_validate_json(corpo)
