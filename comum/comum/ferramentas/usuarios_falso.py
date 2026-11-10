"""SOMENTE DESENVOLVIMENTO: faz o papel do usuarios-service no login da tela.

O login de verdade é do grupo de Autenticação. Para a tela de rastreio poder
ser usada e demonstrada sem ele, este serviço entrega tokens JWT no mesmo
formato (sub, empresaId, perfil, exp) para alguns usuários de demonstração.
Nunca sobe fora do docker-compose de desenvolvimento.

    uvicorn comum.ferramentas.usuarios_falso:app --port 8101
"""

import time

import jwt
from fastapi import FastAPI
from pydantic import BaseModel

from comum import config
from comum.erros import Problema, registrar_tratadores

# O kit usa 15 min; aqui são 8 h para a demonstração não expirar no meio.
VALIDADE_SEGUNDOS = 8 * 3600

USUARIOS = [
    {"id": "usr-comprador-1", "nome": "João Silva", "perfil": "comprador",
     "empresaId": "emp-comprador-1", "empresaNome": "AgroBrasil Compras"},
    {"id": "usr-fornecedor-1", "nome": "Maria Souza", "perfil": "fornecedor",
     "empresaId": "emp-fornecedor-1", "empresaNome": "Fazenda Boa Safra"},
    {"id": "usr-transp-expressa", "nome": "Carla Expressa", "perfil": "transportadora",
     "empresaId": "emp-transp-expressa", "empresaNome": "Expressa Cargas Rápidas"},
    {"id": "usr-admin", "nome": "Administrador", "perfil": "admin",
     "empresaId": "emp-portal", "empresaNome": "Portal B2B"},
]

app = FastAPI(title="Usuários falso (somente desenvolvimento)", version="0.1.0")
registrar_tratadores(app)


class PedidoDeLogin(BaseModel):
    usuarioId: str


@app.get("/health")
async def saude():
    return {"status": "UP", "service": "usuarios-falso"}


@app.get("/api/v1/usuarios/demonstracao", summary="Usuários de demonstração")
async def listar():
    return USUARIOS


@app.post("/api/v1/usuarios/demonstracao/login", summary="Entra como um usuário de demonstração")
async def entrar(pedido: PedidoDeLogin):
    usuario = next((u for u in USUARIOS if u["id"] == pedido.usuarioId), None)
    if usuario is None:
        raise Problema(404, "USUARIO_NAO_ENCONTRADO", "Usuário não encontrado",
                       f"Não existe usuário de demonstração {pedido.usuarioId}.")
    agora = int(time.time())
    token = jwt.encode({"sub": usuario["id"], "empresaId": usuario["empresaId"], "perfil": usuario["perfil"],
                        "iat": agora, "exp": agora + VALIDADE_SEGUNDOS, "type": "access"},
                       config.texto("JWT_SECRET_KEY"), algorithm=config.texto("JWT_ALGORITHM", "HS256"))
    return {"accessToken": token, "tokenType": "Bearer", "expiresIn": VALIDADE_SEGUNDOS, "usuario": usuario}
