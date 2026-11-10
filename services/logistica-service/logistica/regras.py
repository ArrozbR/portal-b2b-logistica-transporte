"""Regra automática de escolha do frete (decisão D5, arquitetura seção 5.2).

Usada no botão "automático" e quando o prazo de decisão de 12 h vence:

1. menor preço;
2. menor prazo em dias úteis (desempate do kit);
3. maior % de entregas no prazo;
4. transportadoraId em ordem alfabética.

O critério 4 existe para o resultado ser sempre o mesmo: sem ele, um empate
total seria decidido pela ordem de chegada das mensagens, e o teste ficaria
instável.

Este módulo não acessa banco nem Kafka, para poder ser testado sozinho.
"""

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class CotacaoCandidata:
    id: str
    transportadora_id: str
    preco: Decimal
    prazo_dias: int


def escolher_automaticamente(cotacoes: list[CotacaoCandidata],
                             pontualidade: dict[str, float] | None = None) -> CotacaoCandidata:
    """Devolve a cotação vencedora pela regra do kit.

    `pontualidade` mapeia transportadoraId → fração de entregas no prazo
    (0 a 1). Transportadora sem histórico conta como 0.
    """
    if not cotacoes:
        raise ValueError("Não há cotação para escolher")
    pontualidade = pontualidade or {}
    return min(
        cotacoes,
        key=lambda c: (Decimal(c.preco), c.prazo_dias, -pontualidade.get(c.transportadora_id, 0.0),
                       c.transportadora_id),
    )
