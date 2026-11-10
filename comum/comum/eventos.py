"""Envelope canônico dos eventos e validação dos payloads.

Todo evento publicado pelo grupo usa o envelope do kit:

    {eventId, eventType, eventVersion, timestamp, source,
     correlationId, aggregateId, payload}

O aggregateId é também a chave da mensagem no Kafka, para que todos os
eventos da mesma entidade caiam na mesma partição e cheguem em ordem.

Os payloads são validados contra os JSON Schemas da pasta `contratos/`.
O script de pedido falso (D23) usa os mesmos schemas, para que um teste
nunca passe com um formato que o serviço real não aceitaria.
"""

import json
import uuid
from functools import lru_cache
from importlib import resources

from jsonschema import Draft202012Validator

from .logs import agora_iso, correlation_id

VERSAO_EVENTO = "1.0"
CAMPOS_ENVELOPE = ("eventId", "eventType", "timestamp", "source", "aggregateId", "payload")


class EventoInvalido(Exception):
    """O evento não pode ser processado nunca, por mais que se tente de novo.

    Vai direto para a DLT, sem retentativas (payload fora do contrato,
    cidade desconhecida, referência que não existe).
    """


def montar_envelope(tipo: str, origem: str, chave: str, payload: dict,
                    id_correlacao: str | None = None) -> dict:
    return {
        "eventId": str(uuid.uuid4()),
        "eventType": tipo,
        "eventVersion": VERSAO_EVENTO,
        "timestamp": agora_iso(),
        "source": origem,
        "correlationId": id_correlacao or correlation_id.get() or str(uuid.uuid4()),
        "aggregateId": chave,
        "payload": payload,
    }


def validar_envelope(envelope: object) -> dict:
    if not isinstance(envelope, dict):
        raise EventoInvalido("O evento não é um objeto JSON")
    faltando = [campo for campo in CAMPOS_ENVELOPE if campo not in envelope]
    if faltando:
        raise EventoInvalido(f"Envelope sem os campos: {', '.join(faltando)}")
    if not isinstance(envelope["payload"], dict):
        raise EventoInvalido("O campo payload precisa ser um objeto")
    return envelope


@lru_cache
def _validador(nome: str) -> Draft202012Validator:
    texto = resources.files("comum.contratos").joinpath(f"{nome}.schema.json").read_text(encoding="utf-8")
    return Draft202012Validator(json.loads(texto))


def erros_do_payload(nome: str, payload: dict) -> list[str]:
    """Lista os erros do payload em relação ao schema (vazia se estiver válido)."""
    erros = []
    for erro in _validador(nome).iter_errors(payload):
        caminho = ".".join(str(p) for p in erro.absolute_path) or "(raiz)"
        erros.append(f"{caminho}: {erro.message}")
    return erros


def validar_payload(nome: str, payload: dict) -> dict:
    erros = erros_do_payload(nome, payload)
    if erros:
        raise EventoInvalido(f"Payload de {nome} fora do contrato: " + "; ".join(erros))
    return payload
