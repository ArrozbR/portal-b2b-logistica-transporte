from decimal import Decimal

from transportadoras.cotacao import PerfilTransportadora, RegraCotacao, atende, calcular
from transportadoras.servico import id_da_cotacao

# Mesmos parâmetros do seed de desenvolvimento (900_seed_desenvolvimento.sql)
EXPRESSA = RegraCotacao(Decimal("1500"), Decimal("3.80"), Decimal("45"), 750, 1, {"GRANEL": Decimal("1.00")})
ECONOMICA = RegraCotacao(Decimal("900"), Decimal("2.60"), Decimal("30"), 400, 2, {"GRANEL": Decimal("1.00")})
GRANELEIRA = RegraCotacao(Decimal("1100"), Decimal("3.00"), Decimal("35"), 550, 1, {"GRANEL": Decimal("1.00")})
FRIO = RegraCotacao(Decimal("2000"), Decimal("4.50"), Decimal("60"), 600, 1, {"REFRIGERADO": Decimal("1.35")})


def test_sorriso_santos_24_toneladas_de_soja():
    # 2.091 km, 24 t, granel: perfis diferentes geram escolhas diferentes
    assert calcular(EXPRESSA, 2091, 24000, "GRANEL") == (Decimal("9025.80"), 4)
    assert calcular(ECONOMICA, 2091, 24000, "GRANEL") == (Decimal("6156.60"), 8)
    assert calcular(GRANELEIRA, 2091, 24000, "GRANEL") == (Decimal("7113.00"), 5)


def test_carga_refrigerada_custa_mais():
    preco, prazo = calcular(FRIO, 1000, 10000, "REFRIGERADO")
    assert preco == Decimal("6885.00")  # (4.50×1000 + 60×10) × 1,35
    assert prazo == 3


def test_preco_minimo_em_viagem_curta():
    assert calcular(EXPRESSA, 50, 1000, "GRANEL")[0] == Decimal("1500.00")


def test_compatibilidade_por_tipo_de_carga_e_estado():
    graneleira = PerfilTransportadora("g", "Graneleira", ("GRANEL",), ("MT", "GO", "MS", "SP", "PR"))
    nacional = PerfilTransportadora("n", "Nacional", ("GRANEL", "CARGA_SECA"), None)

    assert atende(graneleira, "GRANEL", "MT", "SP")
    assert not atende(graneleira, "GRANEL", "MT", "BA")       # Bahia fora da área
    assert not atende(graneleira, "REFRIGERADO", "MT", "SP")  # não leva refrigerado
    assert atende(nacional, "CARGA_SECA", "RS", "MA")


def test_id_da_cotacao_e_sempre_o_mesmo():
    # reprocessar a mesma solicitação gera o mesmo cotacaoId (ajuda na idempotência)
    assert id_da_cotacao("sol-1", "transp-a") == id_da_cotacao("sol-1", "transp-a")
    assert id_da_cotacao("sol-1", "transp-a") != id_da_cotacao("sol-1", "transp-b")
