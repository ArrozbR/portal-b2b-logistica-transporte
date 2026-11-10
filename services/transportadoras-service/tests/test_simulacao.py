from datetime import date, datetime, timedelta, timezone

import pytest

from comum.formatos import BRASILIA
from comum.geo import buscar_cidade, interpolar_rota
from transportadoras.simulacao import (EstadoViagem, cnh_permite, embaralhar, mascarar_cnh, passo, planejar,
                                       progresso, resultado_no_prazo)

AGORA = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)  # terça, 09:00 em Brasília
ROTA = interpolar_rota(buscar_cidade("Sorriso", "MT"), buscar_cidade("Santos", "SP"))
PROMETIDA = date(2026, 11, 16)  # segunda


def estado(**mudancas) -> EstadoViagem:
    base = dict(status="EM_TRANSITO", rota=ROTA, coleta_em=AGORA, chegada_prevista=AGORA + timedelta(hours=100),
                atraso_horas=0.0, atraso_revelado=False, parada_publicada=False, marco_tempo=AGORA,
                marco_progresso=0.0, progresso=0.0, data_prometida=PROMETIDA)
    base.update(mudancas)
    return EstadoViagem(**base)


# ------------------------------------------------------------------ plano

def test_plano_e_reproduzivel_pela_semente():
    assert planejar("ent-1", AGORA, 2091, 750, 0.5, PROMETIDA) == planejar("ent-1", AGORA, 2091, 750, 0.5, PROMETIDA)


def test_chegada_planejada_as_14h_da_data_prometida():
    plano = planejar("ent-1", AGORA, 2091, 750, 0.0, PROMETIDA)
    assert plano.coleta_em == AGORA + timedelta(hours=2)
    assert plano.chegada_planejada == datetime(2026, 11, 16, 14, 0, tzinfo=BRASILIA)
    assert plano.atraso_horas == 0


def test_chegada_nunca_antes_do_tempo_minimo_de_estrada():
    # prometeu para amanhã, mas 2.091 km a 400 km/dia levam mais de 5 dias
    plano = planejar("ent-1", AGORA, 2091, 400, 0.0, date(2026, 11, 11))
    assert plano.chegada_planejada == plano.coleta_em + timedelta(hours=2091 / (400 / 24))


def test_transportadora_que_sempre_atrasa_sorteia_atraso():
    assert planejar("ent-1", AGORA, 2091, 750, 1.0, PROMETIDA).atraso_horas >= 4


# ------------------------------------------------------------------ progresso e prazo

def test_progresso_parte_do_marco_e_nunca_passa_de_1():
    chegada = AGORA + timedelta(hours=10)
    assert progresso(AGORA, 0.0, chegada, AGORA - timedelta(hours=1)) == 0.0
    assert progresso(AGORA, 0.0, chegada, AGORA + timedelta(hours=5)) == 0.5
    assert progresso(AGORA, 0.6, chegada, AGORA + timedelta(hours=5)) == 0.8
    assert progresso(AGORA, 0.0, chegada, chegada + timedelta(days=3)) == 1.0


def test_prazo_vai_ate_o_fim_do_dia_prometido_em_brasilia():
    assert resultado_no_prazo(datetime(2026, 11, 16, 23, 59, tzinfo=BRASILIA), PROMETIDA) == (True, 0.0)
    assert resultado_no_prazo(datetime(2026, 11, 17, 6, 0, tzinfo=BRASILIA), PROMETIDA) == (False, 6.0)


# ------------------------------------------------------------------ passo da viagem

def test_antes_da_coleta_nada_acontece():
    agendada = estado(status="AGENDADA", coleta_em=AGORA + timedelta(hours=2))
    assert passo(agendada, AGORA) == (agendada, [])


def test_coleta_coloca_a_viagem_em_transito():
    novo, eventos = passo(estado(status="AGENDADA", coleta_em=AGORA), AGORA + timedelta(minutes=5))
    assert novo.status == "EM_TRANSITO"
    assert [e.tipo for e in eventos] == ["COLETA_REALIZADA"]
    assert "Sorriso - MT" in eventos[0].descricao


def test_posicao_no_meio_da_viagem():
    novo, eventos = passo(estado(), AGORA + timedelta(hours=20))
    assert [e.tipo for e in eventos] == ["POSICAO"]
    assert eventos[0].progresso == pytest.approx(0.2)
    assert novo.progresso == pytest.approx(0.2)


def test_parada_e_publicada_uma_vez_so():
    novo, eventos = passo(estado(), AGORA + timedelta(hours=50))
    assert [e.tipo for e in eventos] == ["PARADA", "POSICAO"]
    _, de_novo = passo(novo, AGORA + timedelta(hours=55))
    assert [e.tipo for e in de_novo] == ["POSICAO"]


def test_atraso_aparece_aos_60_por_cento_e_o_caminhao_nao_volta():
    com_atraso = estado(atraso_horas=20.0, parada_publicada=True)
    antes, _ = passo(com_atraso, AGORA + timedelta(hours=59))
    depois, eventos = passo(antes, AGORA + timedelta(hours=61))
    assert [e.tipo for e in eventos] == ["PREVISAO_ATUALIZADA", "POSICAO"]
    assert depois.chegada_prevista == AGORA + timedelta(hours=120)
    assert eventos[0].extras["previsaoAnterior"] == AGORA + timedelta(hours=100)
    assert depois.progresso >= antes.progresso  # nunca volta no mapa


def test_relogio_muito_acelerado_publica_tudo_em_ordem():
    # um único passo que pula da saída até depois da chegada
    novo, eventos = passo(estado(atraso_horas=30.0), AGORA + timedelta(days=30))
    assert [e.tipo for e in eventos] == ["PARADA", "PREVISAO_ATUALIZADA", "ENTREGA_REALIZADA"]
    horarios = [e.ocorrido_em for e in eventos]
    assert horarios == sorted(horarios)
    assert novo.status == "ENTREGUE"


def test_entrega_atrasada_alem_do_dia_prometido():
    # chega às 14h do dia 16 + 30 h de atraso = dia 17, 20h (Brasília): 20 h depois da meia-noite
    planejada = datetime(2026, 11, 16, 14, 0, tzinfo=BRASILIA)
    _, eventos = passo(estado(chegada_prevista=planejada, atraso_horas=30.0), AGORA + timedelta(days=30))
    entrega = eventos[-1]
    assert entrega.extras == {"noPrazo": False, "atrasoHoras": 20.0}


def test_entrega_no_prazo():
    planejada = datetime(2026, 11, 16, 14, 0, tzinfo=BRASILIA)
    _, eventos = passo(estado(chegada_prevista=planejada, parada_publicada=True), AGORA + timedelta(days=30))
    assert eventos[-1].extras == {"noPrazo": True, "atrasoHoras": 0.0}


# ------------------------------------------------------------------ motorista e veículo

def test_cnh_mascarada_mostra_so_os_ultimos_4_digitos():
    assert mascarar_cnh("03345678910") == "*******8910"


def test_categoria_da_cnh():
    assert cnh_permite("E", "C") and cnh_permite("E", "E")
    assert not cnh_permite("C", "E")


def test_sorteio_reproduzivel():
    itens = ["a", "b", "c", "d", "e"]
    assert embaralhar("ent-1", itens) == embaralhar("ent-1", itens)
    assert sorted(embaralhar("ent-1", itens)) == itens
