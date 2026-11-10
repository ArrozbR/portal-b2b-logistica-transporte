from datetime import date

import pytest

from comum.geo import (buscar_cidade, distancia_estrada_km, distancia_linha_reta_km, proximo_dia_util,
                       somar_dias_uteis)


def test_sorriso_santos_linha_reta_e_estrada():
    sorriso, santos = buscar_cidade("Sorriso", "MT"), buscar_cidade("Santos", "SP")
    reta = distancia_linha_reta_km(sorriso.lat, sorriso.lon, santos.lat, santos.lon)
    assert reta == pytest.approx(1609, abs=5)
    assert distancia_estrada_km(sorriso, santos) == pytest.approx(2091, abs=7)


def test_busca_de_cidade_ignora_acento_e_maiusculas():
    assert buscar_cidade("SAO PAULO", "sp").nome == "São Paulo"
    assert buscar_cidade("  luis   eduardo magalhaes ", "BA").uf == "BA"


def test_cidade_desconhecida_ou_uf_errada():
    assert buscar_cidade("Atlântida", "SP") is None
    assert buscar_cidade("Santos", "MT") is None


def test_dias_uteis_pulam_fim_de_semana():
    sexta = date(2026, 11, 13)
    assert somar_dias_uteis(sexta, 1) == date(2026, 11, 16)  # segunda
    assert somar_dias_uteis(sexta, 5) == date(2026, 11, 20)
    assert proximo_dia_util(date(2026, 11, 14)) == date(2026, 11, 16)  # sábado → segunda
