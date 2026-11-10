"""SOMENTE DESENVOLVIMENTO: faz o papel do serviço de Autenticação no login da tela.

O login de verdade é do grupo de Autenticação. Para as telas poderem ser
usadas e demonstradas sem ele, este serviço entrega tokens no mesmo formato
que a Autenticação definiu (D25): RS256, com `kid` no cabeçalho, e os claims
`sub`, `tenant_id`, `active_scope`, `roles`, `permissions` e `exp`. A chave
pública fica em `/.well-known/jwks.json`, como no serviço real, e os nossos
serviços a buscam de lá.

A chave RSA é gerada quando o serviço sobe e não é guardada: se ele
reiniciar, os tokens antigos deixam de valer e é preciso entrar de novo.

Com `JWT_ALGORITHM=HS256`, entrega tokens no formato do kit (`empresaId`,
`perfil`), assinados com a `JWT_SECRET_KEY`.

Nunca sobe fora do docker-compose de desenvolvimento.

    uvicorn comum.ferramentas.usuarios_falso:app --port 8101
"""

import hashlib
import json
import time
import uuid

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from jwt.algorithms import RSAAlgorithm
from pydantic import BaseModel, Field

from comum import config
from comum.auth import ESCOPOS, PERFIS, PERMISSAO_ADMIN, algoritmo
from comum.erros import Problema, registrar_tratadores

# O kit usa 15 min; aqui são 8 h para a demonstração não expirar no meio.
VALIDADE_SEGUNDOS = 8 * 3600

USUARIOS = [
    {"id": "usr-comprador-1", "nome": "João Silva", "perfil": "comprador",
     "empresaId": "emp-comprador-1", "empresaNome": "AgroBrasil Compras"},
    {"id": "usr-fornecedor-1", "nome": "Maria Souza", "perfil": "fornecedor",
     "empresaId": "emp-fornecedor-1", "empresaNome": "Fazenda Boa Safra"},
    {"id": "usr-transp-rodovia", "nome": "Rafael Moreira", "perfil": "transportadora",
     "empresaId": "emp-transp-rodovia", "empresaNome": "Rodovia Sul Transportes"},
    {"id": "usr-transp-expressa", "nome": "Carla Expressa", "perfil": "transportadora",
     "empresaId": "emp-transp-expressa", "empresaNome": "Expressa Cargas Rápidas"},
    {"id": "usr-admin", "nome": "Administrador", "perfil": "admin",
     "empresaId": "emp-portal", "empresaNome": "Portal B2B"},
]

# Perfil do módulo → escopo da Autenticação. O admin da plataforma entra como
# TENANT_ADMIN da empresa do portal, com a permissão logistica:admin.
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
    claims = {
        "sub": usuario_id,
        "tenant_id": empresa_id,
        "active_scope": ESCOPO_DO_PERFIL[perfil],
        "roles": [],
        "permissions": [PERMISSAO_ADMIN] if perfil == "admin" else [],
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
