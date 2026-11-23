"""Retentativas e DLT do consumidor, com um banco de mentira (sem Postgres nem Kafka).

O banco falso só anota o que o consumidor grava: as marcações em
processed_events e os eventos da outbox (onde a DLT é gravada).
"""

import asyncio
import json
from contextlib import asynccontextmanager

from comum.consumidor import ConsumidorIdempotente
from comum.eventos import EventoInvalido, montar_envelope


class Resultado:
    rowcount = 1


class ConexaoFalsa:
    def __init__(self, banco):
        self.banco = banco

    async def execute(self, comando, parametros=()):
        if len(parametros) == 4:  # INSERT na outbox: (event_id, topico, chave, envelope)
            self.banco.outbox.append({"topico": parametros[1], "chave": parametros[2], "envelope": parametros[3].obj})
        return Resultado()


class BancoFalso:
    def __init__(self):
        self.outbox = []

    @asynccontextmanager
    async def transacao(self):
        yield ConexaoFalsa(self)


def consumidor(tratador):
    banco = BancoFalso()
    return banco, ConsumidorIdempotente(db=banco, schema="logistica", servico="logistica-service",
                                        grupo="logistica-service", topico_dlt="logistica.dlt",
                                        tratadores={"pedido_criado": tratador}, esperas=(0, 0, 0))


def evento() -> dict:
    return montar_envelope("pedido_criado", "teste", "ped-1", {"pedidoId": "ped-1"}, "corr-1")


def test_falha_temporaria_tenta_3_vezes_e_vai_para_a_dlt_no_formato_do_kit():
    chamadas = []

    async def sempre_falha(conn, envelope):
        chamadas.append(1)
        raise ConnectionError("banco fora do ar")

    banco, c = consumidor(sempre_falha)
    original = evento()
    assert asyncio.run(c.processar("pedido_criado", json.dumps(original).encode())) == "dlt"

    assert len(chamadas) == 4  # a primeira tentativa e mais 3
    [dlt] = banco.outbox
    assert dlt["topico"] == "logistica.dlt" and dlt["chave"] == "ped-1"
    envelope = dlt["envelope"]
    assert envelope["eventType"] == "logistica.dlt" and envelope["correlationId"] == "corr-1"
    payload = envelope["payload"]
    assert set(payload) == {"originalEvent", "error", "stackTrace", "failedAtAttempt", "originalTopic"}
    assert payload["originalEvent"] == original
    assert payload["failedAtAttempt"] == 4
    assert "banco fora do ar" in payload["error"] and "ConnectionError" in payload["stackTrace"]
    assert payload["originalTopic"] == "pedido_criado"


def test_falha_que_tentar_de_novo_nao_resolve_vai_direto_para_a_dlt():
    chamadas = []

    async def fora_do_contrato(conn, envelope):
        chamadas.append(1)
        raise EventoInvalido("Cidade desconhecida: Atlântida/SP")

    banco, c = consumidor(fora_do_contrato)
    assert asyncio.run(c.processar("pedido_criado", json.dumps(evento()).encode())) == "dlt"
    assert len(chamadas) == 1
    payload = banco.outbox[0]["envelope"]["payload"]
    assert payload["failedAtAttempt"] == 1 and "Atlântida" in payload["error"]


def test_mensagem_que_nem_e_json_vai_para_a_dlt_com_o_texto_recebido():
    async def nunca_chamado(conn, envelope):
        raise AssertionError("não deveria processar")

    banco, c = consumidor(nunca_chamado)
    assert asyncio.run(c.processar("pedido_criado", b"isto nao e json")) == "dlt"
    [dlt] = banco.outbox
    assert dlt["chave"] == "desconhecido"
    assert dlt["envelope"]["payload"]["originalEvent"] == "isto nao e json"


def test_event_id_grande_demais_vai_para_a_dlt_sem_travar():
    """eventId maior que a coluna (64) travava o consumidor: a DLT tentava gravá-lo para sempre."""
    async def nunca_chamado(conn, envelope):
        raise AssertionError("não deveria processar")

    banco, c = consumidor(nunca_chamado)
    for evento_id in ("e" * 65, None, "", 123):
        original = evento() | {"eventId": evento_id}
        assert asyncio.run(c.processar("pedido_criado", json.dumps(original).encode())) == "dlt"
    assert len(banco.outbox) == 4
    assert all(d["chave"] == "desconhecido" and "eventId" in d["envelope"]["payload"]["error"] for d in banco.outbox)


def test_chave_da_dlt_cabe_na_coluna():
    """aggregateId de até 128 (limite do grupo de Pedidos) numa coluna de 100: a DLT travava."""
    async def fora_do_contrato(conn, envelope):
        raise EventoInvalido("payload inválido")

    banco, c = consumidor(fora_do_contrato)
    original = evento() | {"aggregateId": "a" * 128}
    assert asyncio.run(c.processar("pedido_criado", json.dumps(original).encode())) == "dlt"
    assert banco.outbox[0]["chave"] == "a" * 100
