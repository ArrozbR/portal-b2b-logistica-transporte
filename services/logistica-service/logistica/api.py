"""Rotas REST da logística.

- Solicitações, cotações e comparação (D6).
- Escolha do frete pelo comprador ou botão "automático" (D5).
- Entregas, rastreio, documentos demonstrativos (D21) e ocorrências.
- Notificações do portal (D22).
- Relógio do módulo (D18).
"""

import uuid
from datetime import timedelta
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Body, Depends, Header, Query, Response
from fastapi.responses import JSONResponse
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field, StringConstraints, model_validator

from comum.auth import Usuario, exigir_perfis, usuario_atual
from comum.db import BancoDeDados, buscar_todos, buscar_um
from comum.erros import Problema
from comum.relogio import calcular_agora
from comum.web import Pagina, paginacao, resposta_paginada

from .documentos import DocumentoIndisponivel
from .documentos import gerar as gerar_documento
from .notificacoes import notificar, texto_ocorrencia
from .regras import CotacaoCandidata, preco_por_tonelada_km, selos
from .servico import AUTOMATICO, ESCOLHA_COMPRADOR, Logistica, agora_real, iso, linha_para_json, para_json

StatusSolicitacao = Literal["ABERTA", "COTADA", "SEM_COTACAO", "SELECIONADA", "INDISPONIVEL", "CANCELADA"]

CAMPOS_SOLICITACAO = """
    id, pedido_id, produto_id, produto_nome, valor_carga, comprador_id, fornecedor_id, tipo_carga, peso_kg,
    origem_cidade, origem_uf, origem_lat, origem_lon, destino_cidade, destino_uf, destino_lat, destino_lon,
    distancia_km, data_coleta_prevista, data_entrega_desejada, aberta_em, prazo_decisao_em,
    cotacao_escolhida_id, criterio, escolhida_por, escolhida_em, status
"""


StatusEntrega = Literal["AGUARDANDO_ALOCACAO", "AGUARDANDO_COLETA", "EM_TRANSITO", "ENTREGUE", "RECUSADA",
                        "CANCELADA"]

CAMPOS_ENTREGA_RESUMO = """
    e.id, e.pedido_id, e.tentativa, e.status, e.transportadora_id, e.transportadora_nome, e.progresso,
    e.previsao_chegada, e.prazo_prometido, e.entregue_em, e.no_prazo, e.atraso_horas, e.com_ocorrencia,
    e.veiculo_placa, s.produto_nome, s.peso_kg, s.tipo_carga, s.origem_cidade, s.origem_uf,
    s.destino_cidade, s.destino_uf, e.atualizado_em
"""

