"""Pool de conexões com o PostgreSQL.

Regra do kit: no máximo 5 conexões por instância (2 cópias × 9 serviços × 5
= 90, abaixo do limite de 100 do banco).

Cada serviço conecta com o seu próprio usuário (svc_logistica,
svc_transportadoras), que só enxerga o próprio schema. O kit usava o
superusuário por padrão (K2).

Uso:
    async with db.transacao() as conn:
        await conn.execute("UPDATE ...", (valor,))
    # ao sair do bloco: commit; se houve exceção: rollback
"""

from contextlib import asynccontextmanager

from psycopg import AsyncConnection
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from . import config


def conninfo_do_ambiente() -> str:
    return make_conninfo(
        host=config.texto("DB_HOST", "localhost"),
        port=config.inteiro("DB_PORT", 5432),
        dbname=config.texto("DB_NAME", "portal_b2b"),
        user=config.texto("DB_USER"),
        password=config.texto("DB_PASSWORD"),
        connect_timeout=3,
        application_name=config.texto("SERVICE_NAME", "servico"),
    )


class BancoDeDados:
    def __init__(self, conninfo: str, max_conexoes: int = 5):
        self.pool = AsyncConnectionPool(
            conninfo,
            min_size=1,
            max_size=max_conexoes,
            open=False,
            kwargs={"row_factory": dict_row},
            check=AsyncConnectionPool.check_connection,
        )

    async def abrir(self) -> None:
        # wait=False: o serviço sobe mesmo se o banco ainda não estiver pronto;
        # o /health/ready mostra "banco DOWN" até a conexão funcionar.
        await self.pool.open(wait=False)

    async def fechar(self) -> None:
        await self.pool.close()

    @asynccontextmanager
    async def transacao(self):
        async with self.pool.connection() as conn:
            yield conn

    async def verificar(self) -> None:
        async with self.pool.connection(timeout=2) as conn:
            await conn.execute("SELECT 1")


async def buscar_um(conn: AsyncConnection, sql: str, parametros: tuple | dict = ()) -> dict | None:
    cursor = await conn.execute(sql, parametros)
    return await cursor.fetchone()


async def buscar_todos(conn: AsyncConnection, sql: str, parametros: tuple | dict = ()) -> list[dict]:
    cursor = await conn.execute(sql, parametros)
    return await cursor.fetchall()
