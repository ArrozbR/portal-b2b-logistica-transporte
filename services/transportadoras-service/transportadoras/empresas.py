"""Transportadora real criada a partir do `empresa_cadastrada` do grupo de Autenticação (D28).

Quando o Identity-Service cadastra uma empresa com o escopo `CARRIER`, ela vira
uma transportadora deste módulo. Assim, o usuário dessa empresa entra com o login
real e encontra a "sua" transportadora (o `tenant_id` do token é o `empresa_id`).

A transportadora nasce **real** (`simulada = FALSE`): ela cota digitando, como a
Rodovia Sul do seed, e cadastra motoristas e veículos na tela "Minha frota". O
evento não diz que cargas ela leva, então ela começa aceitando os quatro tipos; só
cota de fato o que a frota dela comporta.

Formato do evento (Identity-Service, `EventOutbox.cs`, commit `a763ed5`): envelope do
kit, `payload` em camelCase com cópia em snake_case (`tenantId`/`tenant_id`,
`legalName`/`legal_name`, `scopes`, `geoLat`, `geoLng`, `status`).

Funções puras (sem banco), testadas sozinhas.
"""

from comum.eventos import EventoInvalido

TIPOS_DE_CARGA = ("GRANEL", "REFRIGERADO", "CARGA_SECA", "PERIGOSO")
ESCOPO_TRANSPORTADORA = "CARRIER"

# Regra de cotação padrão: a transportadora real cota digitando, então a regra só
# define a duração mínima da viagem simulada (km por dia), como na Rodovia Sul.
REGRA_PADRAO = {"preco_minimo": 1000.00, "tarifa_km": 3.20, "tarifa_ton": 40.00, "km_por_dia": 600,
                "prazo_base_dias": 1}


def _campo(payload: dict, *nomes: str):
    for nome in nomes:
        valor = payload.get(nome)
        if valor not in (None, ""):
            return valor
    return None


def transportadora_da_empresa(payload: dict) -> dict | None:
    """Os dados da transportadora, ou None se a empresa não tem o escopo CARRIER (ou não está ativa)."""
    escopos = payload.get("scopes")
    if not isinstance(escopos, list):
        raise EventoInvalido("empresa_cadastrada sem a lista scopes")
    if ESCOPO_TRANSPORTADORA not in escopos:
        return None
    if (payload.get("status") or "ACTIVE") != "ACTIVE":
        return None
    empresa_id = _campo(payload, "tenantId", "tenant_id")
    nome = _campo(payload, "legalName", "legal_name")
    if not isinstance(empresa_id, str) or not isinstance(nome, str):
        raise EventoInvalido("empresa_cadastrada sem tenantId ou legalName")
    if len(empresa_id) > 64:
        raise EventoInvalido(f"tenantId com mais de 64 caracteres: {empresa_id[:70]}")
    return {"id": empresa_id, "empresa_id": empresa_id, "nome": nome.strip()[:200],
            "tipos_carga": list(TIPOS_DE_CARGA)}
