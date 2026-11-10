"""Rotas REST das transportadoras.

- Consulta das transportadoras homologadas e ranking de desempenho (D6).
- Cargas disponíveis e cotação digitada (D3), para transportadoras reais.
- Cadastro de motoristas e veículos (D19): só a própria transportadora ou um administrador.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field, field_validator

from comum.auth import Usuario, exigir_perfis
from comum.db import BancoDeDados, buscar_todos, buscar_um
from comum.erros import Problema
from comum.formatos import BRASILIA
from comum.web import Pagina, paginacao, resposta_paginada

from .servico import Transportadoras, iso, linha_para_json

CAMPOS = """
    t.id, t.nome, t.telefone_contato, t.ativa, t.simulada, t.tipos_carga, t.ufs_atendidas,
    r.preco_minimo, r.tarifa_km, r.tarifa_ton, r.km_por_dia, r.prazo_base_dias
"""

TipoCarga = Literal["GRANEL", "REFRIGERADO", "CARGA_SECA", "PERIGOSO"]


class DadosMotorista(BaseModel):
    nome: str = Field(..., min_length=3, max_length=200)
    telefone: str | None = Field(None, max_length=30)
    cnhNumero: str = Field(..., pattern=r"^\d{11}$", description="11 dígitos")
    cnhCategoria: Literal["B", "C", "D", "E"]
    cnhValidade: date


class DadosVeiculo(BaseModel):
    placa: str = Field(..., pattern=r"^[A-Z]{3}\d[A-Z0-9]\d{2}$", description="Padrão Mercosul ou antigo, sem traço")
    tipo: str = Field(..., min_length=2, max_length=30, description="Ex.: CARRETA_GRANELEIRA, TRUCK_BAU")
    capacidadeKg: float = Field(..., gt=0, le=80000)
    tiposCarga: list[TipoCarga] = Field(..., min_length=1)
    categoriaCnhExigida: Literal["B", "C", "D", "E"] = "E"


CAMPOS_MOTORISTA = "id, nome, telefone, cnh_numero, cnh_categoria, cnh_validade, ativo, viagem_atual_id IS NOT NULL AS em_viagem"
CAMPOS_VEICULO = ("id, placa, tipo, capacidade_kg, tipos_carga, categoria_cnh_exigida, ativo, "
                  "viagem_atual_id IS NOT NULL AS em_viagem")


class DadosCotacao(BaseModel):
    valor: float = Field(..., gt=0, le=10_000_000, description="Valor do frete em R$")
    dataEntregaPrevista: date = Field(..., description="Data em que a carga chega (prazo estimado)")
    validaAte: datetime = Field(..., description="Até quando a proposta vale (hora do módulo)")
    observacoes: str | None = Field(None, max_length=500)

    @field_validator("validaAte")
    @classmethod
    def com_fuso(cls, valor: datetime) -> datetime:
        return valor if valor.tzinfo else valor.replace(tzinfo=BRASILIA)


# Cargas compatíveis com a transportadora: abertas e dentro do prazo, mais as que ela cotou.
SQL_CARGAS = """
    SELECT s.id, s.pedido_id, s.produto_nome, s.tipo_carga, s.peso_kg, s.origem_cidade, s.origem_uf,
           s.destino_cidade, s.destino_uf, s.distancia_km, s.data_coleta_prevista, s.prazo_decisao_em,
           s.status, s.cancelada, s.transportadora_vencedora_id,
           c.id AS minha_cotacao_id, c.preco AS minha_cotacao_preco, c.prazo_dias AS minha_cotacao_prazo,
           c.data_entrega_prevista AS minha_cotacao_entrega, c.origem_cotacao AS minha_cotacao_origem,
           c.emitida_em AS minha_cotacao_emitida_em
      FROM transportadoras.solicitacao_recebida s
      LEFT JOIN transportadoras.cotacao_emitida c ON c.solicitacao_id = s.id AND c.transportadora_id = %(tid)s
     WHERE s.tipo_carga = ANY(%(tipos)s)
       AND (%(ufs)s::text[] IS NULL OR (s.origem_uf = ANY(%(ufs)s) AND s.destino_uf = ANY(%(ufs)s)))
       AND (%(todas)s OR (s.status = 'ABERTA' AND s.prazo_decisao_em > %(agora)s) OR c.id IS NOT NULL)
     ORDER BY s.data_coleta_prevista DESC, s.recebida_em DESC, s.id
     LIMIT %(limite)s OFFSET %(deslocamento)s
