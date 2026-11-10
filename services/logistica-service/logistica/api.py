"""Rotas REST da logística (etapa 1: consulta das solicitações e cotações)."""

from typing import Literal

from fastapi import APIRouter, Depends, Query

from comum.auth import Usuario, exigir_perfis
from comum.db import BancoDeDados, buscar_todos, buscar_um
from comum.erros import Problema
from comum.web import Pagina, paginacao, resposta_paginada

from .servico import linha_para_json

StatusSolicitacao = Literal["ABERTA", "COTADA", "SEM_COTACAO", "SELECIONADA", "INDISPONIVEL", "CANCELADA"]

CAMPOS_SOLICITACAO = """
    id, pedido_id, produto_id, produto_nome, valor_carga, comprador_id, fornecedor_id, tipo_carga, peso_kg,
    origem_cidade, origem_uf, origem_lat, origem_lon, destino_cidade, destino_uf, destino_lat, destino_lon,
    distancia_km, data_coleta_prevista, data_entrega_desejada, aberta_em, rodada_ate, prazo_decisao_em,
    cotacao_escolhida_id, criterio, status
"""


def _filtro_de_visibilidade(usuario: Usuario) -> tuple[str, list]:
    """Comprador vê as suas; fornecedor vê as dos seus pedidos; admin vê todas."""
    if usuario.perfil == "comprador":
        return "comprador_id = %s", [usuario.empresa_id]
    if usuario.perfil == "fornecedor":
        return "fornecedor_id = %s", [usuario.empresa_id]
    return "TRUE", []


def criar_rotas(db: BancoDeDados) -> APIRouter:
    rotas = APIRouter(prefix="/api/v1/logistica", tags=["solicitações de frete"])
    leitores = exigir_perfis("comprador", "fornecedor", "admin")

    @rotas.get("/solicitacoes", summary="Lista as solicitações de frete visíveis para o usuário")
    async def listar_solicitacoes(
        status: StatusSolicitacao | None = Query(None, description="Filtra por status"),
        pagina: Pagina = Depends(paginacao),
        usuario: Usuario = Depends(leitores),
    ):
        condicao, parametros = _filtro_de_visibilidade(usuario)
        if status:
            condicao += " AND status = %s"
            parametros.append(status)
        async with db.transacao() as conn:
            total = (await buscar_um(
                conn, f"SELECT count(*) AS total FROM logistica.solicitacao_frete WHERE {condicao}", parametros
            ))["total"]
            linhas = await buscar_todos(conn, f"""
                SELECT {CAMPOS_SOLICITACAO} FROM logistica.solicitacao_frete WHERE {condicao}
                 ORDER BY aberta_em DESC LIMIT %s OFFSET %s
            """, [*parametros, pagina.size, pagina.offset])
        return resposta_paginada([linha_para_json(l) for l in linhas], pagina, total)

    @rotas.get("/solicitacoes/{solicitacao_id}", summary="Detalhe da solicitação, com as cotações")
    async def obter_solicitacao(solicitacao_id: str, usuario: Usuario = Depends(leitores)):
        condicao, parametros = _filtro_de_visibilidade(usuario)
        async with db.transacao() as conn:
            solicitacao = await buscar_um(conn, f"""
                SELECT {CAMPOS_SOLICITACAO} FROM logistica.solicitacao_frete WHERE id = %s AND {condicao}
            """, [solicitacao_id, *parametros])
            if solicitacao is None:
                raise Problema(404, "SOLICITACAO_NAO_ENCONTRADA", "Solicitação não encontrada",
                               f"Não existe solicitação de frete {solicitacao_id} visível para você.")
            cotacoes = await buscar_todos(conn, """
                SELECT id, transportadora_id, transportadora_nome, preco, prazo_dias, data_entrega_prevista,
                       valida_ate, origem_cotacao, observacoes, status, recebida_em
                  FROM logistica.cotacao WHERE solicitacao_id = %s ORDER BY preco, prazo_dias
            """, (solicitacao_id,))
        resposta = linha_para_json(solicitacao)
        resposta["cotacoes"] = [linha_para_json(c) for c in cotacoes]
        return resposta

    return rotas
