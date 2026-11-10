from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from logistica.documentos import DocumentoIndisponivel, TIPOS, gerar, numero_do_documento
from logistica.regras import (MAIS_BARATA, MAIS_PONTUAL, MAIS_RAPIDA, RECOMENDADA, CotacaoCandidata,
                              preco_por_tonelada_km, selos)


def cot(id_, transportadora, preco, prazo):
    return CotacaoCandidata(id_, transportadora, Decimal(str(preco)), prazo)


# ------------------------------------------------------------------ selos da comparação

def test_selos_sorriso_santos():
    cotacoes = [cot("eco", "economica", 6156.86, 8), cot("gra", "graneleira", 7113.30, 5),
                cot("exp", "expressa", 9026.18, 4)]
    resultado = selos(cotacoes)
    assert resultado["eco"] == [MAIS_BARATA, RECOMENDADA]
    assert resultado["exp"] == [MAIS_RAPIDA]
    assert resultado["gra"] == []


def test_mais_pontual_so_aparece_com_historico():
    cotacoes = [cot("a", "ta", 5000, 5), cot("b", "tb", 6000, 4)]
    assert MAIS_PONTUAL not in sum(selos(cotacoes).values(), [])
    assert selos(cotacoes, {"ta": 0.6, "tb": 0.9})["b"] == [MAIS_RAPIDA, MAIS_PONTUAL]


def test_empate_ganha_o_selo_junto():
    resultado = selos([cot("a", "ta", 5000, 4), cot("b", "tb", 5000, 4)])
    assert MAIS_BARATA in resultado["a"] and MAIS_BARATA in resultado["b"]
    assert MAIS_RAPIDA in resultado["a"] and MAIS_RAPIDA in resultado["b"]
    assert [RECOMENDADA in resultado[i] for i in ("a", "b")] == [True, False]  # desempate pelo id


def test_sem_cotacao_sem_selos():
    assert selos([]) == {}


def test_preco_por_tonelada_km():
    assert preco_por_tonelada_km(Decimal("6156.86"), 24000, 2091.1) == Decimal("0.1227")
    assert preco_por_tonelada_km(Decimal("100"), 0, 100) is None


# ------------------------------------------------------------------ documentos demonstrativos (D21)

ENTREGA = dict(
    id="ent-1", pedido_id="PED-1", produto_nome="Soja em grão", tipo_carga="GRANEL", peso_kg=Decimal("24000"),
    valor_carga=Decimal("192000"), comprador_id="emp-c", fornecedor_id="emp-f", origem_cidade="Sorriso",
    origem_uf="MT", destino_cidade="Santos", destino_uf="SP", distancia_km=Decimal("2091.1"),
    transportadora_id="transp-x", transportadora_nome="Expressa — Cargas", transportadora_telefone=None,
    motorista_nome="Carlos Mendes", motorista_cnh_mascarada="*******8910", veiculo_placa="ABC1D23",
    veiculo_tipo="CARRETA_GRANELEIRA", coleta_prevista=datetime(2026, 11, 24, 3, 0, tzinfo=timezone.utc),
    coletada_em=None, prazo_prometido=date(2026, 12, 1), preco_frete=Decimal("9026.18"), prazo_dias=4,
)
AGORA = datetime(2026, 11, 25, 12, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize("tipo", ["cte", "romaneio", "nota-fiscal"])
def test_documentos_sao_pdf(tipo):
    pdf = gerar(tipo, ENTREGA, AGORA)
    assert pdf.startswith(b"%PDF-") and len(pdf) > 1000


def test_comprovante_de_coleta_so_depois_da_coleta():
    with pytest.raises(DocumentoIndisponivel):
        gerar("comprovante-coleta", ENTREGA, AGORA)
    coletada = {**ENTREGA, "coletada_em": datetime(2026, 11, 24, 5, 0, tzinfo=timezone.utc)}
    assert gerar("comprovante-coleta", coletada, AGORA).startswith(b"%PDF-")


def test_tipo_desconhecido():
    with pytest.raises(KeyError):
        gerar("boleto", ENTREGA, AGORA)


def test_numero_do_documento_e_estavel_e_diferente_por_tipo():
    assert numero_do_documento("ent-1", "cte") == numero_do_documento("ent-1", "cte")
    assert len({numero_do_documento("ent-1", t) for t in TIPOS}) == len(TIPOS)
