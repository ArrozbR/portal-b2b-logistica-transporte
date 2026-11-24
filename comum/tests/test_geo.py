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


def test_rota_interpolada_e_posicao_na_rota():
    from comum.geo import cidade_mais_proxima, interpolar_rota, posicao_na_rota

    sorriso, santos = buscar_cidade("Sorriso", "MT"), buscar_cidade("Santos", "SP")
    rota = interpolar_rota(sorriso, santos, pontos=60)
    assert len(rota) == 60
    assert rota[0] == (sorriso.lat, sorriso.lon) and rota[-1] == (santos.lat, santos.lon)
    assert posicao_na_rota(rota, 0) == rota[0]
    assert posicao_na_rota(rota, 1) == rota[-1]
    meio = posicao_na_rota(rota, 0.5)
    assert meio[0] == pytest.approx((sorriso.lat + santos.lat) / 2, abs=0.05)
    cidade, distancia = cidade_mais_proxima(-20.47, -54.62)
    assert cidade.nome == "Campo Grande" and distancia < 1


def test_dias_uteis_pulam_fim_de_semana():
    sexta = date(2026, 11, 13)
    assert somar_dias_uteis(sexta, 1) == date(2026, 11, 16)  # segunda
    assert somar_dias_uteis(sexta, 5) == date(2026, 11, 20)
    assert proximo_dia_util(date(2026, 11, 14)) == date(2026, 11, 16)  # sábado → segunda


def test_rota_da_viagem_segue_as_estradas():
    from comum.geo import Cidade, comprimento_km, rota_da_viagem
    sorriso, santos = buscar_cidade("Sorriso", "MT"), buscar_cidade("Santos", "SP")
    rota = rota_da_viagem(sorriso, santos)
    assert rota[0] == (sorriso.lat, sorriso.lon) and rota[-1] == (santos.lat, santos.lon)
    assert len(rota) > 60  # mais pontos que a linha reta: segue as curvas da estrada
    assert comprimento_km(rota) == pytest.approx(distancia_estrada_km(sorriso, santos), rel=0.1)
    # O nome do evento pode vir em outra grafia; a rota é a mesma.
    assert rota_da_viagem(Cidade("SORRISO", "MT", sorriso.lat, sorriso.lon), santos) == rota


def test_travessia_de_balsa_vira_linha_reta():
    from comum.geo import interpolar_rota, rota_da_viagem
    macapa, belem = buscar_cidade("Macapá", "AP"), buscar_cidade("Belém", "PA")
    assert rota_da_viagem(macapa, belem) == interpolar_rota(macapa, belem)
