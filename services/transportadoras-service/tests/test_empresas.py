"""empresa_cadastrada (Identity-Service) → transportadora real (D28)."""

import pytest

from comum.eventos import EventoInvalido
from transportadoras.empresas import transportadora_da_empresa

# Payload como o EventOutbox.cs do Identity-Service publica: camelCase com cópia em snake_case.
AGROLOG = {
    "tenantId": "01900000-0000-7000-8000-000000000030", "groupId": "01900000-0000-7000-8000-000000000001",
    "cnpj": "77888999000103", "legalName": "AgroLog Transportes e Cargas Ltda", "branchType": "HEADQUARTERS",
    "geoLat": -16.68, "geoLng": -49.25, "status": "ACTIVE", "scopes": ["CARRIER"],
    "createdAt": "2026-11-20T10:00:00.0000000+00:00",
    "event_id": "0193...", "tenant_id": "01900000-0000-7000-8000-000000000030",
    "legal_name": "AgroLog Transportes e Cargas Ltda",
}


def test_empresa_com_escopo_carrier_vira_transportadora_real():
    t = transportadora_da_empresa(AGROLOG)
    assert t["id"] == t["empresa_id"] == "01900000-0000-7000-8000-000000000030"
    assert t["nome"] == "AgroLog Transportes e Cargas Ltda"
    assert t["tipos_carga"] == ["GRANEL", "REFRIGERADO", "CARGA_SECA", "PERIGOSO"]


def test_aceita_so_os_campos_em_snake_case():
    so_snake = {"tenant_id": "t-1", "legal_name": "Transportes Um", "scopes": ["BUYER", "CARRIER"]}
    assert transportadora_da_empresa(so_snake)["nome"] == "Transportes Um"


@pytest.mark.parametrize("mudanca", [{"scopes": ["BUYER", "SUPPLIER"]}, {"status": "SUSPENDED"}])
def test_empresa_que_nao_transporta_ou_suspensa_e_ignorada(mudanca):
    assert transportadora_da_empresa(AGROLOG | mudanca) is None


@pytest.mark.parametrize("payload", [
    {"tenantId": "t-1", "legalName": "X"},                       # sem scopes
    {"scopes": ["CARRIER"], "legalName": "X"},                   # sem tenantId
    {"scopes": ["CARRIER"], "tenantId": "t-1"},                  # sem legalName
    {"scopes": ["CARRIER"], "tenantId": "x" * 65, "legalName": "X"},
])
def test_empresa_incompleta_vai_para_a_dlt(payload):
    with pytest.raises(EventoInvalido):
        transportadora_da_empresa(payload)