"""

# Ranking: viagens e cotações de cada transportadora (D6), com filtro opcional por tipo de carga.
SQL_RANKING = """
    SELECT t.id, t.nome, t.simulada, t.tipos_carga,
           COALESCE(vi.entregas, 0) AS entregas, COALESCE(vi.no_prazo, 0) AS no_prazo,
           vi.atraso_medio_horas, COALESCE(vi.escolhida, 0) AS vezes_escolhida,
           COALESCE(co.cotacoes, 0) AS cotacoes, co.preco_medio_t_km
      FROM transportadoras.transportadora t
      LEFT JOIN LATERAL (
            SELECT count(*) FILTER (WHERE v.status = 'ENTREGUE') AS entregas,
                   count(*) FILTER (WHERE v.status = 'ENTREGUE' AND v.no_prazo) AS no_prazo,
                   round(avg(v.atraso_real_horas) FILTER (WHERE v.status = 'ENTREGUE'), 1) AS atraso_medio_horas,
                   count(*) AS escolhida
              FROM transportadoras.viagem v
              JOIN transportadoras.solicitacao_recebida s ON s.id = v.solicitacao_id
             WHERE v.transportadora_id = t.id AND (%(tipo)s::text IS NULL OR s.tipo_carga = %(tipo)s)
      ) vi ON TRUE
      LEFT JOIN LATERAL (
            SELECT count(*) AS cotacoes,
                   round(avg(c.preco / NULLIF(s.peso_kg / 1000.0 * s.distancia_km, 0)), 4) AS preco_medio_t_km
              FROM transportadoras.cotacao_emitida c
              JOIN transportadoras.solicitacao_recebida s ON s.id = c.solicitacao_id
             WHERE c.transportadora_id = t.id AND (%(tipo)s::text IS NULL OR s.tipo_carga = %(tipo)s)
      ) co ON TRUE
     WHERE t.ativa
     ORDER BY (COALESCE(vi.no_prazo, 0)::float / NULLIF(vi.entregas, 0)) DESC NULLS LAST,
              COALESCE(vi.entregas, 0) DESC, t.nome
     LIMIT %(limite)s OFFSET %(deslocamento)s