CAMPOS_ENTREGA_DETALHE = """
    e.id, e.pedido_id, e.tentativa, e.status, e.solicitacao_id, e.cotacao_id, e.transportadora_id,
    e.transportadora_nome, e.transportadora_telefone, e.motorista_nome, e.motorista_telefone,
    e.motorista_cnh_mascarada, e.veiculo_placa, e.veiculo_tipo, e.coleta_prevista, e.coletada_em,
    e.previsao_chegada, e.prazo_prometido, e.progresso, e.posicao_lat, e.posicao_lon, e.posicao_em,
    e.com_ocorrencia, e.entregue_em, e.no_prazo, e.atraso_horas, e.rota, e.atualizado_em,
    c.preco AS preco_frete, c.prazo_dias,
    s.produto_nome, s.peso_kg, s.tipo_carga, s.valor_carga, s.comprador_id, s.fornecedor_id,
    s.origem_cidade, s.origem_uf, s.origem_lat, s.origem_lon,
    s.destino_cidade, s.destino_uf, s.destino_lat, s.destino_lon, s.distancia_km
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


TipoDocumento = Literal["cte", "romaneio", "nota-fiscal", "comprovante-coleta"]


class NovaOcorrencia(BaseModel):
    # Os espaços das pontas saem ANTES de contar o tamanho: "     " (5 espaços) passava no
    # mínimo de 5 caracteres e era gravado como texto vazio.
    descricao: Annotated[str, StringConstraints(strip_whitespace=True, min_length=5, max_length=500)] = Field(
        ..., description="O que aconteceu (5 a 500 caracteres, sem contar espaços nas pontas)")


class AjusteDoRelogio(BaseModel):
    # Decimal com 2 casas: é como o banco guarda (NUMERIC(10,2)). Com float, 0.001 virava 0.00
    # no banco (500) e 1.234 era publicado no relogio_ajustado mas lido como 1.23.
    fator: Decimal = Field(..., gt=0, le=100000, decimal_places=2,
                           description="1 = tempo real; 360 = 3 dias em 12 minutos (até 2 casas decimais)")
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
        pedido_id: str | None = Query(None, min_length=1, max_length=64, description="Filtra pelo pedido"),
        pagina: Pagina = Depends(paginacao),
        usuario: Usuario = Depends(leitores),
    ):
        condicao, parametros = _filtro_de_visibilidade(usuario)
        if status:
            condicao += " AND status = %s"
            parametros.append(status)
        if pedido_id:
            condicao += " AND pedido_id = %s"
            parametros.append(pedido_id)
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

    # ------------------------------------------------------------------ comparação (D6)
    @rotas.get("/solicitacoes/{solicitacao_id}/comparacao", tags=["solicitações de frete"],
               summary="Cotações lado a lado, com selos e a pontualidade de cada transportadora")
    async def comparar(solicitacao_id: str, usuario: Usuario = Depends(leitores)):
        condicao, parametros = _filtro_de_visibilidade(usuario)
        async with db.transacao() as conn:
            s = await buscar_um(conn, f"""
                SELECT {CAMPOS_SOLICITACAO} FROM logistica.solicitacao_frete WHERE id = %s AND {condicao}
            """, [solicitacao_id, *parametros])
            if s is None:
                raise _nao_encontrada(solicitacao_id)
            cotacoes = await buscar_todos(conn, """
                SELECT c.id, c.transportadora_id, c.transportadora_nome, c.preco, c.prazo_dias,
                       c.data_entrega_prevista, c.valida_ate, c.origem_cotacao, c.observacoes, c.status, c.recebida_em,
                       d.entregas, d.entregas_no_prazo, d.atraso_total_horas
                  FROM logistica.cotacao c
                  LEFT JOIN logistica.desempenho_transportadora d ON d.transportadora_id = c.transportadora_id
                 WHERE c.solicitacao_id = %s ORDER BY c.preco, c.prazo_dias
            """, (solicitacao_id,))
            entrega = await buscar_um(conn, """
                SELECT id FROM logistica.entrega WHERE solicitacao_id = %s AND status <> 'RECUSADA'
                 ORDER BY tentativa DESC LIMIT 1
            """, (solicitacao_id,))
            hora = await logistica.relogio.agora(conn)

        validas = [c for c in cotacoes if c["status"] == "VALIDA"]
        pontualidade = {c["transportadora_id"]: c["entregas_no_prazo"] / c["entregas"]
                        for c in cotacoes if c["entregas"]}
        candidatas = [CotacaoCandidata(c["id"], c["transportadora_id"], c["preco"], c["prazo_dias"]) for c in validas]
        selos_por_cotacao = selos(candidatas, pontualidade)
        itens = []
        for c in cotacoes:
            item = linha_para_json({k: v for k, v in c.items()
                                    if k not in ("entregas", "entregas_no_prazo", "atraso_total_horas")})
            item["preco_t_km"] = para_json(preco_por_tonelada_km(c["preco"], s["peso_kg"], s["distancia_km"]))
            item["selos"] = selos_por_cotacao.get(c["id"], [])
            item["escolhida"] = c["id"] == s["cotacao_escolhida_id"]
            item["desempenho"] = {
                "entregas": c["entregas"] or 0,
                "pct_no_prazo": round(c["entregas_no_prazo"] / c["entregas"], 4) if c["entregas"] else None,
                "atraso_medio_horas": round(float(c["atraso_total_horas"]) / c["entregas"], 1) if c["entregas"] else None,
            }
            itens.append(item)
        pode_escolher = (s["status"] == "COTADA" and hora <= s["prazo_decisao_em"]
                         and usuario.perfil in ("comprador", "admin"))
        return {"solicitacao": linha_para_json(s), "cotacoes": itens, "podeEscolher": pode_escolher,
                "entregaId": entrega["id"] if entrega else None, "horaDoModulo": iso(hora)}

    # ------------------------------------------------------------------ entregas e rastreio
    def filtro_entrega(usuario: Usuario) -> tuple[str, list]:
        condicao, parametros = _filtro_de_visibilidade(usuario)
        return condicao.replace("comprador_id", "s.comprador_id").replace("fornecedor_id", "s.fornecedor_id"), parametros

    @rotas.get("/entregas", tags=["entregas e rastreio"], summary="Lista as entregas visíveis para o usuário")
    async def listar_entregas(
        status: StatusEntrega | None = Query(None, description="Filtra por status"),
        incluir_recusadas: bool = Query(False, description="Inclui tentativas recusadas pela transportadora"),
        pagina: Pagina = Depends(paginacao),
        usuario: Usuario = Depends(leitores),
    ):
        condicao, parametros = filtro_entrega(usuario)
        if status:
            condicao += " AND e.status = %s"
            parametros.append(status)
        elif not incluir_recusadas:
            condicao += " AND e.status <> 'RECUSADA'"
        async with db.transacao() as conn:
            total = (await buscar_um(conn, f"""
                SELECT count(*) AS n FROM logistica.entrega e
                  JOIN logistica.solicitacao_frete s ON s.id = e.solicitacao_id WHERE {condicao}
            """, parametros))["n"]
            linhas = await buscar_todos(conn, f"""
                SELECT {CAMPOS_ENTREGA_RESUMO} FROM logistica.entrega e
                  JOIN logistica.solicitacao_frete s ON s.id = e.solicitacao_id
                 WHERE {condicao}
                 ORDER BY e.criado_em DESC LIMIT %s OFFSET %s
            """, [*parametros, pagina.size, pagina.offset])
        return resposta_paginada([linha_para_json(l) for l in linhas], pagina, total)

    async def obter_entrega_visivel(conn, entrega_id: str, usuario: Usuario) -> dict:
        condicao, parametros = filtro_entrega(usuario)
        entrega = await buscar_um(conn, f"""
            SELECT {CAMPOS_ENTREGA_DETALHE} FROM logistica.entrega e
              JOIN logistica.solicitacao_frete s ON s.id = e.solicitacao_id
              JOIN logistica.cotacao c ON c.id = e.cotacao_id
             WHERE e.id = %s AND {condicao}
        """, [entrega_id, *parametros])
        if entrega is None:
            raise Problema(404, "ENTREGA_NAO_ENCONTRADA", "Entrega não encontrada",
                           f"Não existe entrega {entrega_id} visível para você.")
        return entrega

    @rotas.get("/entregas/{entrega_id}", tags=["entregas e rastreio"],
               summary="Resumo da entrega: status, carga, transportadora, motorista e veículo")
    async def obter_entrega(entrega_id: str, usuario: Usuario = Depends(leitores)):
        async with db.transacao() as conn:
            return linha_para_json(await obter_entrega_visivel(conn, entrega_id, usuario))

    @rotas.get("/entregas/{entrega_id}/rastreio", tags=["entregas e rastreio"],
               summary="Rota, posição atual e linha do tempo (a tela consulta a cada 5 s)")
    async def rastrear(entrega_id: str, usuario: Usuario = Depends(leitores)):
        async with db.transacao() as conn:
            e = await obter_entrega_visivel(conn, entrega_id, usuario)
            eventos = await buscar_todos(conn, """
                SELECT sequencia, tipo, descricao, lat, lon, progresso, ocorrido_em
                  FROM logistica.evento_rastreio WHERE entrega_id = %s ORDER BY sequencia
            """, (entrega_id,))
            hora = await logistica.relogio.agora(conn)
            ocorrencias = await buscar_todos(conn, """
                SELECT id, autor_papel, descricao, ocorrida_em FROM logistica.ocorrencia
                 WHERE entrega_id = %s ORDER BY ocorrida_em
            """, (entrega_id,))
        posicao = ({"lat": float(e["posicao_lat"]), "lon": float(e["posicao_lon"])}
                   if e["posicao_lat"] is not None else None)
        return {
            "entregaId": e["id"], "pedidoId": e["pedido_id"], "status": e["status"],
            "progresso": float(e["progresso"]), "posicao": posicao,
            "posicaoEm": iso(e["posicao_em"]) if e["posicao_em"] else None,
            "previsaoChegada": iso(e["previsao_chegada"]) if e["previsao_chegada"] else None,
            "origem": {"cidade": e["origem_cidade"], "uf": e["origem_uf"],
                       "lat": float(e["origem_lat"]), "lon": float(e["origem_lon"])},
            "destino": {"cidade": e["destino_cidade"], "uf": e["destino_uf"],
                        "lat": float(e["destino_lat"]), "lon": float(e["destino_lon"])},
            "rota": e["rota"] or [],
            "eventos": [linha_para_json(ev) for ev in eventos],
            "ocorrencias": [linha_para_json(o) for o in ocorrencias],
            "horaDoModulo": iso(hora),
        }

    @rotas.get("/pedidos/{pedido_id}/entrega", tags=["entregas e rastreio"],
               summary="Entrega atual de um pedido (para a tela de pedidos linkar o rastreio)")
    async def entrega_do_pedido(pedido_id: str, usuario: Usuario = Depends(leitores)):
        condicao, parametros = filtro_entrega(usuario)
        async with db.transacao() as conn:
            linha = await buscar_um(conn, f"""
                SELECT e.id FROM logistica.entrega e JOIN logistica.solicitacao_frete s ON s.id = e.solicitacao_id
                 WHERE e.pedido_id = %s AND {condicao} ORDER BY e.tentativa DESC LIMIT 1
            """, [pedido_id, *parametros])
            if linha is None:
                raise Problema(404, "ENTREGA_NAO_ENCONTRADA", "Entrega não encontrada",
                               f"O pedido {pedido_id} ainda não tem entrega visível para você.")
            return linha_para_json(await obter_entrega_visivel(conn, linha["id"], usuario))

    # ------------------------------------------------------------------ documentos (D21)
    @rotas.get("/entregas/{entrega_id}/documentos/{tipo}", tags=["entregas e rastreio"],
               summary="Documento demonstrativo em PDF (sem valor fiscal)",
               responses={200: {"content": {"application/pdf": {}}}})
    async def documento(entrega_id: str, tipo: TipoDocumento, usuario: Usuario = Depends(leitores)):
        async with db.transacao() as conn:
            entrega = await obter_entrega_visivel(conn, entrega_id, usuario)
            hora = await logistica.relogio.agora(conn)
        try:
            pdf = gerar_documento(tipo, entrega, hora)
        except DocumentoIndisponivel as exc:
            raise Problema(409, "DOCUMENTO_INDISPONIVEL", "Documento ainda não disponível", str(exc))
        nome = f"{tipo}-{entrega['pedido_id']}.pdf"
        return Response(pdf, media_type="application/pdf",
                        headers={"Content-Disposition": f'inline; filename="{nome}"'})

    # ------------------------------------------------------------------ ocorrências
    @rotas.post("/entregas/{entrega_id}/ocorrencias", tags=["entregas e rastreio"], status_code=201,
                summary="Reporta uma ocorrência na entrega (comprador ou fornecedor)")
    async def reportar_ocorrencia(entrega_id: str, corpo: NovaOcorrencia,
                                  usuario: Usuario = Depends(exigir_perfis("comprador", "fornecedor"))):
        async with db.transacao() as conn:
            entrega = await obter_entrega_visivel(conn, entrega_id, usuario)
            if entrega["status"] in ("CANCELADA", "RECUSADA"):
                raise Problema(409, "ENTREGA_ENCERRADA", "Entrega encerrada",
                               f"A entrega está {entrega['status']} e não aceita ocorrências.")
            hora = await logistica.relogio.agora(conn)
            linha = await buscar_um(conn, """
                INSERT INTO logistica.ocorrencia (id, entrega_id, pedido_id, autor_id, autor_papel, descricao, ocorrida_em)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id, autor_papel, descricao, ocorrida_em
            """, (str(uuid.uuid4()), entrega_id, entrega["pedido_id"], usuario.id, usuario.perfil,
                  corpo.descricao, hora))
            await conn.execute("UPDATE logistica.entrega SET com_ocorrencia = TRUE, atualizado_em = now() "
                               "WHERE id = %s", (entrega_id,))
            outro = (entrega["fornecedor_id"], "fornecedor") if usuario.perfil == "comprador" \
                else (entrega["comprador_id"], "comprador")
            await notificar(conn, empresa_id=outro[0], papel=outro[1], tipo="OCORRENCIA",
                            texto=texto_ocorrencia(entrega["pedido_id"], usuario.perfil, corpo.descricao),
                            pedido_id=entrega["pedido_id"], solicitacao_id=entrega["solicitacao_id"], agora=hora)
        return linha_para_json(linha)

    @rotas.get("/entregas/{entrega_id}/ocorrencias", tags=["entregas e rastreio"], summary="Ocorrências da entrega")
    async def listar_ocorrencias(entrega_id: str, usuario: Usuario = Depends(leitores)):
        async with db.transacao() as conn:
            await obter_entrega_visivel(conn, entrega_id, usuario)
            linhas = await buscar_todos(conn, """
                SELECT id, autor_papel, descricao, ocorrida_em FROM logistica.ocorrencia
                 WHERE entrega_id = %s ORDER BY ocorrida_em
            """, (entrega_id,))
        return {"items": [linha_para_json(l) for l in linhas]}

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
            novo = await logistica.ajustar_relogio(conn, float(corpo.fator), timedelta(hours=corpo.avancarHoras),
                                                   usuario.id)
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
