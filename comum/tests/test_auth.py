"""Token do grupo de Autenticação (RS256 + JWKS) e do kit (HS256), D25."""

import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from comum import auth
from comum.erros import Problema

CHAVE = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OUTRA_CHAVE = rsa.generate_private_key(public_exponent=65537, key_size=2048)
KID = "chave-de-teste"
SEGREDO = "segredo-de-teste-com-mais-de-32-caracteres"


class JwksFalso:
    """Faz o papel do /.well-known/jwks.json: só conhece o KID."""

    def get_signing_key(self, kid):
        if kid != KID:
            raise jwt.PyJWKClientError(f"kid desconhecido: {kid}")
        return type("Chave", (), {"key": CHAVE.public_key()})()


@pytest.fixture(autouse=True)
def ambiente(monkeypatch):
    monkeypatch.setenv("JWT_ALGORITHM", "RS256")
    monkeypatch.setenv("JWT_SECRET_KEY", SEGREDO)
    monkeypatch.setattr(auth, "_cliente_jwks", lambda url: JwksFalso())


def token_da_autenticacao(chave=CHAVE, kid=KID, segundos=3600, **claims):
    agora = int(time.time())
    # Claims do Identity-Service (TokenIssuer.cs) depois do switch-context.
    base = {"sub": "usr-7", "iss": "identity-service", "aud": "b2b-platform", "platform_role": "NONE",
            "view_mode": "SINGLE", "group_id": "grupo-1", "tenant_id": "emp-34", "allowed_tenants": ["emp-34"],
            "active_scope": "BUYER", "roles": [], "permissions": [], "iat": agora, "exp": agora + segundos}
    base |= claims
    return jwt.encode({k: v for k, v in base.items() if v is not ...}, chave, algorithm="RS256",
                      headers={"kid": kid} if kid else None)


def codigo(token: str) -> tuple[int, str]:
    with pytest.raises(Problema) as erro:
        auth.decodificar(token)
    return erro.value.status, erro.value.codigo


@pytest.mark.parametrize("escopo, perfil", [("BUYER", "comprador"), ("SUPPLIER", "fornecedor"),
                                            ("CARRIER", "transportadora")])
def test_escopo_da_autenticacao_vira_perfil_do_modulo(escopo, perfil):
    usuario = auth.decodificar(token_da_autenticacao(active_scope=escopo))
    assert usuario == auth.Usuario(id="usr-7", empresa_id="emp-34", perfil=perfil)


def test_permissao_logistica_admin_vira_admin():
    usuario = auth.decodificar(token_da_autenticacao(active_scope="TENANT_ADMIN", permissions=["logistica:admin"]))
    assert usuario.admin


def test_tenant_admin_sem_a_permissao_nao_usa_o_modulo():
    assert codigo(token_da_autenticacao(active_scope="TENANT_ADMIN")) == (403, "PERFIL_NAO_PERMITIDO")


def test_escopo_desconhecido_ou_em_minusculas():
    assert codigo(token_da_autenticacao(active_scope="GERENTE")) == (403, "PERFIL_AUSENTE")
    assert codigo(token_da_autenticacao(active_scope="buyer")) == (403, "PERFIL_AUSENTE")


def test_administrador_da_plataforma_vira_admin_mesmo_sem_empresa():
    assert auth.decodificar(token_da_autenticacao(platform_role="PLATFORM_ADMIN", active_scope="TENANT_ADMIN")).admin
    admin = auth.decodificar(token_da_autenticacao(platform_role="PLATFORM_ADMIN", view_mode="NONE", group_id=None,
                                                   tenant_id=None, allowed_tenants=[], active_scope=None))
    assert admin == auth.Usuario(id="usr-7", empresa_id=None, perfil="admin")


def test_agente_de_suporte_nao_e_admin():
    assert codigo(token_da_autenticacao(platform_role="SUPPORT_AGENT", active_scope="TENANT_ADMIN")) == (
        403, "PERFIL_NAO_PERMITIDO")


