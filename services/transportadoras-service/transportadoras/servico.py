"""Regras de negócio das transportadoras (etapa 1).

    solicitacao_frete_criada ──► cotar_automaticamente ──► cotacao_recebida (uma por transportadora)

Só as transportadoras simuladas (D3) cotam sozinhas. Transportadoras reais
cotam digitando na tela (etapa 4). A checagem de motorista e veículo livres
antes de cotar (D20) entra na etapa 3, junto com o cadastro deles.
"""

import logging
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from psycopg import AsyncConnection

from comum.db import buscar_todos, buscar_um
from comum.eventos import validar_payload
from comum.geo import somar_dias_uteis
from comum.outbox import gravar_evento
from comum.relogio import Relogio

from . import SCHEMA, SERVICO
from .cotacao import PerfilTransportadora, RegraCotacao, atende, calcular

log = logging.getLogger(__name__)

# Namespace fixo: a mesma solicitação + transportadora gera sempre o mesmo cotacaoId.
NAMESPACE_COTACAO = uuid.UUID("6f1d2c3e-4b5a-4c7d-9e8f-0a1b2c3d4e5f")


def id_da_cotacao(solicitacao_id: str, transportadora_id: str) -> str:
    return str(uuid.uuid5(NAMESPACE_COTACAO, f"{solicitacao_id}:{transportadora_id}"))


class Transportadoras:
    def __init__(self, relogio: Relogio):
        self.relogio = relogio

    async def cotar_automaticamente(self, conn: AsyncConnection, envelope: dict) -> int:
        solicitacao = validar_payload("solicitacao_frete_criada", envelope["payload"])
        sid = solicitacao["solicitacaoFreteId"]
        origem, destino = solicitacao["origem"], solicitacao["destino"]

        nova = await buscar_um(conn, """
            INSERT INTO transportadoras.solicitacao_recebida (
                id, pedido_id, produto_nome, tipo_carga, peso_kg, origem_cidade, origem_uf, origem_lat, origem_lon,
                destino_cidade, destino_uf, destino_lat, destino_lon, distancia_km, data_coleta_prevista,
                prazo_decisao_em)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO NOTHING
            RETURNING id
        """, (
            sid, solicitacao["pedidoId"], solicitacao.get("produtoNome"), solicitacao["tipoCarga"],
            solicitacao["pesoKg"], origem["cidade"], origem["uf"], origem["lat"], origem["lon"],
            destino["cidade"], destino["uf"], destino["lat"], destino["lon"], solicitacao["distanciaKm"],
            solicitacao["dataColetaPrevista"], solicitacao["prazoDecisaoEm"],
        ))
        if nova is None:
            log.info("Solicitação já recebida antes", extra={"dados": {"solicitacaoFreteId": sid}})
            return 0

        agora = await self.relogio.agora(conn)
        coleta = date.fromisoformat(solicitacao["dataColetaPrevista"])
        emitidas = 0
        for perfil, regra in await self._transportadoras_simuladas(conn):
            if not atende(perfil, solicitacao["tipoCarga"], origem["uf"], destino["uf"]):
                continue
            preco, prazo = calcular(regra, solicitacao["distanciaKm"], solicitacao["pesoKg"], solicitacao["tipoCarga"])
            await self._emitir(conn, sid, perfil, preco, prazo, somar_dias_uteis(coleta, prazo),
                               solicitacao["prazoDecisaoEm"], agora, envelope.get("correlationId"))
            emitidas += 1

        log.info("Cotações simuladas emitidas", extra={"dados": {
            "solicitacaoFreteId": sid, "tipoCarga": solicitacao["tipoCarga"], "quantidade": emitidas}})
        return emitidas

    async def _transportadoras_simuladas(self, conn: AsyncConnection) -> list[tuple[PerfilTransportadora, RegraCotacao]]:
        linhas = await buscar_todos(conn, """
            SELECT t.id, t.nome, t.tipos_carga, t.ufs_atendidas,
                   r.preco_minimo, r.tarifa_km, r.tarifa_ton, r.fator_tipo_carga, r.km_por_dia, r.prazo_base_dias
              FROM transportadoras.transportadora t
              JOIN transportadoras.regra_cotacao r ON r.transportadora_id = t.id
             WHERE t.ativa AND t.simulada
             ORDER BY t.id
        """)
        resultado = []
        for l in linhas:
            perfil = PerfilTransportadora(
                id=l["id"], nome=l["nome"], tipos_carga=tuple(l["tipos_carga"]),
                ufs_atendidas=tuple(l["ufs_atendidas"]) if l["ufs_atendidas"] else None)
            regra = RegraCotacao(
                preco_minimo=l["preco_minimo"], tarifa_km=l["tarifa_km"], tarifa_ton=l["tarifa_ton"],
                km_por_dia=l["km_por_dia"], prazo_base_dias=l["prazo_base_dias"],
                fator_tipo_carga={k: Decimal(str(v)) for k, v in (l["fator_tipo_carga"] or {}).items()})
            resultado.append((perfil, regra))
        return resultado

    async def _emitir(self, conn: AsyncConnection, solicitacao_id: str, perfil: PerfilTransportadora,
                      preco: Decimal, prazo: int, data_entrega: date, valida_ate: str, agora: datetime,
                      id_correlacao: str | None) -> None:
        cotacao_id = id_da_cotacao(solicitacao_id, perfil.id)
        await conn.execute("""
            INSERT INTO transportadoras.cotacao_emitida (
                id, solicitacao_id, transportadora_id, preco, prazo_dias, data_entrega_prevista, valida_ate,
                origem_cotacao, emitida_em)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'SIMULADA', %s)
        """, (cotacao_id, solicitacao_id, perfil.id, preco, prazo, data_entrega, valida_ate, agora))
        await gravar_evento(conn, SCHEMA, SERVICO, "cotacao_recebida", solicitacao_id, {
            "cotacaoId": cotacao_id,
            "solicitacaoFreteId": solicitacao_id,
            "transportadoraId": perfil.id,
            "transportadoraNome": perfil.nome,
            "preco": float(preco),
            "prazoDias": prazo,
            "dataEntregaPrevista": data_entrega.isoformat(),
            "validaAte": valida_ate,
            "origemCotacao": "SIMULADA",
            "observacoes": None,
        }, id_correlacao)


def para_json(valor):
    if isinstance(valor, Decimal):
        return float(valor)
    if isinstance(valor, datetime):
        return valor.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    if hasattr(valor, "isoformat"):
        return valor.isoformat()
    return valor


def linha_para_json(linha: dict) -> dict:
    return {chave: para_json(valor) for chave, valor in linha.items()}
