"""Simulação da viagem do caminhão (decisões D8, D9 e D10).

Não há GPS real: a posição é calculada pelo relógio do módulo (D18). Por isso,
acelerar o relógio acelera a viagem sem mudar nada aqui.

Plano de uma viagem:

- coleta: algumas horas depois da escolha do frete;
- chegada planejada: às 14h da data prometida na cotação (a transportadora
  planeja chegar no dia que prometeu), mas nunca antes do tempo mínimo de
  estrada (distância ÷ km rodados por dia);
- atraso: sorteado uma vez, com a probabilidade de atraso da transportadora
  (é isso que separa uma transportadora pontual de uma que atrasa e alimenta o
  ranking). O atraso só "aparece" quando o caminhão passa de 60% do caminho,
  como na vida real.

O sorteio usa uma semente fixa (o id da entrega): a mesma entrega gera sempre
a mesma viagem, o que torna os testes estáveis.

Este módulo não acessa banco nem Kafka.
"""

import random
from dataclasses import dataclass, field, replace
from datetime import date, datetime, time, timedelta

from comum.formatos import BRASILIA, data_hora
from comum.geo import Ponto, cidade_mais_proxima, posicao_na_rota

ANTECEDENCIA_COLETA = timedelta(hours=2)
HORA_CHEGADA_PLANEJADA = time(14, 0)
PROGRESSO_DA_PARADA = 0.45
PROGRESSO_QUE_REVELA_ATRASO = 0.60
ATRASO_MINIMO_H, ATRASO_MAXIMO_H = 4.0, 36.0


@dataclass(frozen=True)
class PlanoViagem:
    coleta_em: datetime
    chegada_planejada: datetime
    atraso_horas: float  # 0 = sem atraso


def planejar(semente: str, agora: datetime, distancia_km: float, km_por_dia: int,
             prob_atraso: float, data_prometida: date | None) -> PlanoViagem:
    sorteio = random.Random(semente)
    coleta = agora + ANTECEDENCIA_COLETA
    minimo_de_estrada = coleta + timedelta(hours=distancia_km / (km_por_dia / 24))
    chegada = minimo_de_estrada
    if data_prometida is not None:
        planejada = datetime.combine(data_prometida, HORA_CHEGADA_PLANEJADA, tzinfo=BRASILIA)
        chegada = max(planejada, minimo_de_estrada)
    atraso = 0.0
    if sorteio.random() < prob_atraso:
        atraso = round(sorteio.uniform(ATRASO_MINIMO_H, ATRASO_MAXIMO_H), 1)
    return PlanoViagem(coleta_em=coleta, chegada_planejada=chegada, atraso_horas=atraso)


def progresso(marco_tempo: datetime, marco_progresso: float, chegada: datetime, agora: datetime) -> float:
    """Fração do caminho percorrida (0 a 1).

    Anda em linha reta do último "marco" (a coleta, ou o momento em que o
    atraso apareceu) até a chegada. Começar do marco garante que o caminhão
    nunca volta para trás no mapa quando a previsão de chegada muda.
    """
    if agora <= marco_tempo:
        return marco_progresso
    if agora >= chegada:
        return 1.0
    fracao = (agora - marco_tempo) / (chegada - marco_tempo)
    return round(marco_progresso + (1 - marco_progresso) * fracao, 4)


def resultado_no_prazo(entregue_em: datetime, data_prometida: date | None) -> tuple[bool, float]:
    """(entregou no prazo?, horas de atraso). O prazo vai até 23:59 da data prometida, no horário de Brasília."""
    if data_prometida is None:
        return True, 0.0
    limite = datetime.combine(data_prometida + timedelta(days=1), time(0, 0), tzinfo=BRASILIA)
    if entregue_em <= limite:
        return True, 0.0
    return False, round((entregue_em - limite).total_seconds() / 3600, 1)


def mascarar_cnh(numero: str) -> str:
    """Mostra só os 4 últimos dígitos da CNH (LGPD, D19): '12345678910' → '*******8910'."""
    digitos = "".join(c for c in numero if c.isdigit())
    return "*" * max(len(digitos) - 4, 0) + digitos[-4:]


ORDEM_CNH = "ABCDE"


def cnh_permite(categoria_motorista: str, categoria_exigida: str) -> bool:
    """Categoria C dirige caminhão; E dirige carreta. Uma categoria maior cobre as menores (exceto A)."""
    return ORDEM_CNH.index(categoria_motorista) >= ORDEM_CNH.index(categoria_exigida)


def embaralhar(semente: str, opcoes: list) -> list:
    """Sorteio reproduzível: a mesma semente gera sempre a mesma ordem.

    A escala tenta os itens nessa ordem; o primeiro que conseguir reservar é o sorteado.
    """
    return random.Random(semente).sample(opcoes, len(opcoes))


# --------------------------------------------------------------------------- passo da viagem