"""


def situacao_da_carga(linha: dict, transportadora_id: str, agora: datetime) -> str:
    """Como a carga aparece para a transportadora na tela "Solicitações de frete"."""
    cotou = linha["minha_cotacao_id"] is not None
    vencedora = linha["transportadora_vencedora_id"]
    if vencedora:
        if vencedora == transportadora_id:
            return "VENCEU"
        return "OUTRA_VENCEU" if cotou else "ENCERRADA"
    if linha["cancelada"]:
        return "CANCELADA"
    if linha["status"] == "ABERTA" and linha["prazo_decisao_em"] > agora:
        return "COTACAO_ENVIADA" if cotou else "ACEITANDO_COTACOES"
    return "ENCERRADA"


def criar_rotas(db: BancoDeDados, servico: Transportadoras) -> APIRouter:
    rotas = APIRouter(prefix="/api/v1/transportadoras")
    todos = exigir_perfis("comprador", "fornecedor", "transportadora", "admin")
    donos = exigir_perfis("transportadora", "admin")

    async def conferir_dono(conn, transportadora_id: str, usuario: Usuario) -> None:
        linha = await buscar_um(conn, "SELECT empresa_id FROM transportadoras.transportadora WHERE id = %s",
                                (transportadora_id,))
        if linha is None:
            raise Problema(404, "TRANSPORTADORA_NAO_ENCONTRADA", "Transportadora não encontrada",
                           f"Não existe transportadora {transportadora_id}.")
        if not usuario.admin and linha["empresa_id"] != usuario.empresa_id:
            raise Problema(403, "OUTRA_TRANSPORTADORA", "Acesso negado",
                           "Uma transportadora só gerencia a própria frota.")

    # ------------------------------------------------------------------ rotas fixas (antes de /{transportadora_id})
    @rotas.get("/minha", tags=["transportadoras"], summary="A transportadora da empresa do usuário")
    async def minha(usuario: Usuario = Depends(exigir_perfis("transportadora"))):
        async with db.transacao() as conn:
            linha = await buscar_um(conn, f"""
                SELECT {CAMPOS} FROM transportadoras.transportadora t
                  LEFT JOIN transportadoras.regra_cotacao r ON r.transportadora_id = t.id
                 WHERE t.empresa_id = %s
            """, (usuario.empresa_id,))
        if linha is None:
            raise Problema(404, "SEM_TRANSPORTADORA", "Transportadora não encontrada",
                           "A sua empresa não tem uma transportadora homologada.")
        return linha_para_json(linha)

    @rotas.get("/ranking", tags=["ranking"], summary="Ranking de desempenho das transportadoras")
    async def ranking(tipoCarga: TipoCarga | None = Query(None, description="Filtra por tipo de carga"),
                      pagina: Pagina = Depends(paginacao), _: Usuario = Depends(todos)):
        async with db.transacao() as conn:
            total = (await buscar_um(conn, "SELECT count(*) AS n FROM transportadoras.transportadora WHERE ativa"))["n"]
            linhas = await buscar_todos(conn, SQL_RANKING, {"tipo": tipoCarga, "limite": pagina.size,
                                                            "deslocamento": pagina.offset})
        itens = []
        for posicao, l in enumerate(linhas, start=pagina.offset + 1):
            item = linha_para_json(l)
            item["posicao"] = posicao
            item["pct_no_prazo"] = round(l["no_prazo"] / l["entregas"], 4) if l["entregas"] else None
            itens.append(item)
        return resposta_paginada(itens, pagina, total)

    @rotas.get("/solicitacoes", tags=["cotação digitada"],
               summary="Cargas compatíveis com a transportadora do usuário (tela Solicitações de frete)")
    async def cargas_disponiveis(
        todas: bool = Query(False, description="Inclui as encerradas em que a transportadora não cotou"),
        pagina: Pagina = Depends(paginacao),
        usuario: Usuario = Depends(exigir_perfis("transportadora")),
    ):
        async with db.transacao() as conn:
            transportadora = await buscar_um(conn, """
                SELECT id, tipos_carga, ufs_atendidas FROM transportadoras.transportadora WHERE empresa_id = %s
            """, (usuario.empresa_id,))
            if transportadora is None:
                raise Problema(403, "SEM_TRANSPORTADORA", "Acesso negado",
                               "A sua empresa não tem uma transportadora homologada.")
            agora = await servico.relogio.agora(conn)
            parametros = {"tid": transportadora["id"], "tipos": list(transportadora["tipos_carga"]),
                          "ufs": list(transportadora["ufs_atendidas"]) if transportadora["ufs_atendidas"] else None,
                          "todas": todas, "agora": agora, "limite": pagina.size, "deslocamento": pagina.offset}
            total = (await buscar_um(conn, f"SELECT count(*) AS n FROM ({SQL_CARGAS}) x",
                                     {**parametros, "limite": None, "deslocamento": 0}))["n"]
            linhas = await buscar_todos(conn, SQL_CARGAS, parametros)
        itens = []
        for l in linhas:
            item = linha_para_json(l)
            item["situacao"] = situacao_da_carga(l, transportadora["id"], agora)
            item["pode_cotar"] = item["situacao"] == "ACEITANDO_COTACOES"
            itens.append(item)
        return {**resposta_paginada(itens, pagina, total), "horaDoModulo": iso(agora)}

    @rotas.post("/solicitacoes/{solicitacao_id}/cotacoes", tags=["cotação digitada"],
                status_code=status.HTTP_201_CREATED, summary="Envia uma cotação digitada")
    async def enviar_cotacao(solicitacao_id: str, dados: DadosCotacao,
                             usuario: Usuario = Depends(exigir_perfis("transportadora"))):
        async with db.transacao() as conn:
            return await servico.cotar_manualmente(
                conn, usuario.empresa_id, usuario.id, solicitacao_id, Decimal(str(dados.valor)),
                dados.dataEntregaPrevista, dados.validaAte, dados.observacoes or None)

    # ------------------------------------------------------------------ transportadoras
    @rotas.get("", tags=["transportadoras"], summary="Lista as transportadoras homologadas")
    async def listar(pagina: Pagina = Depends(paginacao), _: Usuario = Depends(todos)):
        async with db.transacao() as conn:
            total = (await buscar_um(conn, "SELECT count(*) AS total FROM transportadoras.transportadora"))["total"]
            linhas = await buscar_todos(conn, f"""
                SELECT {CAMPOS} FROM transportadoras.transportadora t
                  LEFT JOIN transportadoras.regra_cotacao r ON r.transportadora_id = t.id
                 ORDER BY t.nome LIMIT %s OFFSET %s
            """, (pagina.size, pagina.offset))
        return resposta_paginada([linha_para_json(l) for l in linhas], pagina, total)

    @rotas.get("/{transportadora_id}", tags=["transportadoras"], summary="Detalhe de uma transportadora")
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

    # ------------------------------------------------------------------ motoristas
    @rotas.get("/{transportadora_id}/motoristas", tags=["frota"], summary="Motoristas da transportadora")
    async def listar_motoristas(transportadora_id: str, pagina: Pagina = Depends(paginacao),
                                usuario: Usuario = Depends(donos)):
        async with db.transacao() as conn:
            await conferir_dono(conn, transportadora_id, usuario)
            total = (await buscar_um(conn, "SELECT count(*) AS n FROM transportadoras.motorista "
                                           "WHERE transportadora_id = %s", (transportadora_id,)))["n"]
            linhas = await buscar_todos(conn, f"""
                SELECT {CAMPOS_MOTORISTA} FROM transportadoras.motorista
                 WHERE transportadora_id = %s ORDER BY nome LIMIT %s OFFSET %s
            """, (transportadora_id, pagina.size, pagina.offset))
        return resposta_paginada([linha_para_json(l) for l in linhas], pagina, total)

    @rotas.post("/{transportadora_id}/motoristas", tags=["frota"], status_code=status.HTTP_201_CREATED,
                summary="Cadastra um motorista")
    async def criar_motorista(transportadora_id: str, dados: DadosMotorista, usuario: Usuario = Depends(donos)):
        async with db.transacao() as conn:
            await conferir_dono(conn, transportadora_id, usuario)
            if await buscar_um(conn, "SELECT 1 FROM transportadoras.motorista WHERE transportadora_id = %s "
                                     "AND cnh_numero = %s", (transportadora_id, dados.cnhNumero)):
                raise Problema(409, "MOTORISTA_DUPLICADO", "Motorista já cadastrado",
                               "Já existe um motorista com essa CNH nesta transportadora.")
            linha = await buscar_um(conn, f"""
                INSERT INTO transportadoras.motorista (id, transportadora_id, nome, telefone, cnh_numero,
                                                       cnh_categoria, cnh_validade)
                VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING {CAMPOS_MOTORISTA}
            """, (f"mot-{uuid.uuid4().hex[:10]}", transportadora_id, dados.nome, dados.telefone, dados.cnhNumero,
                  dados.cnhCategoria, dados.cnhValidade))
        return linha_para_json(linha)

    @rotas.put("/{transportadora_id}/motoristas/{motorista_id}", tags=["frota"], summary="Atualiza um motorista")
    async def atualizar_motorista(transportadora_id: str, motorista_id: str, dados: DadosMotorista,
                                  usuario: Usuario = Depends(donos)):
        async with db.transacao() as conn:
            await conferir_dono(conn, transportadora_id, usuario)
            linha = await buscar_um(conn, f"""
                UPDATE transportadoras.motorista
                   SET nome = %s, telefone = %s, cnh_numero = %s, cnh_categoria = %s, cnh_validade = %s
                 WHERE id = %s AND transportadora_id = %s RETURNING {CAMPOS_MOTORISTA}
            """, (dados.nome, dados.telefone, dados.cnhNumero, dados.cnhCategoria, dados.cnhValidade,
                  motorista_id, transportadora_id))
        if linha is None:
            raise Problema(404, "MOTORISTA_NAO_ENCONTRADO", "Motorista não encontrado",
                           f"Não existe motorista {motorista_id} nesta transportadora.")
        return linha_para_json(linha)

    @rotas.delete("/{transportadora_id}/motoristas/{motorista_id}", tags=["frota"],
                  summary="Desativa um motorista (o histórico das viagens é mantido)")
    async def desativar_motorista(transportadora_id: str, motorista_id: str, usuario: Usuario = Depends(donos)):
        return await _desativar(db, conferir_dono, usuario, transportadora_id, "motorista", motorista_id)

    # ------------------------------------------------------------------ veículos
    @rotas.get("/{transportadora_id}/veiculos", tags=["frota"], summary="Veículos da transportadora")
    async def listar_veiculos(transportadora_id: str, pagina: Pagina = Depends(paginacao),
                              usuario: Usuario = Depends(donos)):
        async with db.transacao() as conn:
            await conferir_dono(conn, transportadora_id, usuario)
            total = (await buscar_um(conn, "SELECT count(*) AS n FROM transportadoras.veiculo "
                                           "WHERE transportadora_id = %s", (transportadora_id,)))["n"]
            linhas = await buscar_todos(conn, f"""
                SELECT {CAMPOS_VEICULO} FROM transportadoras.veiculo
                 WHERE transportadora_id = %s ORDER BY placa LIMIT %s OFFSET %s
            """, (transportadora_id, pagina.size, pagina.offset))
        return resposta_paginada([linha_para_json(l) for l in linhas], pagina, total)

    @rotas.post("/{transportadora_id}/veiculos", tags=["frota"], status_code=status.HTTP_201_CREATED,
                summary="Cadastra um veículo")
    async def criar_veiculo(transportadora_id: str, dados: DadosVeiculo, usuario: Usuario = Depends(donos)):
        async with db.transacao() as conn:
            await conferir_dono(conn, transportadora_id, usuario)
            if await buscar_um(conn, "SELECT 1 FROM transportadoras.veiculo WHERE placa = %s", (dados.placa,)):
                raise Problema(409, "PLACA_DUPLICADA", "Placa já cadastrada",
                               f"Já existe um veículo com a placa {dados.placa}.")
            linha = await buscar_um(conn, f"""
                INSERT INTO transportadoras.veiculo (id, transportadora_id, placa, tipo, capacidade_kg, tipos_carga,
                                                     categoria_cnh_exigida)
                VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING {CAMPOS_VEICULO}
            """, (f"vei-{uuid.uuid4().hex[:10]}", transportadora_id, dados.placa, dados.tipo, dados.capacidadeKg,
                  list(dados.tiposCarga), dados.categoriaCnhExigida))
        return linha_para_json(linha)

    @rotas.put("/{transportadora_id}/veiculos/{veiculo_id}", tags=["frota"], summary="Atualiza um veículo")
    async def atualizar_veiculo(transportadora_id: str, veiculo_id: str, dados: DadosVeiculo,
                                usuario: Usuario = Depends(donos)):
        async with db.transacao() as conn:
            await conferir_dono(conn, transportadora_id, usuario)
            linha = await buscar_um(conn, f"""
                UPDATE transportadoras.veiculo
                   SET placa = %s, tipo = %s, capacidade_kg = %s, tipos_carga = %s, categoria_cnh_exigida = %s
                 WHERE id = %s AND transportadora_id = %s RETURNING {CAMPOS_VEICULO}
            """, (dados.placa, dados.tipo, dados.capacidadeKg, list(dados.tiposCarga), dados.categoriaCnhExigida,
                  veiculo_id, transportadora_id))
        if linha is None:
            raise Problema(404, "VEICULO_NAO_ENCONTRADO", "Veículo não encontrado",
                           f"Não existe veículo {veiculo_id} nesta transportadora.")
        return linha_para_json(linha)

    @rotas.delete("/{transportadora_id}/veiculos/{veiculo_id}", tags=["frota"],
                  summary="Desativa um veículo (o histórico das viagens é mantido)")
    async def desativar_veiculo(transportadora_id: str, veiculo_id: str, usuario: Usuario = Depends(donos)):
        return await _desativar(db, conferir_dono, usuario, transportadora_id, "veiculo", veiculo_id)

    return rotas


async def _desativar(db: BancoDeDados, conferir_dono, usuario: Usuario, transportadora_id: str,
                     tabela: str, item_id: str) -> dict:
    nomes = {"motorista": ("transportadoras.motorista", "MOTORISTA", "Motorista"),
             "veiculo": ("transportadoras.veiculo", "VEICULO", "Veículo")}
    tabela_sql, codigo, nome = nomes[tabela]
    async with db.transacao() as conn:
        await conferir_dono(conn, transportadora_id, usuario)
        linha = await buscar_um(conn, f"SELECT viagem_atual_id FROM {tabela_sql} WHERE id = %s "
                                      "AND transportadora_id = %s FOR UPDATE", (item_id, transportadora_id))
        if linha is None:
            raise Problema(404, f"{codigo}_NAO_ENCONTRADO", f"{nome} não encontrado",
                           f"Não existe {tabela} {item_id} nesta transportadora.")
        if linha["viagem_atual_id"]:
            raise Problema(409, f"{codigo}_EM_VIAGEM", f"{nome} em viagem",
                           f"Não é possível desativar: o {tabela} está numa viagem em andamento.")
        await conn.execute(f"UPDATE {tabela_sql} SET ativo = FALSE WHERE id = %s", (item_id,))
    return {"id": item_id, "ativo": False}
