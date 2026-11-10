"""Regra automática de escolha do frete e selos da comparação (decisões D5 e D6).

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


# --------------------------------------------------------------------------- comparação (D6)

MAIS_BARATA = "MAIS_BARATA"
MAIS_RAPIDA = "MAIS_RAPIDA"
MAIS_PONTUAL = "MAIS_PONTUAL"
RECOMENDADA = "RECOMENDADA_PELA_REGRA"


def preco_por_tonelada_km(preco: Decimal, peso_kg: float, distancia_km: float) -> Decimal | None:
    """Preço do frete dividido por toneladas × km: compara cargas e rotas de tamanhos diferentes."""
    base = Decimal(str(peso_kg)) / 1000 * Decimal(str(distancia_km))
    return (Decimal(preco) / base).quantize(Decimal("0.0001")) if base > 0 else None


def selos(cotacoes: list[CotacaoCandidata], pontualidade: dict[str, float] | None = None) -> dict[str, list[str]]:
    """Selos de cada cotação: mais barata, mais rápida, mais pontual e recomendada pela regra automática.

    Empates ganham o selo juntos. "Mais pontual" só aparece se alguma
    transportadora já tiver entregas no histórico (`pontualidade`).
    """
    resultado: dict[str, list[str]] = {c.id: [] for c in cotacoes}
    if not cotacoes:
        return resultado
    pontualidade = pontualidade or {}
    menor_preco = min(Decimal(c.preco) for c in cotacoes)
    menor_prazo = min(c.prazo_dias for c in cotacoes)
    com_historico = [c for c in cotacoes if c.transportadora_id in pontualidade]
    maior_pontualidade = max((pontualidade[c.transportadora_id] for c in com_historico), default=None)
    recomendada = escolher_automaticamente(cotacoes, pontualidade).id
    for c in cotacoes:
        if Decimal(c.preco) == menor_preco:
            resultado[c.id].append(MAIS_BARATA)
        if c.prazo_dias == menor_prazo:
            resultado[c.id].append(MAIS_RAPIDA)
        if maior_pontualidade is not None and pontualidade.get(c.transportadora_id) == maior_pontualidade:
            resultado[c.id].append(MAIS_PONTUAL)
        if c.id == recomendada:
            resultado[c.id].append(RECOMENDADA)
    return resultado
