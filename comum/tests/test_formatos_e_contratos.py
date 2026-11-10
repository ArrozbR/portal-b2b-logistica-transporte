from datetime import datetime, timezone

import pytest

from comum.eventos import EventoInvalido, erros_do_payload, validar_payload
from comum.formatos import data_hora, moeda
from comum.relogio import EstadoRelogio


def test_moeda_no_formato_brasileiro():
    assert moeda(6156.86) == "R$ 6.156,86"
    assert moeda(1500) == "R$ 1.500,00"
    assert moeda(0.5) == "R$ 0,50"


def test_data_hora_no_horario_de_brasilia():
    assert data_hora(datetime(2026, 11, 10, 12, 30, tzinfo=timezone.utc)) == "10/11/2026 09:30"


def test_estado_do_relogio_vai_e_volta_pelo_evento():
    estado = EstadoRelogio(datetime(2026, 11, 9, 21, 0, tzinfo=timezone.utc),
                           datetime(2026, 11, 12, 8, 0, tzinfo=timezone.utc), 360.0, 7)
    evento = estado.para_evento()
    assert erros_do_payload("relogio_ajustado", evento) == []
    assert EstadoRelogio.do_evento(evento) == estado


@pytest.mark.parametrize("payload", [
    {"pedidoId": "p1", "novoStatus": "CANCELADO"},           # formato do boilerplate do kit
    {"pedidoId": "p1", "status": "CANCELADO"},               # formato alternativo
    {"pedidoId": "p1", "novoStatus": "ENTREGUE", "statusAnterior": "FRETE_SELECIONADO", "outro": 1},
])
def test_pedido_atualizado_aceito(payload):
    assert validar_payload("pedido_atualizado", payload) is payload


def test_pedido_atualizado_sem_status_e_recusado():
    with pytest.raises(EventoInvalido):
        validar_payload("pedido_atualizado", {"pedidoId": "p1"})
