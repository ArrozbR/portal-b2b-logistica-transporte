"""Rotas REST das transportadoras (etapa 1: consulta do cadastro)."""

from fastapi import APIRouter, Depends

from comum.auth import Usuario, exigir_perfis
from comum.db import BancoDeDados, buscar_todos, buscar_um
from comum.erros import Problema
from comum.web import Pagina, paginacao, resposta_paginada

from .servico import linha_para_json

CAMPOS = """
    t.id, t.nome, t.telefone_contato, t.ativa, t.simulada, t.tipos_carga, t.ufs_atendidas,
    r.preco_minimo, r.tarifa_km, r.tarifa_ton, r.km_por_dia, r.prazo_base_dias
"""


def criar_rotas(db: BancoDeDados) -> APIRouter:
    rotas = APIRouter(prefix="/api/v1/transportadoras", tags=["transportadoras"])
    todos = exigir_perfis("comprador", "fornecedor", "transportadora", "admin")

    @rotas.get("", summary="Lista as transportadoras homologadas")
    async def listar(pagina: Pagina = Depends(paginacao), _: Usuario = Depends(todos)):
        async with db.transacao() as conn:
            total = (await buscar_um(conn, "SELECT count(*) AS total FROM transportadoras.transportadora"))["total"]
            linhas = await buscar_todos(conn, f"""
                SELECT {CAMPOS} FROM transportadoras.transportadora t
                  LEFT JOIN transportadoras.regra_cotacao r ON r.transportadora_id = t.id
                 ORDER BY t.nome LIMIT %s OFFSET %s
            """, (pagina.size, pagina.offset))
        return resposta_paginada([linha_para_json(l) for l in linhas], pagina, total)

    @rotas.get("/{transportadora_id}", summary="Detalhe de uma transportadora")
    async def obter(transportadora_id: str, _: Usuario = Depends(todos)):
        async with db.transacao() as conn:
            linha = await buscar_um(conn, f"""
                SELECT {CAMPOS} FROM transportadoras.transportadora t
                  LEFT JOIN transportadoras.regra_cotacao r ON r.transportadora_id = t.id
                 WHERE t.id = %s
            """, (transportadora_id,))
        if linha is None:
            raise Problema(404, "TRANSPORTADORA_NAO_ENCONTRADA", "Transportadora não encontrada",
                           f"Não existe transportadora {transportadora_id}.")
        return linha_para_json(linha)

    return rotas
