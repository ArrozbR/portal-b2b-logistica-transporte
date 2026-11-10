"""Acompanhamento da entrega a partir dos eventos de rastreio (etapa 3).

    rastreio_atualizado ──► registrar_rastreio
        VIAGEM_ALOCADA      motorista, veículo, rota e coleta prevista; avisa comprador e fornecedor
        VIAGEM_RECUSADA     troca de transportadora (Logistica.trocar_transportadora)
        COLETA_REALIZADA    entrega vai a EM_TRANSITO; avisa os dois
        POSICAO, PARADA     posição, progresso e previsão
        PREVISAO_ATUALIZADA nova previsão; avisa o comprador do atraso
        OCORRENCIA          marca a entrega com ocorrência
        ENTREGA_REALIZADA   entrega vai a ENTREGUE; publica entrega_concluida, conta a pontualidade, avisa os dois

Ordem: o Kafka entrega em ordem os eventos de um mesmo pedido (chave
pedidoId). Mesmo assim, cada evento traz um número de `sequencia`, e um
evento com número menor ou igual ao último aplicado é ignorado. Assim, uma
mensagem repetida ou atrasada nunca faz o caminhão voltar no mapa.
"""

import logging
from datetime import datetime

from psycopg import AsyncConnection
from psycopg.types.json import Jsonb

from comum.db import buscar_um
from comum.eventos import EventoInvalido, validar_payload
from comum.outbox import gravar_evento

from . import SCHEMA, SERVICO
from .notificacoes import (COMPRADOR, FORNECEDOR, notificar, texto_coleta_realizada, texto_entrega_realizada,
                           texto_motorista_escalado, texto_previsao_atualizada)
from .servico import Logistica

log = logging.getLogger(__name__)

STATUS_FINAIS = ("ENTREGUE", "CANCELADA", "RECUSADA")


def _momento(texto: str | None) -> datetime | None:
    return datetime.fromisoformat(texto) if texto else None


