"""Rotas REST das transportadoras.

- Consulta das transportadoras homologadas.
- Cadastro de motoristas e veículos (D19): só a própria transportadora ou um administrador.
"""

import uuid
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from comum.auth import Usuario, exigir_perfis
from comum.db import BancoDeDados, buscar_todos, buscar_um
from comum.erros import Problema
from comum.web import Pagina, paginacao, resposta_paginada

from .servico import linha_para_json

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


def criar_rotas(db: BancoDeDados) -> APIRouter:
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
