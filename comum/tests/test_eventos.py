import argparse

import pytest

from comum.eventos import EventoInvalido, erros_do_payload, montar_envelope, validar_envelope, validar_payload


def pedido_valido(**mudancas) -> dict:
    pedido = {
        "pedidoId": "ped-1", "compradorId": "emp-12", "fornecedorId": "emp-34", "produtoId": "prod-1",
        "produtoNome": "Soja em grão", "quantidade": 24000, "unidade": "KG", "pesoKg": 24000,
        "tipoTransporte": "GRANEL", "valorTotal": 192000.0,
        "origem": {"cidade": "Sorriso", "uf": "MT"}, "destino": {"cidade": "Santos", "uf": "SP"},
    }
    pedido.update(mudancas)
    return pedido


def test_envelope_tem_os_campos_do_kit():
    envelope = montar_envelope("pedido_criado", "pedidos-service", "ped-1", {"a": 1}, "corr-1")
    assert set(envelope) == {"eventId", "eventType", "eventVersion", "timestamp", "source",
                             "correlationId", "aggregateId", "payload"}
    assert envelope["aggregateId"] == "ped-1"
    assert envelope["correlationId"] == "corr-1"
    assert validar_envelope(envelope) is envelope


def test_envelope_incompleto_e_invalido():
    with pytest.raises(EventoInvalido, match="eventId"):
        validar_envelope({"eventType": "x", "timestamp": "t", "source": "s", "aggregateId": "a", "payload": {}})
    with pytest.raises(EventoInvalido):
        validar_envelope(["não", "é", "objeto"])


def test_pedido_valido_passa_no_contrato():
    assert erros_do_payload("pedido_criado", pedido_valido()) == []


def test_campos_extras_sao_aceitos():
    # compatibilidade BACKWARD: o grupo de Pedidos pode mandar campos que não usamos
    assert erros_do_payload("pedido_criado", pedido_valido(campoNovo="x")) == []


@pytest.mark.parametrize("mudanca", [
    {"destino": None},
    {"tipoTransporte": "LIQUIDO"},
    {"pesoKg": 0},
    {"origem": {"cidade": "Sorriso", "uf": "mt"}},
])
def test_pedido_fora_do_contrato(mudanca):
    with pytest.raises(EventoInvalido, match="fora do contrato"):
        validar_payload("pedido_criado", pedido_valido(**mudanca))


def test_script_de_pedido_falso_gera_pedido_dentro_do_contrato():
    # D23: o script não pode aceitar um pedido que o serviço recusaria
    from comum.ferramentas.publicar_pedido_falso import _local, montar_payload

    args = argparse.Namespace(
        pedido_id=None, origem=_local("Rio Verde/GO"), destino=_local("Paranaguá/PR"), tipo="GRANEL",
        peso=28000.0, produto="Milho", produto_id="prod-milho", valor=50000.0,
        comprador="emp-1", fornecedor="emp-2")
    assert erros_do_payload("pedido_criado", montar_payload(args)) == []
