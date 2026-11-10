"""Logs estruturados em JSON, sempre com o correlationId.

Regra do kit: nada de print(); todo log sai em JSON no stdout e carrega o
X-Correlation-Id da requisição ou do evento que está sendo processado.

Uso:
    log = logging.getLogger(__name__)
    log.info("Solicitação criada", extra={"dados": {"solicitacaoFreteId": sid}})
"""

import json
import logging
import sys
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone

# Guarda o correlationId da requisição ou do evento em andamento.
# ContextVar funciona com asyncio: cada tarefa enxerga o seu próprio valor.
correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)

_servico = "desconhecido"


@contextmanager
def correlacao(id_correlacao: str | None):
    """Usa `id_correlacao` nos logs dentro do bloco `with` (para rotinas que não vêm de uma requisição)."""
    token = correlation_id.set(id_correlacao)
    try:
        yield
    finally:
        correlation_id.reset(token)


def agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class FormatoJSON(logging.Formatter):
    def format(self, registro: logging.LogRecord) -> str:
        dados = {
            "timestamp": agora_iso(),
            "level": registro.levelname,
            "service": _servico,
            "correlationId": correlation_id.get(),
            "logger": registro.name,
            "message": registro.getMessage(),
        }
        extras = getattr(registro, "dados", None)
        if isinstance(extras, dict):
            dados.update(extras)
        if registro.exc_info:
            dados["exception"] = self.formatException(registro.exc_info)
        return json.dumps(dados, ensure_ascii=False, default=str)


def configurar_logs(servico: str, nivel: str = "INFO") -> None:
    global _servico
    _servico = servico

    saida = logging.StreamHandler(sys.stdout)
    saida.setFormatter(FormatoJSON())

    raiz = logging.getLogger()
    raiz.handlers[:] = [saida]
    raiz.setLevel(nivel)

    # Faz os logs do uvicorn e do aiokafka saírem no mesmo formato.
    for nome in ("uvicorn", "uvicorn.error", "uvicorn.access", "aiokafka"):
        logger = logging.getLogger(nome)
        logger.handlers[:] = []
        logger.propagate = True
    logging.getLogger("aiokafka").setLevel("WARNING")
    logging.getLogger("uvicorn.access").setLevel("WARNING")
