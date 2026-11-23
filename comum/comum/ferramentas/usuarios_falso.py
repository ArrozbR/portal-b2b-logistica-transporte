"""SOMENTE DESENVOLVIMENTO: faz o papel do serviço de Autenticação no login da tela.

O login de verdade é do grupo de Autenticação. Para as telas poderem ser
usadas e demonstradas sem ele, este serviço entrega tokens no mesmo formato
do Identity-Service (D25, `TokenIssuer.cs`): RS256, com `kid` no cabeçalho, e os
claims `sub`, `iss`, `aud`, `platform_role`, `view_mode`, `tenant_id`,
`active_scope`, `roles`, `permissions` e `exp`, como depois do switch-context. A chave
pública fica em `/.well-known/jwks.json`, como no serviço real, e os nossos
serviços a buscam de lá.

A chave RSA é gerada quando o serviço sobe e não é guardada: se ele
reiniciar, os tokens antigos deixam de valer e é preciso entrar de novo.

Com `JWT_ALGORITHM=HS256`, entrega tokens no formato do kit (`empresaId`,
`perfil`), assinados com a `JWT_SECRET_KEY`.

Também imita as rotas de login do Identity-Service (D28), no mesmo formato, para as
telas usarem o fluxo real com o falso ou com o serviço de verdade:

    POST /api/v1/auth/login           e-mail e senha → token sem empresa + refresh_token
                                      + available_contexts (empresas e escopos)
    POST /api/v1/auth/switch-context  escolhe empresa e escopo → token com tenant_id e active_scope
    POST /api/v1/auth/refresh         troca o refresh_token por um token novo (mesmo contexto)
    POST /api/v1/auth/logout          204

Senha de todos os usuários de demonstração: `demo`. O token do login real vale
15 min (`TOKEN_MINUTOS`), como no Identity-Service; a tela renova sozinha.

Nunca sobe fora do docker-compose de desenvolvimento.

    uvicorn comum.ferramentas.usuarios_falso:app --port 8101
"""

import hashlib
import json
import time
import uuid

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI, Header, Response
from jwt.algorithms import RSAAlgorithm
from pydantic import BaseModel, Field

from comum import config
from comum.auth import ADMIN_DA_PLATAFORMA, AUDIENCIA_PADRAO, EMISSOR_PADRAO, ESCOPOS, PERFIS, algoritmo
from comum.erros import Problema, registrar_tratadores

# O kit usa 15 min; aqui são 8 h para a demonstração não expirar no meio.
VALIDADE_SEGUNDOS = 8 * 3600

USUARIOS = [
    {"id": "usr-comprador-1", "nome": "João Silva", "perfil": "comprador", "email": "comprador@demo.grupo5",
     "empresaId": "emp-comprador-1", "empresaNome": "AgroBrasil Compras"},
    {"id": "usr-fornecedor-1", "nome": "Maria Souza", "perfil": "fornecedor", "email": "fornecedor@demo.grupo5",
     "empresaId": "emp-fornecedor-1", "empresaNome": "Fazenda Boa Safra"},
    {"id": "usr-transp-rodovia", "nome": "Rafael Moreira", "perfil": "transportadora", "email": "rodovia@demo.grupo5",
     "empresaId": "emp-transp-rodovia", "empresaNome": "Rodovia Sul Transportes"},
    {"id": "usr-transp-expressa", "nome": "Carla Expressa", "perfil": "transportadora", "email": "expressa@demo.grupo5",
     "empresaId": "emp-transp-expressa", "empresaNome": "Expressa Cargas Rápidas"},
    {"id": "usr-admin", "nome": "Administrador", "perfil": "admin", "email": "admin@demo.grupo5",
     "empresaId": "emp-portal", "empresaNome": "Portal B2B"},
]
SENHA_DEMONSTRACAO = "demo"

# Perfil do módulo → escopo da Autenticação. O admin da plataforma entra como
# TENANT_ADMIN da empresa do portal, com platform_role PLATFORM_ADMIN.
ESCOPO_DO_PERFIL = {perfil: escopo for escopo, perfil in ESCOPOS.items()} | {"admin": "TENANT_ADMIN"}

_CHAVE_PRIVADA = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_JWK = RSAAlgorithm.to_jwk(_CHAVE_PRIVADA.public_key(), as_dict=True)
KID = "usuarios-falso-" + hashlib.sha256(json.dumps(_JWK, sort_keys=True).encode()).hexdigest()[:16]
_JWK |= {"kid": KID, "use": "sig", "alg": "RS256"}

app = FastAPI(title="Usuários falso (somente desenvolvimento)", version="0.2.0")
registrar_tratadores(app)


