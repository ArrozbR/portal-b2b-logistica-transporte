"""Cidades, distâncias e dias úteis (decisões D9 e D15).

As coordenadas são aproximadas (centro da cidade) e servem só para a
simulação. A lista cobre polos do agronegócio e portos, que é o cenário do
portal. Cidade fora da lista: o evento vai para a DLT com o motivo, e a
cidade pode ser acrescentada aqui.
"""

import math
import unicodedata
from dataclasses import dataclass
from datetime import date, timedelta

FATOR_SINUOSIDADE = 1.3  # estrada é ~30% mais longa que a linha reta


@dataclass(frozen=True)
class Cidade:
    nome: str
    uf: str
    lat: float
    lon: float


_CIDADES = [
    # Mato Grosso
    Cidade("Sorriso", "MT", -12.5453, -55.7114),
    Cidade("Sinop", "MT", -11.8642, -55.5093),
    Cidade("Lucas do Rio Verde", "MT", -13.0588, -55.9042),
    Cidade("Rondonópolis", "MT", -16.4673, -54.6372),
    Cidade("Cuiabá", "MT", -15.6014, -56.0979),
    Cidade("Primavera do Leste", "MT", -15.5600, -54.2811),
    Cidade("Sapezal", "MT", -13.5428, -58.8146),
    Cidade("Campo Novo do Parecis", "MT", -13.6587, -57.8907),
    # Goiás
    Cidade("Rio Verde", "GO", -17.7923, -50.9192),
    Cidade("Goiânia", "GO", -16.6869, -49.2648),
    Cidade("Jataí", "GO", -17.8784, -51.7204),
    # Mato Grosso do Sul
    Cidade("Campo Grande", "MS", -20.4697, -54.6201),
    Cidade("Dourados", "MS", -22.2231, -54.8120),
    Cidade("Maracaju", "MS", -21.6105, -55.1678),
    # Minas Gerais
    Cidade("Uberlândia", "MG", -18.9128, -48.2755),
    Cidade("Uberaba", "MG", -19.7472, -47.9381),
    Cidade("Belo Horizonte", "MG", -19.9167, -43.9345),
    # Paraná
    Cidade("Paranaguá", "PR", -25.5205, -48.5095),
    Cidade("Cascavel", "PR", -24.9578, -53.4596),
    Cidade("Londrina", "PR", -23.3045, -51.1696),
    Cidade("Curitiba", "PR", -25.4284, -49.2733),
    Cidade("Ponta Grossa", "PR", -25.0950, -50.1619),
    # São Paulo
    Cidade("Santos", "SP", -23.9608, -46.3336),
    Cidade("São Paulo", "SP", -23.5505, -46.6333),
    Cidade("Campinas", "SP", -22.9099, -47.0626),
    Cidade("Ribeirão Preto", "SP", -21.1704, -47.8103),
    # Outros portos e polos
    Cidade("Luís Eduardo Magalhães", "BA", -12.0960, -45.7866),
    Cidade("Salvador", "BA", -12.9777, -38.5016),
    Cidade("Balsas", "MA", -7.5325, -46.0356),
    Cidade("São Luís", "MA", -2.5307, -44.3068),
    Cidade("Recife", "PE", -8.0476, -34.8770),
    Cidade("Porto Alegre", "RS", -30.0346, -51.2177),
    Cidade("Rio Grande", "RS", -32.0350, -52.0986),
    Cidade("Itajaí", "SC", -26.9078, -48.6619),
    Cidade("Rio de Janeiro", "RJ", -22.9068, -43.1729),
]


def _normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    return " ".join(sem_acento.lower().split())


_INDICE = {(_normalizar(c.nome), c.uf): c for c in _CIDADES}


def buscar_cidade(nome: str, uf: str) -> Cidade | None:
    """Busca sem diferenciar maiúsculas nem acentos: "SAO PAULO"/"sp" encontra São Paulo."""
    return _INDICE.get((_normalizar(nome), uf.strip().upper()))


def cidades() -> list[Cidade]:
    return list(_CIDADES)


def distancia_linha_reta_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Fórmula de haversine: distância sobre a superfície da Terra."""
    raio_terra = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * raio_terra * math.asin(math.sqrt(a))


def distancia_estrada_km(origem: Cidade, destino: Cidade) -> float:
    reta = distancia_linha_reta_km(origem.lat, origem.lon, destino.lat, destino.lon)
    return round(reta * FATOR_SINUOSIDADE, 1)


def somar_dias_uteis(inicio: date, dias: int) -> date:
    """Soma dias úteis (segunda a sexta). Feriados não são considerados."""
    atual = inicio
    restantes = dias
    while restantes > 0:
        atual += timedelta(days=1)
        if atual.weekday() < 5:
            restantes -= 1
    return atual


def proximo_dia_util(dia: date) -> date:
    return somar_dias_uteis(dia, 1)
