"""Rotinas em segundo plano que não podem morrer.

O consumidor, a outbox e as rotinas de prazo rodam como tarefas asyncio
dentro do processo da API. Se uma delas falhar (ex.: o Redpanda caiu), o
supervisor registra o erro e a reinicia depois de alguns segundos.
"""

import asyncio
import logging
from typing import Awaitable, Callable

log = logging.getLogger(__name__)


async def supervisionar(nome: str, rotina: Callable[[], Awaitable[None]], espera: float = 3.0) -> None:
    while True:
        try:
            await rotina()
            log.warning("Rotina terminou sem erro; reiniciando", extra={"dados": {"rotina": nome}})
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Rotina falhou; reiniciando", extra={"dados": {"rotina": nome, "esperaSegundos": espera}})
        await asyncio.sleep(espera)


async def repetir(intervalo: float, passo: Callable[[], Awaitable[object]]) -> None:
    """Executa `passo` para sempre, esperando `intervalo` segundos entre execuções."""
    while True:
        await passo()
        await asyncio.sleep(intervalo)


def iniciar(tarefas: dict[str, Callable[[], Awaitable[None]]]) -> list[asyncio.Task]:
    return [asyncio.create_task(supervisionar(nome, rotina), name=nome) for nome, rotina in tarefas.items()]


async def parar(tarefas: list[asyncio.Task]) -> None:
    for tarefa in tarefas:
        tarefa.cancel()
    await asyncio.gather(*tarefas, return_exceptions=True)