def emitir_token(usuario_id: str, empresa_id: str, perfil: str, segundos: int = VALIDADE_SEGUNDOS) -> str:
    agora = int(time.time())
    if algoritmo() == "HS256":  # formato do kit
        claims = {"sub": usuario_id, "empresaId": empresa_id, "perfil": perfil,
                  "iat": agora, "exp": agora + segundos, "type": "access"}
        return jwt.encode(claims, config.texto("JWT_SECRET_KEY"), algorithm="HS256")
    # Mesmos claims do Identity-Service (TokenIssuer.cs), depois do switch-context (view_mode SINGLE).
    # O admin é o administrador da plataforma (platform_role PLATFORM_ADMIN), como o
    # platform-admin@agrobrasil.com.br do seed deles.
    claims = {
        "jti": str(uuid.uuid4()),
        "sub": usuario_id,
        "iss": config.texto("JWT_ISSUER", EMISSOR_PADRAO),
        "aud": config.texto("JWT_AUDIENCE", AUDIENCIA_PADRAO),
        "platform_role": ADMIN_DA_PLATAFORMA if perfil == "admin" else "NONE",
        "view_mode": "SINGLE",
        "group_id": f"grupo-{empresa_id}",
        "tenant_id": empresa_id,
        "allowed_tenants": [empresa_id],
        "active_scope": ESCOPO_DO_PERFIL[perfil],
        "roles": [],
        "permissions": [],
        "iat": agora,
        "exp": agora + segundos,
    }
    return jwt.encode(claims, _CHAVE_PRIVADA, algorithm="RS256", headers={"kid": KID})


class PedidoDeLogin(BaseModel):
    usuarioId: str


class PedidoDeToken(BaseModel):
    perfil: str = Field(..., description="comprador, fornecedor, transportadora ou admin")
    empresaId: str = "emp-comprador-1"
    usuarioId: str | None = None
    minutos: int = Field(15, ge=1, le=24 * 60)


@app.get("/health")
async def saude():
    return {"status": "UP", "service": "usuarios-falso"}


@app.get("/.well-known/jwks.json", summary="Chaves públicas para validar os tokens")
async def jwks():
    return {"keys": [_JWK]}


@app.get("/api/v1/usuarios/demonstracao", summary="Usuários de demonstração")
async def listar():
    return USUARIOS


@app.post("/api/v1/usuarios/demonstracao/login", summary="Entra como um usuário de demonstração")
async def entrar(pedido: PedidoDeLogin):
    usuario = next((u for u in USUARIOS if u["id"] == pedido.usuarioId), None)
    if usuario is None:
        raise Problema(404, "USUARIO_NAO_ENCONTRADO", "Usuário não encontrado",
                       f"Não existe usuário de demonstração {pedido.usuarioId}.")
    token = emitir_token(usuario["id"], usuario["empresaId"], usuario["perfil"])
    return {"accessToken": token, "tokenType": "Bearer", "expiresIn": VALIDADE_SEGUNDOS, "usuario": usuario}


@app.post("/api/v1/usuarios/demonstracao/token", summary="Token de teste para qualquer perfil e empresa")
async def token_de_teste(pedido: PedidoDeToken):
    if pedido.perfil not in PERFIS:
        raise Problema(422, "PERFIL_INVALIDO", "Perfil inválido", f"Use um destes perfis: {', '.join(PERFIS)}.")
    usuario_id = pedido.usuarioId or f"usr-{uuid.uuid4().hex[:8]}"
    return {"accessToken": emitir_token(usuario_id, pedido.empresaId, pedido.perfil, pedido.minutos * 60),
            "tokenType": "Bearer", "expiresIn": pedido.minutos * 60}


# ---------------------------------------------------------------------------- rotas do Identity-Service (D28)
# Mesmos caminhos, corpos e respostas do Identity-Service (LoginEndpoint.cs,
# SwitchContextEndpoint.cs, RefreshEndpoint.cs), só com o que as nossas telas usam.

def _minutos() -> int:
    return config.inteiro("TOKEN_MINUTOS", 15)


# refresh_token → {"usuarioId", "perfil" ou None (token do login, sem empresa)}
_SESSOES: dict[str, dict] = {}


def _usuario_por(campo: str, valor: str) -> dict | None:
    return next((u for u in USUARIOS if u[campo] == valor), None)


def _escopo(usuario: dict) -> str:
    return "PLATFORM_ADMIN" if usuario["perfil"] == "admin" else ESCOPO_DO_PERFIL[usuario["perfil"]]


def _token_sem_contexto(usuario: dict) -> str:
    """Token do login (view_mode NONE): ainda sem empresa nem escopo, como no Identity-Service."""
    if usuario["perfil"] == "admin":
        # O administrador da plataforma usa o módulo sem escolher empresa (platform_role).
        return emitir_token(usuario["id"], usuario["empresaId"], "admin", _minutos() * 60)
    agora = int(time.time())
    claims = {"jti": str(uuid.uuid4()), "sub": usuario["id"], "iss": config.texto("JWT_ISSUER", EMISSOR_PADRAO),
              "aud": config.texto("JWT_AUDIENCE", AUDIENCIA_PADRAO), "platform_role": "NONE", "view_mode": "NONE",
              "allowed_tenants": [], "roles": [], "permissions": [], "iat": agora, "exp": agora + _minutos() * 60}
    return jwt.encode(claims, _CHAVE_PRIVADA, algorithm="RS256", headers={"kid": KID})


