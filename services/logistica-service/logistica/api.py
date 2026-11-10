"""Rotas REST da logística.

- Solicitações e cotações (consulta).
- Escolha do frete pelo comprador ou botão "automático" (D5).
- Notificações do portal (D22).
- Relógio do módulo (D18).
"""

from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, Body, Depends, Header, Query
from fastapi.responses import JSONResponse
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field, model_validator

from comum.auth import Usuario, exigir_perfis, usuario_atual
from comum.db import BancoDeDados, buscar_todos, buscar_um
from comum.erros import Problema
from comum.relogio import calcular_agora
from comum.web import Pagina, paginacao, resposta_paginada

from .servico import AUTOMATICO, ESCOLHA_COMPRADOR, Logistica, agora_real, iso, linha_para_json

StatusSolicitacao = Literal["ABERTA", "COTADA", "SEM_COTACAO", "SELECIONADA", "INDISPONIVEL", "CANCELADA"]

CAMPOS_SOLICITACAO = """
    id, pedido_id, produto_id, produto_nome, valor_carga, comprador_id, fornecedor_id, tipo_carga, peso_kg,
    origem_cidade, origem_uf, origem_lat, origem_lon, destino_cidade, destino_uf, destino_lat, destino_lon,
    distancia_km, data_coleta_prevista, data_entrega_desejada, aberta_em, prazo_decisao_em,
    cotacao_escolhida_id, criterio, escolhida_por, escolhida_em, status
"""


class PedidoDeEscolha(BaseModel):
    """Informe `cotacaoId` (o comprador escolhe) OU `modo: AUTOMATICO` (regra do menor preço)."""

    cotacaoId: str | None = Field(None, description="Cotação escolhida pelo comprador")
    modo: Literal["AUTOMATICO"] | None = Field(None, description="Aplica a regra automática agora")

    @model_validator(mode="after")
    def um_dos_dois(self):
        if (self.cotacaoId is None) == (self.modo is None):
            raise ValueError("Informe cotacaoId ou modo AUTOMATICO (um dos dois, não os dois)")
        return self


class AjusteDoRelogio(BaseModel):
    fator: float = Field(..., gt=0, le=100000, description="1 = tempo real; 360 = 3 dias em 12 minutos")
    avancarHoras: float = Field(0, ge=0, le=24 * 60, description="Adianta o relógio do módulo (opcional)")


class MarcacaoDeLeitura(BaseModel):
    lida: bool = True


def _filtro_de_visibilidade(usuario: Usuario) -> tuple[str, list]:
    """Comprador vê as suas; fornecedor vê as dos seus pedidos; admin vê todas."""
    if usuario.perfil == "comprador":
        return "comprador_id = %s", [usuario.empresa_id]
    if usuario.perfil == "fornecedor":
        return "fornecedor_id = %s", [usuario.empresa_id]
    return "TRUE", []


def _nao_encontrada(solicitacao_id: str) -> Problema:
    return Problema(404, "SOLICITACAO_NAO_ENCONTRADA", "Solicitação não encontrada",
                    f"Não existe solicitação de frete {solicitacao_id} visível para você.")


