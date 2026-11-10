from datetime import datetime, timedelta, timezone

from comum.relogio import EstadoRelogio, calcular_agora, reajustar

T0 = datetime(2026, 11, 9, 21, 0, tzinfo=timezone.utc)


def test_sem_estado_o_relogio_e_a_hora_real():
    assert calcular_agora(None, T0) == T0


def test_fator_360_faz_3_dias_passarem_em_12_minutos():
    estado = EstadoRelogio(base_real=T0, base_virtual=T0, fator=360, versao=1)
    assert calcular_agora(estado, T0 + timedelta(minutes=12)) == T0 + timedelta(days=3)


def test_mudar_o_fator_nao_faz_o_relogio_saltar():
    rapido = EstadoRelogio(base_real=T0, base_virtual=T0, fator=360, versao=1)
    depois = T0 + timedelta(minutes=1)
    hora_do_modulo = calcular_agora(rapido, depois)

    normal = reajustar(rapido, depois, novo_fator=1)
    assert calcular_agora(normal, depois) == hora_do_modulo
    assert calcular_agora(normal, depois + timedelta(minutes=1)) == hora_do_modulo + timedelta(minutes=1)
    assert normal.versao == 2


def test_avancar_o_relogio():
    estado = reajustar(None, T0, novo_fator=1, avancar=timedelta(days=1))
    assert calcular_agora(estado, T0) == T0 + timedelta(days=1)
