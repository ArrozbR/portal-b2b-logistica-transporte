"""Validação do JWT emitido pelo usuarios-service e controle de acesso por perfil.

O token tem os claims sub (usuário), empresaId (o guia do kit chama de
empresa_id; aceitamos os dois), perfil (comprador, fornecedor,
transportadora ou admin) e exp.

- Sem token, token inválido ou expirado: 401.
- Perfil sem permissão para a rota: 403.
- Token sem perfil: 403 (o kit devolvia 500 nesse caso, K8).

Uso numa rota:
    @rotas.get("/x")
    async def x(usuario: Usuario = Depends(exigir_perfis("comprador", "admin"))):
        ...
"""

from dataclasses import dataclass

import jwt
from fastapi import Depends, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from . import config
from .erros import Problema

PERFIS = ("comprador", "fornecedor", "transportadora", "admin")

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Usuario:
    id: str
    empresa_id: str | None
    perfil: str

    @property
    def admin(self) -> bool:
        return self.perfil == "admin"


def _segredo() -> str:
    return config.texto("JWT_SECRET_KEY")


def decodificar(token: str) -> Usuario:
    try:
        claims = jwt.decode(token, _segredo(), algorithms=[config.texto("JWT_ALGORITHM", "HS256")])
    except jwt.ExpiredSignatureError:
        raise Problema(401, "TOKEN_EXPIRADO", "Token expirado", "O token de acesso expirou. Faça login de novo.")
    except jwt.InvalidTokenError:
        raise Problema(401, "TOKEN_INVALIDO", "Token inválido", "O token de acesso não é válido.")

    perfil = claims.get("perfil")
    if perfil not in PERFIS:
        raise Problema(403, "PERFIL_AUSENTE", "Acesso negado", "O token não informa um perfil válido.")
    return Usuario(id=str(claims.get("sub")), empresa_id=claims.get("empresaId") or claims.get("empresa_id"),
                   perfil=perfil)


def usuario_atual(credenciais: HTTPAuthorizationCredentials | None = Security(_bearer)) -> Usuario:
    if credenciais is None:
        raise Problema(401, "NAO_AUTENTICADO", "Não autenticado",
                       "Envie o token no cabeçalho Authorization: Bearer <token>.")
    return decodificar(credenciais.credentials)


def exigir_perfis(*perfis: str):
    def verificar(usuario: Usuario = Depends(usuario_atual)) -> Usuario:
        if usuario.perfil not in perfis:
            raise Problema(403, "PERFIL_NAO_PERMITIDO", "Acesso negado",
                           f"O perfil '{usuario.perfil}' não pode usar esta rota. Perfis permitidos: {', '.join(perfis)}.")
        return usuario
    return verificar
