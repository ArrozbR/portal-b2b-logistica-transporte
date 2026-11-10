"""Validação do JWT e controle de acesso por perfil (D25).

O algoritmo vem da configuração, nunca do próprio token:

- RS256 (padrão): o token do grupo de Autenticação. É assinado com uma chave
  RSA privada, que só a Autenticação tem; a chave pública de cada `kid` vem do
  JWKS (`AUTH_JWKS_URL`, normalmente `/.well-known/jwks.json` pelo gateway),
  guardada em cache por 1 hora. Claims: `sub`, `iss` (`identity-service`),
  `aud` (`b2b-platform`), `exp`, `platform_role` (NONE, SUPPORT_AGENT,
  PLATFORM_ADMIN), `view_mode` (NONE, SINGLE, MACRO_GROUP), `tenant_id`,
  `active_scope` (BUYER, SUPPLIER, CARRIER, TENANT_ADMIN) e `permissions`
  (código do Identity-Service, `TokenIssuer.cs`). `iss` e `aud` são conferidos
  (`JWT_ISSUER`, `JWT_AUDIENCE`): o PyJWT recusa um token com `aud` se a
  audiência esperada não for informada.
- HS256 (`JWT_ALGORITHM=HS256`): o formato do kit, com a chave compartilhada
  `JWT_SECRET_KEY` e os claims `sub`, `empresaId` (ou `empresa_id`), `perfil`
  e `exp`. Fica para rodar com o kit enquanto ele não for atualizado.

Os dois formatos viram os perfis do módulo:

| Token | Perfil |
|---|---|
| `active_scope` BUYER | comprador |
| `active_scope` SUPPLIER | fornecedor |
| `active_scope` CARRIER | transportadora |
| `platform_role` PLATFORM_ADMIN (ou permissão `logistica:admin`) | admin (administrador da plataforma) |
| `active_scope` TENANT_ADMIN, sem ser administrador da plataforma | 403: administra a empresa, não o módulo |
| Sem empresa ou sem escopo ativo (`view_mode` NONE, logo depois do login, ou MACRO_GROUP) | 403 `CONTEXTO_NAO_SELECIONADO`: a tela deve chamar o switch-context |

O admin do módulo vê as entregas de todas as empresas e mexe no relógio, por
isso não basta ser administrador de uma empresa. O administrador da plataforma
não precisa ter escolhido uma empresa.

- Sem token, token inválido ou expirado: 401.
- Perfil sem permissão para a rota: 403.
- Token sem perfil: 403 (o kit devolvia 500 nesse caso, K8).

Uso numa rota:
    @rotas.get("/x")
    async def x(usuario: Usuario = Depends(exigir_perfis("comprador", "admin"))):
        ...
"""

from dataclasses import dataclass
from functools import lru_cache

import jwt
from fastapi import Depends, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from . import config
from .erros import Problema

PERFIS = ("comprador", "fornecedor", "transportadora", "admin")
ALGORITMOS = ("RS256", "HS256")
ESCOPOS = {"BUYER": "comprador", "SUPPLIER": "fornecedor", "CARRIER": "transportadora"}
ESCOPO_ADMIN_DA_EMPRESA = "TENANT_ADMIN"
ADMIN_DA_PLATAFORMA = "PLATFORM_ADMIN"  # claim platform_role do Identity-Service
PERMISSAO_ADMIN = "logistica:admin"     # alternativa, proposta nossa (D25)
JWKS_PADRAO = "http://gateway:8080/.well-known/jwks.json"  # o endereço que a Autenticação indicou
EMISSOR_PADRAO = "identity-service"     # JWT_ISSUER do Identity-Service
AUDIENCIA_PADRAO = "b2b-platform"       # JWT_AUDIENCE do Identity-Service

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Usuario:
    id: str
    empresa_id: str | None
    perfil: str

    @property
    def admin(self) -> bool:
        return self.perfil == "admin"


def algoritmo() -> str:
    alg = config.texto("JWT_ALGORITHM", "RS256").upper()
    if alg not in ALGORITMOS:
        raise RuntimeError(f"JWT_ALGORITHM deve ser {' ou '.join(ALGORITMOS)}, não {alg}")
    return alg


