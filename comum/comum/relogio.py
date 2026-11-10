"""Relógio do módulo (decisão D18).

Nenhuma regra de negócio usa a hora do computador. Todas usam o relógio do
módulo, que pode andar mais rápido para a apresentação:

    agora_virtual = base_virtual + (agora_real - base_real) × fator

- fator 1   → tempo real
- fator 360 → 1 hora real vale 15 dias; 3 dias de viagem passam em 12 min

O estado do relógio fica na tabela `relogio` de cada serviço (linha única).
Sem linha gravada, o relógio é a hora real. A alteração pelo administrador e
a sincronização entre os serviços (evento relogio_ajustado) entram na etapa 2.
"""

import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from psycopg import AsyncConnection, sql

from .db import BancoDeDados, buscar_um


@dataclass(frozen=True)
class EstadoRelogio:
    base_real: datetime
    base_virtual: datetime
    fator: float
    versao: int


def calcular_agora(estado: EstadoRelogio | None, agora_real: datetime) -> datetime:
    """Função pura: dado o estado do relógio e a hora real, devolve a hora do módulo."""
    if estado is None:
        return agora_real
    decorrido = (agora_real - estado.base_real).total_seconds()
    return estado.base_virtual + timedelta(seconds=decorrido * estado.fator)


def reajustar(estado: EstadoRelogio | None, agora_real: datetime, novo_fator: float,
              avancar: timedelta = timedelta(0)) -> EstadoRelogio:
    """Novo estado ao mudar o fator, sem salto: a hora do módulo continua de onde estava."""
    agora_virtual = calcular_agora(estado, agora_real) + avancar
    versao = (estado.versao if estado else 0) + 1
    return EstadoRelogio(base_real=agora_real, base_virtual=agora_virtual, fator=novo_fator, versao=versao)


class Relogio:
    def __init__(self, db: BancoDeDados, schema: str, cache_segundos: float = 2.0):
        self.db = db
        self.schema = schema
        self.cache_segundos = cache_segundos
        self._estado: EstadoRelogio | None = None
        self._lido_em = 0.0

    async def estado(self, conn: AsyncConnection | None = None) -> EstadoRelogio | None:
        """Estado atual, com cache de poucos segundos.

        Passe `conn` quando já estiver dentro de uma transação, para não
        ocupar uma segunda conexão do pool.
        """
        if time.monotonic() - self._lido_em > self.cache_segundos:
            if conn is not None:
                linha = await self._ler(conn)
            else:
                async with self.db.transacao() as nova:
                    linha = await self._ler(nova)
            self._estado = EstadoRelogio(linha["base_real"], linha["base_virtual"], float(linha["fator"]),
                                         linha["versao"]) if linha else None
            self._lido_em = time.monotonic()
        return self._estado

    async def _ler(self, conn: AsyncConnection) -> dict | None:
        return await buscar_um(
            conn,
            sql.SQL("SELECT base_real, base_virtual, fator, versao FROM {}.relogio WHERE id = 1")
            .format(sql.Identifier(self.schema)),
        )

    async def agora(self, conn: AsyncConnection | None = None) -> datetime:
        return calcular_agora(await self.estado(conn), datetime.now(timezone.utc))
