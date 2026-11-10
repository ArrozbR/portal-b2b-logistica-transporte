"""Motor de cotação simulada (decisão D7, arquitetura seção 5.4).

    preco = max(preco_minimo, (tarifa_km × distancia_km + tarifa_ton × peso_t) × fator_tipo_carga)
    prazo = prazo_base_dias + ceil(distancia_km / km_por_dia)

Cada transportadora tem os seus parâmetros, o que gera escolhas diferentes:
uma cara e rápida, outra barata e lenta, etc. O cálculo é determinístico
(mesma entrada, mesmo resultado), para os testes serem estáveis.

Este módulo não acessa banco nem Kafka.
"""

import math
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal


@dataclass(frozen=True)
class PerfilTransportadora:
    id: str
    nome: str
    tipos_carga: tuple[str, ...]
    ufs_atendidas: tuple[str, ...] | None  # None = atende todo o país


@dataclass(frozen=True)
class RegraCotacao:
    preco_minimo: Decimal
    tarifa_km: Decimal
    tarifa_ton: Decimal
    km_por_dia: int
    prazo_base_dias: int
    fator_tipo_carga: dict[str, Decimal] = field(default_factory=dict)


def atende(perfil: PerfilTransportadora, tipo_carga: str, uf_origem: str, uf_destino: str) -> bool:
    """A transportadora leva esse tipo de carga entre esses dois estados?"""
    if tipo_carga not in perfil.tipos_carga:
        return False
    if perfil.ufs_atendidas is None:
        return True
    return uf_origem in perfil.ufs_atendidas and uf_destino in perfil.ufs_atendidas


def calcular(regra: RegraCotacao, distancia_km: float, peso_kg: float, tipo_carga: str) -> tuple[Decimal, int]:
    """Devolve (preço em R$, prazo em dias úteis)."""
    distancia = Decimal(str(distancia_km))
    peso_t = Decimal(str(peso_kg)) / 1000
    fator = Decimal(str(regra.fator_tipo_carga.get(tipo_carga, 1)))
    bruto = (regra.tarifa_km * distancia + regra.tarifa_ton * peso_t) * fator
    preco = max(regra.preco_minimo, bruto).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    prazo = regra.prazo_base_dias + math.ceil(distancia_km / regra.km_por_dia)
    return preco, prazo