def _nova_sessao(usuario: dict, perfil: str | None) -> str:
    refresh = uuid.uuid4().hex + uuid.uuid4().hex
    _SESSOES[refresh] = {"usuarioId": usuario["id"], "perfil": perfil}
    return refresh


def _contextos(usuario: dict) -> list[dict]:
    if usuario["perfil"] == "admin":
        return []
    return [{"group_id": f"grupo-{usuario['empresaId']}", "group_name": usuario["empresaNome"],
             "tenant_id": usuario["empresaId"], "cnpj": None, "legal_name": usuario["empresaNome"],
             "branch_type": "HEADQUARTERS", "is_owner": True, "can_view_group": False,
             "available_scopes": [_escopo(usuario)], "roles": []}]


def _erro_auth(status: int, codigo: str, detalhe: str) -> Problema:
    return Problema(status, codigo, "Falha na autenticação", detalhe)


class PedidoDeLoginReal(BaseModel):
    email: str
    password: str


class TrocaDeContexto(BaseModel):
    view_mode: str
    target_scope: str
    target_tenant_id: str | None = None


class Renovacao(BaseModel):
    refresh_token: str


@app.post("/api/v1/auth/login", summary="Login (mesmo formato do Identity-Service)")
async def login_real(pedido: PedidoDeLoginReal):
    usuario = _usuario_por("email", pedido.email.strip().lower())
    if usuario is None or pedido.password != SENHA_DEMONSTRACAO:
        raise _erro_auth(401, "ERR-AUTH-001", "E-mail ou senha inválidos.")
    perfil = "admin" if usuario["perfil"] == "admin" else None
    return {"access_token": _token_sem_contexto(usuario), "token_type": "Bearer", "expires_in": _minutos() * 60,
            "refresh_token": _nova_sessao(usuario, perfil), "refresh_expires_in": 604800,
            "user": {"id": usuario["id"], "email": usuario["email"], "name": usuario["nome"],
                     "platform_role": "PLATFORM_ADMIN" if usuario["perfil"] == "admin" else "NONE"},
            "available_contexts": _contextos(usuario)}


@app.post("/api/v1/auth/switch-context", summary="Escolhe empresa e escopo (mesmo formato do Identity-Service)")
async def trocar_contexto(pedido: TrocaDeContexto, authorization: str | None = Header(None)):
    token = (authorization or "").removeprefix("Bearer ").strip()
    try:
        claims = jwt.decode(token, _CHAVE_PRIVADA.public_key(), algorithms=["RS256"],
                            audience=config.texto("JWT_AUDIENCE", AUDIENCIA_PADRAO))
    except jwt.InvalidTokenError:
        raise _erro_auth(401, "ERR-AUTH-002", "Envie o token do login no cabeçalho Authorization.")
    usuario = _usuario_por("id", claims["sub"])
    if usuario is None or pedido.view_mode != "SINGLE" or pedido.target_tenant_id != usuario["empresaId"] \
            or pedido.target_scope != _escopo(usuario):
        raise _erro_auth(403, "ERR-AUTH-003", "O usuário não tem esse escopo nessa empresa.")
    # Como na família de sessão do Identity-Service: o refresh passa a renovar com este contexto.
    for sessao in _SESSOES.values():
        if sessao["usuarioId"] == usuario["id"]:
            sessao["perfil"] = usuario["perfil"]
    return {"access_token": emitir_token(usuario["id"], usuario["empresaId"], usuario["perfil"], _minutos() * 60),
            "token_type": "Bearer", "expires_in": _minutos() * 60,
            "context": {"sub": usuario["id"], "tenant_id": usuario["empresaId"], "view_mode": "SINGLE",
                        "active_scope": pedido.target_scope, "roles": [], "permissions": []}}


@app.post("/api/v1/auth/refresh", summary="Renova o token (mesmo formato do Identity-Service)")
async def renovar(pedido: Renovacao):
    sessao = _SESSOES.pop(pedido.refresh_token, None)
    usuario = _usuario_por("id", sessao["usuarioId"]) if sessao else None
    if usuario is None:
        raise _erro_auth(401, "ERR-AUTH-004", "Sessão expirada. Faça login de novo.")
    token = (emitir_token(usuario["id"], usuario["empresaId"], usuario["perfil"], _minutos() * 60)
             if sessao["perfil"] else _token_sem_contexto(usuario))
    return {"access_token": token, "token_type": "Bearer", "expires_in": _minutos() * 60,
            "refresh_token": _nova_sessao(usuario, sessao["perfil"]), "refresh_expires_in": 604800}


@app.post("/api/v1/auth/logout", status_code=204, summary="Encerra a sessão")
async def logout():
    return Response(status_code=204)
