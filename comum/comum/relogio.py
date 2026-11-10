"""Relógio do módulo (decisão D18).

Nenhuma regra de negócio usa a hora do computador. Todas usam o relógio do
módulo, que pode andar mais rápido para a apresentação:

    agora_virtual = base_virtual + (agora_real - base_real) × fator

- fator 1    → tempo real
- fator 360  → 3 dias de viagem passam em 12 minutos
- fator 3600 → as 12 h de prazo do comprador passam em 12 segundos

Quem manda no relógio é o logistica-service: o administrador altera pela API,
a logística grava na sua tabela `relogio` e publica `relogio_ajustado`; o
transportadoras-service consome e grava na tabela dele. Sem linha gravada, o
relógio é a hora real.

Exceção: a rodada automática de 10 s é um tempo TÉCNICO (espera das respostas
automáticas das transportadoras) e corre na hora real. Se corresse no relógio
acelerado, terminaria antes de as cotações conseguirem chegar.
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

    def para_evento(self) -> dict:
        return {"versao": self.versao, "baseReal": _iso(self.base_real),
                "baseVirtual": _iso(self.base_virtual), "fator": self.fator}

    @staticmethod
    def do_evento(payload: dict) -> "EstadoRelogio":
        return EstadoRelogio(base_real=datetime.fromisoformat(payload["baseReal"]),
                             base_virtual=datetime.fromisoformat(payload["baseVirtual"]),
                             fator=float(payload["fator"]), versao=int(payload["versao"]))


def _iso(momento: datetime) -> str:
    return momento.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


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


async def gravar_estado(conn: AsyncConnection, schema: str, estado: EstadoRelogio) -> bool:
    """Grava o estado se a versão for mais nova que a gravada. Devolve se gravou.

    A comparação de versão torna a gravação idempotente e protege contra
    ajustes que cheguem fora de ordem.
    """
    cursor = await conn.execute(
        sql.SQL("""
            INSERT INTO {tabela} (id, base_real, base_virtual, fator, versao) VALUES (1, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE
               SET base_real = EXCLUDED.base_real, base_virtual = EXCLUDED.base_virtual,
                   fator = EXCLUDED.fator, versao = EXCLUDED.versao
             WHERE {tabela}.versao < EXCLUDED.versao
        """).format(tabela=sql.Identifier(schema, "relogio")),
        (estado.base_real, estado.base_virtual, estado.fator, estado.versao),
    )
    return cursor.rowcount == 1


class Relogio:
    """Lê o estado do relógio do banco.

    Sem cache por padrão: com o relógio acelerado 3600×, um cache de 2 s
    deixaria as duas cópias do serviço até 2 HORAS de módulo uma da outra (uma
    acharia que o prazo venceu antes da outra). Ler uma linha a cada chamada é
    barato, e assim as duas cópias sempre veem o mesmo relógio.
    """

    def __init__(self, db: BancoDeDados, schema: str, cache_segundos: float = 0.0):
        self.db = db
        self.schema = schema
        self.cache_segundos = cache_segundos
        self._estado: EstadoRelogio | None = None
        self._lido_em = float("-inf")

    def invalidar(self) -> None:
        """Força a próxima leitura a ir ao banco (usar depois de um ajuste)."""
        self._lido_em = float("-inf")

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
