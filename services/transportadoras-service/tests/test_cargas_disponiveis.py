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
