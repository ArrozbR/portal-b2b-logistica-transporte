"""Pedido de teste criado pelo admin no pedidos-falso (papel do grupo de Pedidos, D23)."""

import json
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from comum import auth
from comum.eventos import erros_do_payload
from comum.ferramentas import pedidos_falso

CHAVE = rsa.generate_private_key(public_exponent=65537, key_size=2048)
KID = "chave-de-teste"


class JwksFalso:
    def get_signing_key(self, kid):
        return type("Chave", (), {"key": CHAVE.public_key()})()


class ProdutorFalso:
    """Guarda o que seria publicado no Kafka."""

    def __init__(self, falhar=False):
        self.enviados, self.falhar = [], falhar

    async def send_and_wait(self, topico, value, key):
        if self.falhar:
            raise ConnectionError("Redpanda fora do ar")
        self.enviados.append((topico, key.decode(), json.loads(value)))


def token(**claims):
    agora = int(time.time())
    base = {"sub": "usr-admin", "iss": "identity-service", "aud": "b2b-platform", "platform_role": "PLATFORM_ADMIN",
            "view_mode": "SINGLE", "tenant_id": "emp-portal", "active_scope": "TENANT_ADMIN", "permissions": [],
            "iat": agora, "exp": agora + 600} | claims
    return jwt.encode(base, CHAVE, algorithm="RS256", headers={"kid": KID})


ADMIN = {"Authorization": f"Bearer {token()}"}
COMPRADOR = {"Authorization": f"Bearer {token(sub='usr-c', platform_role='NONE', tenant_id='emp-comprador-1', active_scope='BUYER')}"}


@pytest.fixture
def produtor(monkeypatch):
    monkeypatch.setenv("JWT_ALGORITHM", "RS256")
    monkeypatch.setattr(auth, "_cliente_jwks", lambda url: JwksFalso())
    falso = ProdutorFalso()
    monkeypatch.setitem(pedidos_falso.kafka, "produtor", falso)
    monkeypatch.setattr(pedidos_falso, "status", {})
    return falso


@pytest.fixture
def cliente():
    return TestClient(pedidos_falso.app)  # sem "with": não sobe o Kafka de verdade


def test_admin_cria_pedido_e_publica_pedido_criado_no_contrato(produtor, cliente):
    r = cliente.post("/api/v1/pedidos-falso/pedidos", headers=ADMIN, json={
        "origem": {"cidade": "sorriso", "uf": "mt"}, "destino": {"cidade": "SANTOS", "uf": "SP"},
        "tipoTransporte": "GRANEL", "pesoKg": 24000, "produtoNome": "Soja em grão", "valorTotal": 192000})
    assert r.status_code == 202
    topico, chave, envelope = produtor.enviados[0]
    assert topico == "pedido_criado" and chave == r.json()["pedidoId"] == envelope["aggregateId"]
    assert envelope["source"] == "pedidos-falso" and envelope["eventType"] == "pedido_criado"
    payload = envelope["payload"]
    assert erros_do_payload("pedido_criado", payload) == []
    # A cidade sai com o nome da lista (acentos e maiúsculas certos), como a logística procura.
    assert payload["origem"] == {"cidade": "Sorriso", "uf": "MT"}
    assert payload["destino"] == {"cidade": "Santos", "uf": "SP"}
    assert payload["compradorId"] == "emp-comprador-1"


def test_correlation_id_da_requisicao_vai_para_o_evento(produtor, cliente):
    r = cliente.post("/api/v1/pedidos-falso/pedidos", headers=ADMIN | {"X-Correlation-Id": "cid-tela-1"},
                     json={"origem": {"cidade": "Rio Verde", "uf": "GO"}, "destino": {"cidade": "Paranaguá", "uf": "PR"}})
    assert r.status_code == 202
    assert produtor.enviados[0][2]["correlationId"] == "cid-tela-1"