class Rastreio:
    def __init__(self, logistica: Logistica):
        self.logistica = logistica

    async def registrar_rastreio(self, conn: AsyncConnection, envelope: dict) -> str:
        ev = validar_payload("rastreio_atualizado", envelope["payload"])
        entrega = await buscar_um(conn, """
            SELECT e.*, s.comprador_id, s.fornecedor_id, s.correlation_id
              FROM logistica.entrega e JOIN logistica.solicitacao_frete s ON s.id = e.solicitacao_id
             WHERE e.id = %s FOR UPDATE OF e
        """, (ev["entregaId"],))
        if entrega is None:
            raise EventoInvalido(f"Entrega desconhecida: {ev['entregaId']}")

        if ev["sequencia"] <= entrega["ultima_sequencia"]:
            log.info("Evento de rastreio antigo ou repetido, ignorado", extra={"dados": {
                "entregaId": ev["entregaId"], "sequencia": ev["sequencia"],
                "ultimaAplicada": entrega["ultima_sequencia"]}})
            return "ignorado"
        if entrega["status"] in STATUS_FINAIS:
            log.info("Evento de rastreio de entrega encerrada, ignorado", extra={"dados": {
                "entregaId": ev["entregaId"], "status": entrega["status"], "tipo": ev["tipo"]}})
            return "ignorado"

        posicao = ev.get("posicao") or {}
        await conn.execute("""
            INSERT INTO logistica.evento_rastreio (entrega_id, sequencia, tipo, descricao, lat, lon, progresso,
                                                   ocorrido_em, event_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (entrega["id"], ev["sequencia"], ev["tipo"], ev["descricao"], posicao.get("lat"), posicao.get("lon"),
              ev.get("progresso"), ev["ocorridoEm"], envelope["eventId"]))
        await conn.execute("UPDATE logistica.entrega SET ultima_sequencia = %s, atualizado_em = now() WHERE id = %s",
                           (ev["sequencia"], entrega["id"]))

        tratar = {
            "VIAGEM_ALOCADA": self._alocada,
            "VIAGEM_RECUSADA": self._recusada,
            "COLETA_REALIZADA": self._coletada,
            "POSICAO": self._posicao,
            "PARADA": self._posicao,
            "PREVISAO_ATUALIZADA": self._previsao,
            "OCORRENCIA": self._ocorrencia,
            "ENTREGA_REALIZADA": self._entregue,
        }[ev["tipo"]]
        await tratar(conn, entrega, ev)
        log.info("Rastreio aplicado", extra={"dados": {
            "entregaId": entrega["id"], "pedidoId": entrega["pedido_id"], "tipo": ev["tipo"],
            "sequencia": ev["sequencia"], "progresso": ev.get("progresso")}})
        return ev["tipo"]

    # ------------------------------------------------------------------ cada tipo de evento
    async def _alocada(self, conn: AsyncConnection, entrega: dict, ev: dict) -> None:
        transportadora = ev.get("transportadora") or {}
        await conn.execute("""
            UPDATE logistica.entrega
               SET status = 'AGUARDANDO_COLETA', motorista_nome = %s, motorista_telefone = %s,
                   motorista_cnh_mascarada = %s, veiculo_placa = %s, veiculo_tipo = %s, rota = %s,
                   coleta_prevista = %s, previsao_chegada = %s, progresso = 0,
                   posicao_lat = %s, posicao_lon = %s, posicao_em = %s,
                   transportadora_nome = COALESCE(%s, transportadora_nome), transportadora_telefone = %s
             WHERE id = %s
        """, (ev["motorista"]["nome"], ev["motorista"].get("telefone"), ev["motorista"].get("cnhMascarada"),
              ev["veiculo"]["placa"], ev["veiculo"]["tipo"], Jsonb(ev["rota"]), ev["coletaPrevista"],
              ev["previsaoChegada"], ev["posicao"]["lat"], ev["posicao"]["lon"], ev["ocorridoEm"],
              transportadora.get("nome"), transportadora.get("telefone"), entrega["id"]))
        await self._avisar(conn, entrega, (COMPRADOR, FORNECEDOR), "MOTORISTA_ESCALADO",
                           texto_motorista_escalado(entrega["pedido_id"], ev["motorista"]["nome"],
                                                    ev["veiculo"]["placa"], _momento(ev["coletaPrevista"])))

    async def _recusada(self, conn: AsyncConnection, entrega: dict, ev: dict) -> None:
        await self.logistica.trocar_transportadora(conn, entrega)

    async def _coletada(self, conn: AsyncConnection, entrega: dict, ev: dict) -> None:
        await conn.execute("""
            UPDATE logistica.entrega SET status = 'EM_TRANSITO', coletada_em = %s,
                   posicao_lat = COALESCE(%s, posicao_lat), posicao_lon = COALESCE(%s, posicao_lon), posicao_em = %s
             WHERE id = %s
        """, (ev["ocorridoEm"], (ev.get("posicao") or {}).get("lat"), (ev.get("posicao") or {}).get("lon"),
              ev["ocorridoEm"], entrega["id"]))
        previsao = _momento(ev.get("previsaoChegada")) or entrega["previsao_chegada"]
        await self._avisar(conn, entrega, (COMPRADOR, FORNECEDOR), "COLETA_REALIZADA",
                           texto_coleta_realizada(entrega["pedido_id"], previsao))

    async def _posicao(self, conn: AsyncConnection, entrega: dict, ev: dict) -> None:
        await conn.execute("""
            UPDATE logistica.entrega
               SET posicao_lat = %s, posicao_lon = %s, posicao_em = %s, progresso = %s, previsao_chegada = %s
             WHERE id = %s
        """, (ev["posicao"]["lat"], ev["posicao"]["lon"], ev["ocorridoEm"], ev["progresso"], ev["previsaoChegada"],
              entrega["id"]))

    async def _previsao(self, conn: AsyncConnection, entrega: dict, ev: dict) -> None:
        await self._posicao(conn, entrega, ev)
        anterior = _momento(ev.get("previsaoAnterior")) or entrega["previsao_chegada"]
        await self._avisar(conn, entrega, (COMPRADOR,), "PREVISAO_ATUALIZADA",
                           texto_previsao_atualizada(entrega["pedido_id"], anterior, _momento(ev["previsaoChegada"])))

    async def _ocorrencia(self, conn: AsyncConnection, entrega: dict, ev: dict) -> None:
        await conn.execute("UPDATE logistica.entrega SET com_ocorrencia = TRUE WHERE id = %s", (entrega["id"],))

    async def _entregue(self, conn: AsyncConnection, entrega: dict, ev: dict) -> None:
        await conn.execute("""
            UPDATE logistica.entrega
               SET status = 'ENTREGUE', entregue_em = %s, no_prazo = %s, atraso_horas = %s, progresso = 1,
                   posicao_lat = %s, posicao_lon = %s, posicao_em = %s
             WHERE id = %s
        """, (ev["ocorridoEm"], ev["noPrazo"], ev["atrasoHoras"], ev["posicao"]["lat"], ev["posicao"]["lon"],
              ev["ocorridoEm"], entrega["id"]))

        # Pontualidade da transportadora, usada na comparação e no desempate (arquitetura, seção 9.3).
        await conn.execute("""
            INSERT INTO logistica.desempenho_transportadora
                (transportadora_id, nome, entregas, entregas_no_prazo, atraso_total_horas)
            VALUES (%s, %s, 1, %s, %s)
            ON CONFLICT (transportadora_id) DO UPDATE
               SET nome = COALESCE(EXCLUDED.nome, logistica.desempenho_transportadora.nome),
                   entregas = logistica.desempenho_transportadora.entregas + 1,
                   entregas_no_prazo = logistica.desempenho_transportadora.entregas_no_prazo + EXCLUDED.entregas_no_prazo,
                   atraso_total_horas = logistica.desempenho_transportadora.atraso_total_horas
                                        + EXCLUDED.atraso_total_horas,
                   atualizado_em = now()
        """, (entrega["transportadora_id"], entrega["transportadora_nome"], 1 if ev["noPrazo"] else 0,
              ev["atrasoHoras"]))

        payload = {
            "pedidoId": entrega["pedido_id"],
            "entregaId": entrega["id"],
            "transportadoraId": entrega["transportadora_id"],
            "entregueEm": ev["ocorridoEm"],
            "prazoPrometido": entrega["prazo_prometido"].isoformat() if entrega["prazo_prometido"] else None,
            "noPrazo": ev["noPrazo"],
            "atrasoHoras": ev["atrasoHoras"],
        }
        validar_payload("entrega_concluida", payload)
        await gravar_evento(conn, SCHEMA, SERVICO, "entrega_concluida", entrega["pedido_id"], payload,
                            entrega["correlation_id"])
        await self._avisar(conn, entrega, (COMPRADOR, FORNECEDOR), "ENTREGA_REALIZADA",
                           texto_entrega_realizada(entrega["pedido_id"], _momento(ev["ocorridoEm"]),
                                                   ev["noPrazo"], ev["atrasoHoras"]))

    async def _avisar(self, conn: AsyncConnection, entrega: dict, papeis: tuple[str, ...], tipo: str,
                      texto: tuple[str, str]) -> None:
        agora = await self.logistica.relogio.agora(conn)
        empresas = {COMPRADOR: entrega["comprador_id"], FORNECEDOR: entrega["fornecedor_id"]}
        for papel in papeis:
            await notificar(conn, empresa_id=empresas[papel], papel=papel, tipo=tipo, texto=texto,
                            pedido_id=entrega["pedido_id"], solicitacao_id=entrega["solicitacao_id"], agora=agora)