def criar_rotas(db: BancoDeDados, logistica: Logistica) -> APIRouter:
    rotas = APIRouter(prefix="/api/v1/logistica")
    leitores = exigir_perfis("comprador", "fornecedor", "admin")

    # ------------------------------------------------------------------ solicitações
    @rotas.get("/solicitacoes", tags=["solicitações de frete"],
               summary="Lista as solicitações de frete visíveis para o usuário")
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

    @rotas.get("/solicitacoes/{solicitacao_id}", tags=["solicitações de frete"],
               summary="Detalhe da solicitação, com as cotações")
    async def obter_solicitacao(solicitacao_id: str, usuario: Usuario = Depends(leitores)):
        condicao, parametros = _filtro_de_visibilidade(usuario)
        async with db.transacao() as conn:
            solicitacao = await buscar_um(conn, f"""
                SELECT {CAMPOS_SOLICITACAO} FROM logistica.solicitacao_frete WHERE id = %s AND {condicao}
            """, [solicitacao_id, *parametros])
            if solicitacao is None:
                raise _nao_encontrada(solicitacao_id)
            cotacoes = await buscar_todos(conn, """
                SELECT id, transportadora_id, transportadora_nome, preco, prazo_dias, data_entrega_prevista,
                       valida_ate, origem_cotacao, observacoes, status, recebida_em
                  FROM logistica.cotacao WHERE solicitacao_id = %s ORDER BY preco, prazo_dias
            """, (solicitacao_id,))
        resposta = linha_para_json(solicitacao)
        resposta["cotacoes"] = [linha_para_json(c) for c in cotacoes]
        return resposta

    # ------------------------------------------------------------------ escolha do frete
    @rotas.post(
        "/solicitacoes/{solicitacao_id}/selecionar-frete", tags=["solicitações de frete"],
        summary="O comprador escolhe a cotação, ou pede a escolha automática",
        description=(
            "Corpo `{\"cotacaoId\": \"...\"}` para escolher uma cotação, ou `{\"modo\": \"AUTOMATICO\"}` para "
            "aplicar a regra do menor preço agora. Exige o cabeçalho `Idempotency-Key`: repetir a mesma "
            "requisição com a mesma chave devolve a mesma resposta, sem escolher de novo."
        ),
    )
    async def selecionar_frete(
        solicitacao_id: str,
        corpo: PedidoDeEscolha = Body(...),
        idempotency_key: str | None = Header(None, alias="Idempotency-Key", max_length=100),
        usuario: Usuario = Depends(exigir_perfis("comprador", "admin")),
    ):
        if not idempotency_key:
            raise Problema(400, "IDEMPOTENCY_KEY_AUSENTE", "Cabeçalho obrigatório",
                           "Envie o cabeçalho Idempotency-Key (por exemplo, um UUID gerado pela tela).")
        chave = f"selecionar-frete:{usuario.id}:{idempotency_key}"

        anterior = await _resposta_guardada(db, chave)
        if anterior is not None:
            return anterior

        criterio = ESCOLHA_COMPRADOR if corpo.cotacaoId else AUTOMATICO
        try:
            async with db.transacao() as conn:
                dono = await buscar_um(conn, "SELECT comprador_id FROM logistica.solicitacao_frete WHERE id = %s",
                                       (solicitacao_id,))
                if dono is None or (usuario.perfil == "comprador" and dono["comprador_id"] != usuario.empresa_id):
                    raise _nao_encontrada(solicitacao_id)
                resposta = await logistica.escolher(conn, solicitacao_id, corpo.cotacaoId, criterio,
                                                    escolhida_por=usuario.id)
                await conn.execute(
                    "INSERT INTO logistica.idempotency_keys (key, response_payload) VALUES (%s, %s)",
                    (chave, Jsonb(resposta)))
            return resposta
        except Problema:
            # Duas requisições iguais ao mesmo tempo: a segunda espera a primeira e
            # recebe 409; se a primeira gravou a resposta, devolve a mesma resposta.
            anterior = await _resposta_guardada(db, chave)
            if anterior is not None:
                return anterior
            raise

    # ------------------------------------------------------------------ notificações
    @rotas.get("/notificacoes", tags=["notificações"], summary="Notificações da empresa do usuário")
    async def listar_notificacoes(
        lida: bool | None = Query(None, description="true = só lidas; false = só não lidas"),
        pagina: Pagina = Depends(paginacao),
        usuario: Usuario = Depends(exigir_perfis("comprador", "fornecedor")),
    ):
        condicao, parametros = "empresa_id = %s AND papel = %s", [usuario.empresa_id, usuario.perfil]
        async with db.transacao() as conn:
            nao_lidas = (await buscar_um(
                conn, f"SELECT count(*) AS n FROM logistica.notificacao WHERE {condicao} AND NOT lida", parametros
            ))["n"]
            if lida is not None:
                condicao += " AND lida = %s"
                parametros.append(lida)
            total = (await buscar_um(
                conn, f"SELECT count(*) AS n FROM logistica.notificacao WHERE {condicao}", parametros))["n"]
            linhas = await buscar_todos(conn, f"""
                SELECT id, tipo, titulo, mensagem, pedido_id, solicitacao_id, lida, criada_em
                  FROM logistica.notificacao WHERE {condicao}
                 ORDER BY criada_em DESC, criado_em_real DESC LIMIT %s OFFSET %s
            """, [*parametros, pagina.size, pagina.offset])
        return {**resposta_paginada([linha_para_json(l) for l in linhas], pagina, total), "naoLidas": nao_lidas}

    @rotas.patch("/notificacoes/{notificacao_id}", tags=["notificações"], summary="Marca como lida ou não lida")
    async def marcar_notificacao(notificacao_id: str, corpo: MarcacaoDeLeitura,
                                 usuario: Usuario = Depends(exigir_perfis("comprador", "fornecedor"))):
        async with db.transacao() as conn:
            linha = await buscar_um(conn, """
                UPDATE logistica.notificacao SET lida = %s
                 WHERE id = %s AND empresa_id = %s AND papel = %s
                RETURNING id, tipo, titulo, mensagem, pedido_id, solicitacao_id, lida, criada_em
            """, (corpo.lida, notificacao_id, usuario.empresa_id, usuario.perfil))
        if linha is None:
            raise Problema(404, "NOTIFICACAO_NAO_ENCONTRADA", "Notificação não encontrada",
                           f"Não existe notificação {notificacao_id} para você.")
        return linha_para_json(linha)

    # ------------------------------------------------------------------ relógio do módulo
    @rotas.get("/relogio", tags=["relógio do módulo"], summary="Hora do módulo e velocidade atual")
    async def ver_relogio(_: Usuario = Depends(usuario_atual)):
        estado = await logistica.relogio.estado()
        real = agora_real()
        return {"horaDoModulo": iso(calcular_agora(estado, real)), "horaReal": iso(real),
                "fator": estado.fator if estado else 1.0, "versao": estado.versao if estado else 0}

    @rotas.post("/admin/relogio", tags=["relógio do módulo"],
                summary="Acelera, desacelera ou adianta o relógio do módulo (só administrador)")
    async def ajustar_relogio(corpo: AjusteDoRelogio, usuario: Usuario = Depends(exigir_perfis("admin"))):
        async with db.transacao() as conn:
            novo = await logistica.ajustar_relogio(conn, corpo.fator, timedelta(hours=corpo.avancarHoras), usuario.id)
        logistica.relogio.invalidar()
        return {"horaDoModulo": iso(novo.base_virtual), "horaReal": iso(novo.base_real),
                "fator": novo.fator, "versao": novo.versao}

    return rotas


async def _resposta_guardada(db: BancoDeDados, chave: str) -> JSONResponse | None:
    async with db.transacao() as conn:
        linha = await buscar_um(conn, "SELECT response_payload FROM logistica.idempotency_keys WHERE key = %s",
                                (chave,))
    if linha is None:
        return None
    return JSONResponse(linha["response_payload"], headers={"X-Idempotent-Replay": "true"})