@lru_cache
def _cliente_jwks(url: str) -> jwt.PyJWKClient:
    # Busca o JWKS uma vez e guarda por 1 hora. Um kid desconhecido (a
    # Autenticação trocou a chave) faz uma nova busca, no máximo a cada 5 s:
    # um token com kid inventado não faz o serviço buscar o JWKS sem parar.
    return jwt.PyJWKClient(url, cache_jwk_set=True, lifespan=3600, timeout=5, cooldown_duration=5)


def _invalido(detalhe: str = "O token de acesso não é válido.") -> Problema:
    return Problema(401, "TOKEN_INVALIDO", "Token inválido", detalhe)


def _chave(token: str, alg: str):
    if alg == "HS256":
        return config.texto("JWT_SECRET_KEY")
    try:
        kid = jwt.get_unverified_header(token).get("kid")
    except jwt.InvalidTokenError:
        raise _invalido()
    if not kid:
        raise _invalido("O token não informa a chave (kid) que o assinou.")
    try:
        return _cliente_jwks(config.texto("AUTH_JWKS_URL", JWKS_PADRAO)).get_signing_key(kid).key
    except jwt.PyJWKClientConnectionError:
        raise Problema(503, "AUTENTICACAO_INDISPONIVEL", "Autenticação indisponível",
                       "Não foi possível obter as chaves do serviço de Autenticação. Tente de novo em instantes.")
    except jwt.PyJWKClientError:
        raise _invalido("A chave que assinou o token não é conhecida.")


def _usuario(claims: dict) -> Usuario:
    if algoritmo() == "RS256":  # formato do grupo de Autenticação
        empresa = claims.get("tenant_id") or None
        escopo = claims.get("active_scope")
        permissoes = claims.get("permissions")
        if claims.get("platform_role") == ADMIN_DA_PLATAFORMA or (
                isinstance(permissoes, list) and PERMISSAO_ADMIN in permissoes):
            perfil = "admin"  # não precisa ter escolhido uma empresa
        elif not isinstance(empresa, str) or not escopo:
            # Token do login (view_mode NONE) ou de grupo (MACRO_GROUP): o módulo trabalha com uma empresa só.
            raise Problema(403, "CONTEXTO_NAO_SELECIONADO", "Empresa e perfil não escolhidos",
                           "Escolha a empresa e o escopo (BUYER, SUPPLIER ou CARRIER) pela troca de contexto "
                           "(POST /api/v1/auth/switch-context, view_mode SINGLE) antes de usar o módulo.")
        elif escopo == ESCOPO_ADMIN_DA_EMPRESA:
            raise Problema(403, "PERFIL_NAO_PERMITIDO", "Acesso negado",
                           "O escopo TENANT_ADMIN administra a empresa e não usa o módulo de logística. "
                           "Troque o contexto para BUYER, SUPPLIER ou CARRIER.")
        else:
            perfil = ESCOPOS.get(escopo)
    else:  # formato do kit
        empresa = claims.get("empresaId") or claims.get("empresa_id")
        perfil = claims.get("perfil")

    if perfil not in PERFIS:
        raise Problema(403, "PERFIL_AUSENTE", "Acesso negado", "O token não informa um perfil válido.")
    return Usuario(id=str(claims["sub"]), empresa_id=empresa, perfil=perfil)


def decodificar(token: str) -> Usuario:
    alg = algoritmo()
    chave = _chave(token, alg)
    try:
        if alg == "RS256":
            claims = jwt.decode(token, chave, algorithms=[alg],
                                issuer=config.texto("JWT_ISSUER", EMISSOR_PADRAO),
                                audience=config.texto("JWT_AUDIENCE", AUDIENCIA_PADRAO),
                                options={"require": ["exp", "sub", "iss", "aud"]})
        else:  # o token do kit não tem iss nem aud
            claims = jwt.decode(token, chave, algorithms=[alg], options={"require": ["exp", "sub"]})
    except jwt.ExpiredSignatureError:
        raise Problema(401, "TOKEN_EXPIRADO", "Token expirado", "O token de acesso expirou. Faça login de novo.")
    except (jwt.InvalidAudienceError, jwt.InvalidIssuerError):
        raise _invalido("O token não foi emitido pelo serviço de Autenticação para o portal (iss ou aud).")
    except jwt.InvalidTokenError:
        raise _invalido()
    return _usuario(claims)


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
