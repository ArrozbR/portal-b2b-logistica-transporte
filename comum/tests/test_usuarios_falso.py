"""Login no formato do Identity-Service imitado pelo usuarios-falso (D28).

O token final é conferido pelo mesmo `comum.auth` que os nossos serviços usam.
"""

import pytest
from fastapi.testclient import TestClient

from comum import auth
from comum.erros import Problema
from comum.ferramentas import usuarios_falso


class JwksDoFalso:
    def get_signing_key(self, kid):
        return type("Chave", (), {"key": usuarios_falso._CHAVE_PRIVADA.public_key()})()


@pytest.fixture
def cliente(monkeypatch):
    monkeypatch.setenv("JWT_ALGORITHM", "RS256")
    monkeypatch.setattr(auth, "_cliente_jwks", lambda url: JwksDoFalso())
    return TestClient(usuarios_falso.app)


def entrar(cliente, email, senha="demo"):
    return cliente.post("/api/v1/auth/login", json={"email": email, "password": senha})


def test_login_e_troca_de_contexto_dao_o_token_do_comprador(cliente):
    login = entrar(cliente, "comprador@demo.grupo5")
    assert login.status_code == 200
    corpo = login.json()
    assert corpo["user"]["name"] == "João Silva" and corpo["user"]["platform_role"] == "NONE"
    contexto = corpo["available_contexts"][0]
    assert contexto["tenant_id"] == "emp-comprador-1" and contexto["available_scopes"] == ["BUYER"]

    # O token do login ainda não tem empresa: o módulo responde 403 CONTEXTO_NAO_SELECIONADO.
    with pytest.raises(Problema) as erro:
        auth.decodificar(corpo["access_token"])
    assert erro.value.codigo == "CONTEXTO_NAO_SELECIONADO"

    troca = cliente.post("/api/v1/auth/switch-context",
                         headers={"Authorization": f"Bearer {corpo['access_token']}"},
                         json={"view_mode": "SINGLE", "target_scope": "BUYER", "target_tenant_id": "emp-comprador-1"})
    assert troca.status_code == 200 and troca.json()["context"]["active_scope"] == "BUYER"
    assert auth.decodificar(troca.json()["access_token"]) == auth.Usuario("usr-comprador-1", "emp-comprador-1",
                                                                          "comprador")


def test_refresh_mantem_o_contexto_e_gira_o_refresh_token(cliente):
    login = entrar(cliente, "rodovia@demo.grupo5").json()
    cliente.post("/api/v1/auth/switch-context", headers={"Authorization": f"Bearer {login['access_token']}"},
                 json={"view_mode": "SINGLE", "target_scope": "CARRIER", "target_tenant_id": "emp-transp-rodovia"})
    # A troca de contexto fica na sessão: o refresh devolve o token da transportadora.
    novo = cliente.post("/api/v1/auth/refresh", json={"refresh_token": login["refresh_token"]})
    assert novo.status_code == 200
    assert auth.decodificar(novo.json()["access_token"]).perfil == "transportadora"
    # O refresh_token antigo não vale mais.
    assert cliente.post("/api/v1/auth/refresh", json={"refresh_token": login["refresh_token"]}).status_code == 401


def test_admin_da_plataforma_entra_sem_escolher_empresa(cliente):
    corpo = entrar(cliente, "admin@demo.grupo5").json()
    assert corpo["user"]["platform_role"] == "PLATFORM_ADMIN" and corpo["available_contexts"] == []
    assert auth.decodificar(corpo["access_token"]).admin


@pytest.mark.parametrize("email, senha", [("comprador@demo.grupo5", "errada"), ("ninguem@demo.grupo5", "demo")])
def test_login_invalido(cliente, email, senha):
    assert entrar(cliente, email, senha).status_code == 401


def test_troca_para_empresa_ou_escopo_que_o_usuario_nao_tem(cliente):
    token = entrar(cliente, "comprador@demo.grupo5").json()["access_token"]
    for corpo in ({"view_mode": "SINGLE", "target_scope": "CARRIER", "target_tenant_id": "emp-comprador-1"},
                  {"view_mode": "SINGLE", "target_scope": "BUYER", "target_tenant_id": "emp-outra"}):
        r = cliente.post("/api/v1/auth/switch-context", headers={"Authorization": f"Bearer {token}"}, json=corpo)
        assert r.status_code == 403