@pytest.mark.parametrize("caso, claims", [
    ("token do login (view_mode NONE)", dict(view_mode="NONE", group_id=None, tenant_id=None, allowed_tenants=[],
                                              active_scope=None)),
    ("visão de grupo (MACRO_GROUP)", dict(view_mode="MACRO_GROUP", tenant_id=None, allowed_tenants=["a", "b"])),
    ("sem empresa", dict(tenant_id="")),
])
def test_sem_contexto_escolhido(caso, claims):
    assert codigo(token_da_autenticacao(**claims)) == (403, "CONTEXTO_NAO_SELECIONADO"), caso


@pytest.mark.parametrize("caso, claims", [
    ("outra audiência", dict(aud="outro-sistema")),
    ("sem audiência", dict(aud=...)),
    ("outro emissor", dict(iss="servico-falso")),
    ("sem emissor", dict(iss=...)),
])
def test_emissor_e_audiencia_sao_conferidos(caso, claims):
    # O Identity-Service manda iss "identity-service" e aud "b2b-platform".
    assert codigo(token_da_autenticacao(**claims)) == (401, "TOKEN_INVALIDO"), caso


def test_emissor_e_audiencia_vem_da_configuracao(monkeypatch):
    monkeypatch.setenv("JWT_ISSUER", "auth-homologacao")
    monkeypatch.setenv("JWT_AUDIENCE", "portal-homologacao")
    assert auth.decodificar(token_da_autenticacao(iss="auth-homologacao", aud="portal-homologacao")).perfil == "comprador"
    assert codigo(token_da_autenticacao()) == (401, "TOKEN_INVALIDO")


@pytest.mark.parametrize("caso, token", [
    ("assinado com outra chave", lambda: token_da_autenticacao(chave=OUTRA_CHAVE)),
    ("kid desconhecido", lambda: token_da_autenticacao(kid="outra")),
    ("sem kid", lambda: token_da_autenticacao(kid=None)),
    ("HS256 no lugar de RS256", lambda: jwt.encode({"sub": "u", "tenant_id": "e", "active_scope": "BUYER",
                                                     "exp": int(time.time()) + 60}, SEGREDO, algorithm="HS256",
                                                    headers={"kid": KID})),
    ("malformado", lambda: "nao-e-um-token"),
])
def test_token_invalido(caso, token):
    assert codigo(token()) == (401, "TOKEN_INVALIDO"), caso


def test_token_expirado():
    assert codigo(token_da_autenticacao(segundos=-10)) == (401, "TOKEN_EXPIRADO")


def test_jwks_fora_do_ar(monkeypatch):
    class JwksForaDoAr:
        def get_signing_key(self, kid):
            raise jwt.PyJWKClientConnectionError("conexão recusada")
    monkeypatch.setattr(auth, "_cliente_jwks", lambda url: JwksForaDoAr())
    assert codigo(token_da_autenticacao()) == (503, "AUTENTICACAO_INDISPONIVEL")


def test_formato_do_kit_com_hs256(monkeypatch):
    monkeypatch.setenv("JWT_ALGORITHM", "HS256")
    token = jwt.encode({"sub": "usr-1", "empresaId": "emp-1", "perfil": "fornecedor",
                        "exp": int(time.time()) + 60}, SEGREDO, algorithm="HS256")
    assert auth.decodificar(token) == auth.Usuario(id="usr-1", empresa_id="emp-1", perfil="fornecedor")
    # com HS256 configurado, um token RS256 é recusado
    assert codigo(token_da_autenticacao()) == (401, "TOKEN_INVALIDO")


def test_algoritmo_desconhecido_na_configuracao(monkeypatch):
    monkeypatch.setenv("JWT_ALGORITHM", "none")
    with pytest.raises(RuntimeError):
        auth.decodificar(token_da_autenticacao())
