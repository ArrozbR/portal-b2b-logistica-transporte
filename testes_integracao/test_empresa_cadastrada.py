"""Empresa com escopo CARRIER no Identity-Service vira transportadora real (D28).

O evento é publicado no formato do Identity-Service (EventOutbox.cs): envelope do kit,
payload em camelCase com cópia em snake_case, e os campos repetidos na raiz.
"""

import asyncio
import uuid

from apoio import _publicar, consultar, esperar


def evento_da_autenticacao(tenant_id: str, nome: str, escopos: list[str]) -> dict:
    payload = {"tenantId": tenant_id, "groupId": str(uuid.uuid4()), "cnpj": "77888999000103", "legalName": nome,
               "branchType": "HEADQUARTERS", "geoLat": -16.68, "geoLng": -49.25, "status": "ACTIVE",
               "scopes": escopos, "createdAt": "2026-11-23T12:00:00.0000000+00:00",
               "event_id": str(uuid.uuid4()), "tenant_id": tenant_id, "legal_name": nome}
    envelope = {"eventId": payload["event_id"], "eventType": "empresa_cadastrada", "eventVersion": "1.0",
                "timestamp": "2026-11-23T12:00:00.0000000+00:00", "source": "identity-service",
                "correlationId": str(uuid.uuid4()), "aggregateId": tenant_id, "payload": payload}
    return envelope | {k: v for k, v in payload.items() if k not in envelope}   # cópia na raiz


def transportadora(tenant_id: str) -> dict | None:
    linhas = consultar("SELECT t.nome, t.simulada, r.km_por_dia FROM transportadoras.transportadora t "
                       "JOIN transportadoras.regra_cotacao r ON r.transportadora_id = t.id WHERE t.empresa_id = %s",
                       (tenant_id,))
    return linhas[0] if linhas else None


def test_empresa_transportadora_do_identity_service_vira_transportadora_real(api):
    tenant_id = str(uuid.uuid4())
    asyncio.run(_publicar("empresa_cadastrada", evento_da_autenticacao(tenant_id, "Transportes IT Ltda", ["CARRIER"])))
    criada = esperar(lambda: transportadora(tenant_id), mensagem="transportadora não foi criada")
    assert criada["nome"] == "Transportes IT Ltda" and criada["simulada"] is False and criada["km_por_dia"] == 600

    # O usuário dessa empresa entra (token CARRIER com o tenant_id dela) e acha a sua transportadora.
    token = api.post("/api/v1/usuarios/demonstracao/token",
                     json={"perfil": "transportadora", "empresaId": tenant_id}).json()["accessToken"]
    minha = api.get("/api/v1/transportadoras/minha", headers={"Authorization": f"Bearer {token}"})
    assert minha.status_code == 200 and minha.json()["nome"] == "Transportes IT Ltda"


def test_empresa_sem_escopo_carrier_nao_vira_transportadora():
    tenant_id = str(uuid.uuid4())
    evento = evento_da_autenticacao(tenant_id, "Compradora IT", ["BUYER", "TENANT_ADMIN"])
    asyncio.run(_publicar("empresa_cadastrada", evento))
    esperar(lambda: consultar("SELECT 1 FROM transportadoras.processed_events WHERE event_id = %s",
                              (evento["eventId"],)), mensagem="evento não foi processado")
    assert transportadora(tenant_id) is None
