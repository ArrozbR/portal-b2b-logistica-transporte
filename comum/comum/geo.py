"""Cidades, distâncias e dias úteis (decisões D9 e D15).

As coordenadas são aproximadas (centro da cidade) e servem só para a
simulação. A lista cobre as 27 capitais, polos do agronegócio, cidades médias e
portos, que é o cenário do portal. Cidade fora da lista: o evento vai para a DLT com o motivo, e a
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
    # Acrescentadas em 23/11/2026: todas as capitais e mais polos do agronegócio,
    # cidades médias e portos (o grupo de Pedidos usa Anápolis/GO nos exemplos).
    # Capitais que faltavam
    Cidade("Brasília", "DF", -15.7939, -47.8828),
    Cidade("Palmas", "TO", -10.1840, -48.3336),
    Cidade("Belém", "PA", -1.4558, -48.4902),
    Cidade("Manaus", "AM", -3.1190, -60.0217),
    Cidade("Porto Velho", "RO", -8.7612, -63.9004),
    Cidade("Rio Branco", "AC", -9.9754, -67.8249),
    Cidade("Boa Vista", "RR", 2.8235, -60.6758),
    Cidade("Macapá", "AP", 0.0349, -51.0694),
    Cidade("Teresina", "PI", -5.0920, -42.8038),
    Cidade("Fortaleza", "CE", -3.7319, -38.5267),
    Cidade("Natal", "RN", -5.7945, -35.2110),
    Cidade("João Pessoa", "PB", -7.1195, -34.8450),
    Cidade("Maceió", "AL", -9.6658, -35.7353),
    Cidade("Aracaju", "SE", -10.9472, -37.0731),
    Cidade("Vitória", "ES", -20.3155, -40.3128),
    Cidade("Florianópolis", "SC", -27.5954, -48.5480),
    # Goiás e Distrito Federal
    Cidade("Anápolis", "GO", -16.3281, -48.9534),
    Cidade("Aparecida de Goiânia", "GO", -16.8198, -49.2469),
    Cidade("Itumbiara", "GO", -18.4093, -49.2158),
    Cidade("Catalão", "GO", -18.1656, -47.9440),
    Cidade("Mineiros", "GO", -17.5654, -52.5537),
    Cidade("Cristalina", "GO", -16.7676, -47.6131),
    Cidade("Luziânia", "GO", -16.2525, -47.9501),
    Cidade("Quirinópolis", "GO", -18.4483, -50.4519),
    # Mato Grosso
    Cidade("Tangará da Serra", "MT", -14.6229, -57.4933),
    Cidade("Campo Verde", "MT", -15.5456, -55.1626),
    Cidade("Nova Mutum", "MT", -13.8374, -56.0743),
    Cidade("Querência", "MT", -12.6093, -52.1821),
    Cidade("Barra do Garças", "MT", -15.8900, -52.2567),
    Cidade("Alta Floresta", "MT", -9.8756, -56.0861),
    Cidade("Diamantino", "MT", -14.4086, -56.4461),
    # Mato Grosso do Sul
    Cidade("Três Lagoas", "MS", -20.7849, -51.7007),
    Cidade("Chapadão do Sul", "MS", -18.7908, -52.6260),
    Cidade("Ponta Porã", "MS", -22.5296, -55.7203),
    Cidade("Corumbá", "MS", -19.0077, -57.6510),
    Cidade("São Gabriel do Oeste", "MS", -19.3950, -54.5503),
    # Minas Gerais
    Cidade("Juiz de Fora", "MG", -21.7642, -43.3496),
    Cidade("Montes Claros", "MG", -16.7350, -43.8617),
    Cidade("Patos de Minas", "MG", -18.5789, -46.5181),
    Cidade("Unaí", "MG", -16.3592, -46.9064),
    Cidade("Paracatu", "MG", -17.2252, -46.8711),
    Cidade("Varginha", "MG", -21.5513, -45.4303),
    Cidade("Ipatinga", "MG", -19.4683, -42.5367),
    Cidade("Araguari", "MG", -18.6456, -48.1934),
    Cidade("Patrocínio", "MG", -18.9437, -46.9934),
    # São Paulo
    Cidade("São José do Rio Preto", "SP", -20.8113, -49.3758),
    Cidade("Bauru", "SP", -22.3246, -49.0871),
    Cidade("Presidente Prudente", "SP", -22.1207, -51.3925),
    Cidade("Araçatuba", "SP", -21.2089, -50.4328),
    Cidade("Piracicaba", "SP", -22.7253, -47.6492),
    Cidade("Sorocaba", "SP", -23.5015, -47.4526),
    Cidade("São José dos Campos", "SP", -23.1896, -45.8841),
    Cidade("Franca", "SP", -20.5386, -47.4009),
    Cidade("Barretos", "SP", -20.5531, -48.5698),
    Cidade("Marília", "SP", -22.2139, -49.9458),
    # Paraná
    Cidade("Maringá", "PR", -23.4205, -51.9333),
    Cidade("Foz do Iguaçu", "PR", -25.5163, -54.5854),
    Cidade("Guarapuava", "PR", -25.3935, -51.4562),
    Cidade("Toledo", "PR", -24.7246, -53.7412),
    Cidade("Campo Mourão", "PR", -24.0463, -52.3780),
    # Santa Catarina
    Cidade("Joinville", "SC", -26.3045, -48.8487),
    Cidade("Chapecó", "SC", -27.1004, -52.6152),
    Cidade("Blumenau", "SC", -26.9194, -49.0661),
    Cidade("Lages", "SC", -27.8150, -50.3259),
    Cidade("São Francisco do Sul", "SC", -26.2433, -48.6383),
    # Rio Grande do Sul
    Cidade("Caxias do Sul", "RS", -29.1678, -51.1794),
    Cidade("Passo Fundo", "RS", -28.2620, -52.4064),
    Cidade("Pelotas", "RS", -31.7654, -52.3376),
    Cidade("Santa Maria", "RS", -29.6842, -53.8069),
    Cidade("Cruz Alta", "RS", -28.6386, -53.6064),
    Cidade("Ijuí", "RS", -28.3880, -53.9147),
    # Bahia
    Cidade("Barreiras", "BA", -12.1439, -44.9968),
    Cidade("Feira de Santana", "BA", -12.2664, -38.9663),
    Cidade("Vitória da Conquista", "BA", -14.8615, -40.8442),
    Cidade("Ilhéus", "BA", -14.7936, -39.0463),
    # Norte e Nordeste
    Cidade("Imperatriz", "MA", -5.5185, -47.4777),
    Cidade("Uruçuí", "PI", -7.2294, -44.5561),
    Cidade("Bom Jesus", "PI", -9.0744, -44.3586),
    Cidade("Gurupi", "TO", -11.7279, -49.0686),
    Cidade("Araguaína", "TO", -7.1910, -48.2075),
    Cidade("Porto Nacional", "TO", -10.7081, -48.4172),
    Cidade("Santarém", "PA", -2.4385, -54.6996),
    Cidade("Marabá", "PA", -5.3686, -49.1178),
    Cidade("Paragominas", "PA", -2.9967, -47.3525),
    Cidade("Barcarena", "PA", -1.5059, -48.6258),
    Cidade("Itacoatiara", "AM", -3.1386, -58.4442),
    Cidade("Vilhena", "RO", -12.7406, -60.1458),
    Cidade("Ji-Paraná", "RO", -10.8853, -61.9517),
    Cidade("Petrolina", "PE", -9.3891, -40.5030),
    Cidade("Caruaru", "PE", -8.2760, -35.9819),
    Cidade("Juazeiro do Norte", "CE", -7.2131, -39.3151),
    Cidade("Campina Grande", "PB", -7.2307, -35.8817),
    Cidade("Mossoró", "RN", -5.1878, -37.3441),
    # Sudeste: Espírito Santo e Rio de Janeiro
    Cidade("Linhares", "ES", -19.3946, -40.0643),
    Cidade("Campos dos Goytacazes", "RJ", -21.7545, -41.3244),
    Cidade("Itaguaí", "RJ", -22.8636, -43.7798),
    Cidade("Volta Redonda", "RJ", -22.5231, -44.1042),
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


Ponto = tuple[float, float]  # (latitude, longitude)


def interpolar_rota(origem: Cidade, destino: Cidade, pontos: int = 60) -> list[Ponto]:
    """Rota simulada: `pontos` pontos em linha reta entre as duas cidades (D9).

    A rota por estrada (OSRM) é um extra para depois; a linha reta é honesta
    sobre ser uma simulação.
    """
    passos = max(pontos - 1, 1)
    return [
        (round(origem.lat + (destino.lat - origem.lat) * i / passos, 6),
         round(origem.lon + (destino.lon - origem.lon) * i / passos, 6))
        for i in range(passos + 1)
    ]


def posicao_na_rota(rota: list[Ponto], progresso: float) -> Ponto:
    """Ponto da rota depois de percorrer `progresso` (0 a 1) da distância total."""
    if not rota:
        raise ValueError("Rota vazia")
    progresso = min(max(progresso, 0.0), 1.0)
    trechos = [distancia_linha_reta_km(*rota[i], *rota[i + 1]) for i in range(len(rota) - 1)]
    total = sum(trechos)
    if total == 0 or progresso == 0:
        return rota[0]
    alvo = total * progresso
    percorrido = 0.0
    for i, trecho in enumerate(trechos):
        if percorrido + trecho >= alvo:
            fracao = (alvo - percorrido) / trecho if trecho else 0
            (lat1, lon1), (lat2, lon2) = rota[i], rota[i + 1]
            return (round(lat1 + (lat2 - lat1) * fracao, 6), round(lon1 + (lon2 - lon1) * fracao, 6))
        percorrido += trecho
    return rota[-1]


def cidade_mais_proxima(lat: float, lon: float) -> tuple[Cidade, float]:
    """A cidade da lista mais perto do ponto, e a distância até ela em km."""
    return min(((c, distancia_linha_reta_km(lat, lon, c.lat, c.lon)) for c in _CIDADES), key=lambda par: par[1])


def somar_dias_uteis(inicio: date, dias: int) -> date:
    """Soma dias úteis (segunda a sexta). Feriados não são considerados."""
    atual = inicio
    restantes = dias
    while restantes > 0:
        atual += timedelta(days=1)
        if atual.weekday() < 5:
            restantes -= 1
    return atual


def dias_uteis_entre(inicio: date, fim: date) -> int:
    """Quantos dias úteis depois de `inicio` até `fim` (inclusive). Inverso de somar_dias_uteis."""
    dias, atual = 0, inicio
    while atual < fim:
        atual += timedelta(days=1)
        if atual.weekday() < 5:
            dias += 1
    return dias


def proximo_dia_util(dia: date) -> date:
    return somar_dias_uteis(dia, 1)