def test_so_o_admin_cria_pedido(produtor, cliente):
    corpo = {"origem": {"cidade": "Sorriso", "uf": "MT"}, "destino": {"cidade": "Santos", "uf": "SP"}}
    assert cliente.post("/api/v1/pedidos-falso/pedidos", json=corpo).status_code == 401
    r = cliente.post("/api/v1/pedidos-falso/pedidos", headers=COMPRADOR, json=corpo)
    assert r.status_code == 403 and r.json()["codigo"] == "PERFIL_NAO_PERMITIDO"
    assert produtor.enviados == []


@pytest.mark.parametrize("corpo, codigo", [
    ({"origem": {"cidade": "Atlântida", "uf": "MT"}, "destino": {"cidade": "Santos", "uf": "SP"}}, "CIDADE_DESCONHECIDA"),
    ({"origem": {"cidade": "Santos", "uf": "SP"}, "destino": {"cidade": "santos", "uf": "sp"}}, "ORIGEM_IGUAL_AO_DESTINO"),
    ({"origem": {"cidade": "Sorriso", "uf": "MT"}, "destino": {"cidade": "Santos", "uf": "SP"}, "pesoKg": 0}, "DADOS_INVALIDOS"),
    ({"origem": {"cidade": "Sorriso", "uf": "MT"}, "destino": {"cidade": "Santos", "uf": "SP"}, "tipoTransporte": "VIVO"},
     "DADOS_INVALIDOS"),
])
def test_pedido_invalido_nao_e_publicado(produtor, cliente, corpo, codigo):
    r = cliente.post("/api/v1/pedidos-falso/pedidos", headers=ADMIN, json=corpo)
    assert r.status_code == 422 and r.json()["codigo"] == codigo
    assert produtor.enviados == []


def test_pedido_id_repetido_e_recusado(produtor, cliente):
    corpo = {"origem": {"cidade": "Sorriso", "uf": "MT"}, "destino": {"cidade": "Santos", "uf": "SP"}, "pedidoId": "ped-k6-1"}
    assert cliente.post("/api/v1/pedidos-falso/pedidos", headers=ADMIN, json=corpo).status_code == 202
    r = cliente.post("/api/v1/pedidos-falso/pedidos", headers=ADMIN, json=corpo)
    assert r.status_code == 409 and r.json()["codigo"] == "PEDIDO_JA_EXISTE"
    assert len(produtor.enviados) == 1


def test_kafka_fora_do_ar_responde_503(produtor, cliente, monkeypatch):
    monkeypatch.setitem(pedidos_falso.kafka, "produtor", ProdutorFalso(falhar=True))
    r = cliente.post("/api/v1/pedidos-falso/pedidos", headers=ADMIN,
                     json={"origem": {"cidade": "Sorriso", "uf": "MT"}, "destino": {"cidade": "Santos", "uf": "SP"}})
    assert r.status_code == 503 and r.json()["codigo"] == "KAFKA_INDISPONIVEL"
    assert pedidos_falso.status == {}  # não fica registrado um pedido que não saiu


def test_cancelamento_publica_pedido_atualizado(produtor, cliente):
    r = cliente.post("/api/v1/pedidos-falso/pedidos/ped-k6-2/cancelamento", headers=ADMIN)
    assert r.status_code == 202
    topico, chave, envelope = produtor.enviados[0]
    assert (topico, chave) == ("pedido_atualizado", "ped-k6-2")
    assert envelope["payload"]["novoStatus"] == "CANCELADO"
    assert erros_do_payload("pedido_atualizado", envelope["payload"]) == []


def test_lista_de_cidades_e_a_da_simulacao(produtor, cliente):
    r = cliente.get("/api/v1/pedidos-falso/cidades", headers=ADMIN)
    assert r.status_code == 200
    assert {"cidade": "Jataí", "uf": "GO"} in r.json() and len(r.json()) == 35
