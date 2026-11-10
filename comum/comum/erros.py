"""Respostas de erro no padrão RFC 7807 (Problem Details).

Toda resposta 4xx e 5xx sai com Content-Type application/problem+json e os
campos type, title, status, detail, instance, correlationId e timestamp.
O campo extra "codigo" é um identificador estável para o QA testar
(ex.: FRETE_JA_ESCOLHIDO).

Corrige os itens K9 da análise do kit: o kit não incluía timestamp e deixava
o 422 de validação do FastAPI fora do padrão.
"""

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .logs import agora_iso, correlation_id

TIPO_BASE = "https://portal-b2b.corp/erros/"
TIPO_CONTEUDO = "application/problem+json"


class Problema(Exception):
    """Erro de negócio que vira uma resposta RFC 7807.

    Exemplo:
        raise Problema(409, "FRETE_JA_ESCOLHIDO", "Frete já escolhido",
                       "A solicitação sol-1 já tem um frete escolhido.")
    """

    def __init__(self, status: int, codigo: str, titulo: str, detalhe: str, extras: dict | None = None):
        super().__init__(detalhe)
        self.status = status
        self.codigo = codigo
        self.titulo = titulo
        self.detalhe = detalhe
        self.extras = extras or {}


def _correlacao(request: Request) -> str | None:
    return getattr(request.state, "correlation_id", None) or correlation_id.get()


def resposta_problema(request: Request, status: int, codigo: str, titulo: str, detalhe: str,
                      extras: dict | None = None) -> JSONResponse:
    corpo = {
        "type": TIPO_BASE + codigo.lower().replace("_", "-"),
        "title": titulo,
        "status": status,
        "detail": detalhe,
        "instance": request.url.path,
        "correlationId": _correlacao(request),
        "timestamp": agora_iso(),
        "codigo": codigo,
    }
    if extras:
        corpo.update(jsonable_encoder(extras))
    return JSONResponse(status_code=status, content=corpo, media_type=TIPO_CONTEUDO)


_TITULOS_HTTP = {
    400: ("REQUISICAO_INVALIDA", "Requisição inválida"),
    401: ("NAO_AUTENTICADO", "Não autenticado"),
    403: ("ACESSO_NEGADO", "Acesso negado"),
    404: ("NAO_ENCONTRADO", "Não encontrado"),
    405: ("METODO_NAO_PERMITIDO", "Método não permitido"),
}


def registrar_tratadores(app: FastAPI) -> None:
    @app.exception_handler(Problema)
    async def _problema(request: Request, exc: Problema):
        return resposta_problema(request, exc.status, exc.codigo, exc.titulo, exc.detalhe, exc.extras)

    @app.exception_handler(RequestValidationError)
    async def _validacao(request: Request, exc: RequestValidationError):
        erros = [
            {"campo": ".".join(str(p) for p in erro.get("loc", [])), "mensagem": erro.get("msg")}
            for erro in exc.errors()
        ]
        return resposta_problema(request, 422, "DADOS_INVALIDOS", "Dados inválidos",
                                 "Um ou mais campos da requisição são inválidos.", {"erros": erros})

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException):
        codigo, titulo = _TITULOS_HTTP.get(exc.status_code, ("ERRO_HTTP", "Erro"))
        return resposta_problema(request, exc.status_code, codigo, titulo, str(exc.detail))