@dataclass(frozen=True)
class EstadoViagem:
    status: str                 # AGENDADA, EM_TRANSITO, ENTREGUE, CANCELADA
    rota: list[Ponto]
    coleta_em: datetime
    chegada_prevista: datetime
    atraso_horas: float
    atraso_revelado: bool
    parada_publicada: bool
    marco_tempo: datetime
    marco_progresso: float
    progresso: float
    data_prometida: date | None


@dataclass(frozen=True)
class EventoViagem:
    tipo: str
    descricao: str
    ocorrido_em: datetime
    posicao: Ponto
    progresso: float
    previsao: datetime
    extras: dict = field(default_factory=dict)


def instante_do_progresso(marco_tempo: datetime, marco_progresso: float, chegada: datetime, alvo: float) -> datetime:
    """Inverso de `progresso`: em que momento o caminhão atinge a fração `alvo` do caminho."""
    if alvo <= marco_progresso:
        return marco_tempo
    return marco_tempo + (chegada - marco_tempo) * ((alvo - marco_progresso) / (1 - marco_progresso))


def _local(ponto: Ponto) -> str:
    cidade, distancia = cidade_mais_proxima(*ponto)
    return f"{cidade.nome} - {cidade.uf}" if distancia <= 150 else "na rodovia"


def passo(estado: EstadoViagem, agora: datetime) -> tuple[EstadoViagem, list[EventoViagem]]:
    """Avança a viagem até `agora` (hora do módulo) e devolve o novo estado e os eventos a publicar.

    Os eventos saem em ordem cronológica. Se o relógio estiver muito acelerado e
    o caminhão "pular" a parada ou o ponto em que o atraso aparece, eles são
    publicados mesmo assim, com o horário em que teriam acontecido.
    """
    if estado.status == "AGENDADA":
        if agora < estado.coleta_em:
            return estado, []
        origem = estado.rota[0]
        coleta = EventoViagem("COLETA_REALIZADA", f"Carga coletada em {_local(origem)}.", estado.coleta_em,
                              origem, 0.0, estado.chegada_prevista)
        return replace(estado, status="EM_TRANSITO", marco_tempo=estado.coleta_em, marco_progresso=0.0,
                       progresso=0.0), [coleta]

    if estado.status != "EM_TRANSITO":
        return estado, []

    eventos: list[EventoViagem] = []
    e = estado
    p = progresso(e.marco_tempo, e.marco_progresso, e.chegada_prevista, agora)

    if not e.parada_publicada and p >= PROGRESSO_DA_PARADA:
        quando = instante_do_progresso(e.marco_tempo, e.marco_progresso, e.chegada_prevista, PROGRESSO_DA_PARADA)
        onde = posicao_na_rota(e.rota, PROGRESSO_DA_PARADA)
        local = _local(onde)
        texto = f"Parada para descanso do motorista em {local}." if local != "na rodovia" \
            else "Parada para descanso do motorista na rodovia."
        eventos.append(EventoViagem("PARADA", texto, quando, onde, PROGRESSO_DA_PARADA, e.chegada_prevista,
                                    {"local": local, "duracaoPrevistaMin": 480}))
        e = replace(e, parada_publicada=True)

    if e.atraso_horas > 0 and not e.atraso_revelado and p >= PROGRESSO_QUE_REVELA_ATRASO:
        p_marco = min(p, 0.95)
        t_marco = instante_do_progresso(e.marco_tempo, e.marco_progresso, e.chegada_prevista, p_marco)
        anterior = e.chegada_prevista
        nova = anterior + timedelta(hours=e.atraso_horas)
        e = replace(e, chegada_prevista=nova, marco_tempo=t_marco, marco_progresso=p_marco, atraso_revelado=True)
        eventos.append(EventoViagem("PREVISAO_ATUALIZADA", f"Previsão de chegada ajustada para {data_hora(nova)}.",
                                    t_marco, posicao_na_rota(e.rota, p_marco), p_marco, nova,
                                    {"previsaoAnterior": anterior}))
        p = progresso(e.marco_tempo, e.marco_progresso, e.chegada_prevista, agora)

    if p >= 1:
        destino = e.rota[-1]
        no_prazo, atraso = resultado_no_prazo(e.chegada_prevista, e.data_prometida)
        eventos.append(EventoViagem("ENTREGA_REALIZADA", f"Entrega realizada em {_local(destino)}.",
                                    e.chegada_prevista, destino, 1.0, e.chegada_prevista,
                                    {"noPrazo": no_prazo, "atrasoHoras": atraso}))
        return replace(e, status="ENTREGUE", progresso=1.0), eventos

    eventos.append(EventoViagem("POSICAO", "Veículo em deslocamento conforme rota planejada.", agora,
                                posicao_na_rota(e.rota, p), p, e.chegada_prevista))
    return replace(e, progresso=p), eventos
