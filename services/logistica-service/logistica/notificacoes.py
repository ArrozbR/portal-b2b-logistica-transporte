"""Notificações no portal para comprador e fornecedor (decisão D22).

As notificações são gravadas na tabela `logistica.notificacao` NA MESMA
TRANSAÇÃO da mudança que as gerou: se a mudança for desfeita, a notificação
também é. A tela mostra a contagem de não lidas no sino.

As funções `texto_*` são puras (sem banco), para serem testadas sozinhas.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from psycopg import AsyncConnection

from comum.formatos import data_hora, moeda

COMPRADOR = "comprador"
FORNECEDOR = "fornecedor"


def texto_cotacoes_disponiveis(pedido_id: str, prazo: datetime) -> tuple[str, str]:
    return ("Cotações de frete disponíveis",
            f"O pedido {pedido_id} recebeu cotações de frete. Escolha uma até {data_hora(prazo)}; "
            f"depois disso, o sistema escolhe a de menor preço.")


def texto_sem_cotacao(pedido_id: str, prazo: datetime) -> tuple[str, str]:
    return ("Nenhuma transportadora cotou ainda",
            f"O pedido {pedido_id} ainda não recebeu cotação de frete. Se nenhuma transportadora cotar até "
            f"{data_hora(prazo)}, o frete será dado como indisponível e o pedido será cancelado.")


def texto_frete_escolhido(pedido_id: str, transportadora: str, preco: Decimal, prazo_dias: int,
                          automatico: bool) -> tuple[str, str]:
    como = "pela regra automática (menor preço)" if automatico else "pelo comprador"
    return ("Frete escolhido",
            f"O frete do pedido {pedido_id} foi escolhido {como}: {transportadora}, {moeda(preco)}, "
            f"{prazo_dias} dias úteis.")


def texto_frete_indisponivel(pedido_id: str) -> tuple[str, str]:
    return ("Frete indisponível",
            f"Nenhuma transportadora cotou o frete do pedido {pedido_id} dentro do prazo. "
            f"O pedido será cancelado.")


async def notificar(conn: AsyncConnection, *, empresa_id: str, papel: str, tipo: str, texto: tuple[str, str],
                    pedido_id: str | None, solicitacao_id: str | None, agora: datetime) -> None:
    titulo, mensagem = texto
    await conn.execute("""
        INSERT INTO logistica.notificacao (id, empresa_id, papel, tipo, titulo, mensagem, pedido_id,
                                           solicitacao_id, criada_em)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (str(uuid.uuid4()), empresa_id, papel, tipo, titulo, mensagem, pedido_id, solicitacao_id, agora))
