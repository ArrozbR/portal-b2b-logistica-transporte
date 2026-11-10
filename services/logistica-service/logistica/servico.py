"""Regras de negócio da logística (etapa 1).

Fluxo coberto:
    pedido_criado ──► abrir_solicitacao ──► solicitacao_frete_criada
    cotacao_recebida ──► registrar_cotacao
    prazo vence ──► escolher (regra automática) ──► frete_selecionado
    prazo vence sem cotação ──► frete_indisponivel

Todas as funções recebem a conexão `conn` já dentro de uma transação. Quem
chama (consumidor ou rotina de prazos) faz o commit; se qualquer coisa falhar,
nada é gravado, nem o evento na outbox.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from psycopg import AsyncConnection

from comum.db import BancoDeDados, buscar_todos, buscar_um
from comum.erros import Problema
from comum.eventos import EventoInvalido, validar_payload
from comum.geo import buscar_cidade, distancia_estrada_km, proximo_dia_util
from comum.logs import correlacao
from comum.outbox import gravar_evento
from comum.relogio import Relogio

from . import SCHEMA, SERVICO
from .regras import CotacaoCandidata, escolher_automaticamente

log = logging.getLogger(__name__)

ESCOLHA_COMPRADOR = "ESCOLHA_COMPRADOR"
AUTOMATICO = "AUTOMATICO_MENOR_PRECO"


@dataclass(frozen=True)
class Prazos:
    rodada_segundos: int = 10          # rodada automática (tempo do kit)
    decisao_segundos: int = 12 * 3600  # prazo para o comprador decidir (D4)


def _iso(momento: datetime) -> str:
    return momento.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class Logistica:
    def __init__(self, relogio: Relogio, prazos: Prazos):
        self.relogio = relogio
        self.prazos = prazos

    # ------------------------------------------------------------------ pedido_criado
    async def abrir_solicitacao(self, conn: AsyncConnection, envelope: dict) -> str | None:
        pedido = validar_payload("pedido_criado", envelope["payload"])
        origem = buscar_cidade(pedido["origem"]["cidade"], pedido["origem"]["uf"])
        destino = buscar_cidade(pedido["destino"]["cidade"], pedido["destino"]["uf"])
        if origem is None:
            raise EventoInvalido(f"Cidade de origem desconhecida: {pedido['origem']}")
        if destino is None:
            raise EventoInvalido(f"Cidade de destino desconhecida: {pedido['destino']}")

        agora = await self.relogio.agora(conn)
        solicitacao_id = str(uuid.uuid4())
        distancia = distancia_estrada_km(origem, destino)
        coleta = proximo_dia_util(agora.date())
        rodada_ate = agora + timedelta(seconds=self.prazos.rodada_segundos)
        prazo_decisao = agora + timedelta(seconds=self.prazos.decisao_segundos)

        criada = await buscar_um(conn, """
            INSERT INTO logistica.solicitacao_frete (
                id, pedido_id, produto_id, produto_nome, valor_carga, comprador_id, fornecedor_id,
                tipo_carga, peso_kg, origem_cidade, origem_uf, origem_lat, origem_lon,
                destino_cidade, destino_uf, destino_lat, destino_lon, distancia_km,
                data_coleta_prevista, data_entrega_desejada, aberta_em, rodada_ate, prazo_decisao_em,
                status, correlation_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, 'ABERTA', %s)
            ON CONFLICT (pedido_id) DO NOTHING
            RETURNING id
        """, (
            solicitacao_id, pedido["pedidoId"], pedido["produtoId"], pedido["produtoNome"], pedido["valorTotal"],
            pedido["compradorId"], pedido["fornecedorId"], pedido["tipoTransporte"], pedido["pesoKg"],
            origem.nome, origem.uf, origem.lat, origem.lon, destino.nome, destino.uf, destino.lat, destino.lon,
            distancia, coleta, pedido.get("dataEntregaDesejada"), agora, rodada_ate, prazo_decisao,
            envelope.get("correlationId"),
        ))
        if criada is None:
            # Outro evento (com outro eventId) para o mesmo pedido: não abre duas solicitações.
            log.info("Pedido já tem solicitação de frete", extra={"dados": {"pedidoId": pedido["pedidoId"]}})
            return None

        await gravar_evento(conn, SCHEMA, SERVICO, "solicitacao_frete_criada", solicitacao_id, {
            "solicitacaoFreteId": solicitacao_id,
            "pedidoId": pedido["pedidoId"],
            "produtoId": pedido["produtoId"],
            "produtoNome": pedido["produtoNome"],
            "compradorId": pedido["compradorId"],
            "fornecedorId": pedido["fornecedorId"],
            "tipoCarga": pedido["tipoTransporte"],
            "pesoKg": float(pedido["pesoKg"]),
            "origem": {"cidade": origem.nome, "uf": origem.uf, "lat": origem.lat, "lon": origem.lon},
            "destino": {"cidade": destino.nome, "uf": destino.uf, "lat": destino.lat, "lon": destino.lon},
            "distanciaKm": distancia,
            "dataColetaPrevista": coleta.isoformat(),
            "prazoDecisaoEm": _iso(prazo_decisao),
            "status": "ABERTA",
        }, envelope.get("correlationId"))
        log.info("Solicitação de frete aberta", extra={"dados": {
            "solicitacaoFreteId": solicitacao_id, "pedidoId": pedido["pedidoId"],
            "origem": f"{origem.nome}/{origem.uf}", "destino": f"{destino.nome}/{destino.uf}",
            "distanciaKm": distancia}})
        return solicitacao_id

    # ------------------------------------------------------------------ cotacao_recebida
    async def registrar_cotacao(self, conn: AsyncConnection, envelope: dict) -> str:
        cotacao = validar_payload("cotacao_recebida", envelope["payload"])

        # FOR UPDATE: trava a solicitação para a cotação e a escolha não se cruzarem.
        solicitacao = await buscar_um(
            conn, "SELECT id, status FROM logistica.solicitacao_frete WHERE id = %s FOR UPDATE",
            (cotacao["solicitacaoFreteId"],))
        if solicitacao is None:
            raise EventoInvalido(f"Solicitação desconhecida: {cotacao['solicitacaoFreteId']}")

        aberta = solicitacao["status"] in ("ABERTA", "SEM_COTACAO", "COTADA")
        status = "VALIDA" if aberta else "RECUSADA_TARDE"
        agora = await self.relogio.agora(conn)
        await conn.execute("""
            INSERT INTO logistica.cotacao (
                id, solicitacao_id, transportadora_id, transportadora_nome, preco, prazo_dias,
                data_entrega_prevista, valida_ate, origem_cotacao, observacoes, status, recebida_em)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (solicitacao_id, transportadora_id) DO NOTHING
        """, (
            cotacao["cotacaoId"], cotacao["solicitacaoFreteId"], cotacao["transportadoraId"],
            cotacao.get("transportadoraNome"), cotacao["preco"], cotacao["prazoDias"],
            cotacao.get("dataEntregaPrevista"), cotacao.get("validaAte"),
            cotacao.get("origemCotacao", "SIMULADA"), cotacao.get("observacoes"), status, agora,
        ))
        if aberta and solicitacao["status"] != "COTADA":
            await conn.execute(
                "UPDATE logistica.solicitacao_frete SET status = 'COTADA', atualizado_em = now() "
                "WHERE id = %s AND status IN ('ABERTA', 'SEM_COTACAO')", (solicitacao["id"],))

        log.info("Cotação recebida", extra={"dados": {
            "solicitacaoFreteId": cotacao["solicitacaoFreteId"], "transportadoraId": cotacao["transportadoraId"],
            "preco": cotacao["preco"], "prazoDias": cotacao["prazoDias"], "situacao": status}})
        return status

    # ------------------------------------------------------------------ escolha do frete
    async def escolher(self, conn: AsyncConnection, solicitacao_id: str, cotacao_id: str | None,
                       criterio: str) -> dict:
        """Escolhe o frete. Sem `cotacao_id`, aplica a regra automática.

        Garantia de escolha única (arquitetura, seção 11.1): a gravação só muda
        o status se ele ainda for COTADA. Quem chegar depois recebe 409.
        """
        solicitacao = await buscar_um(
            conn, "SELECT * FROM logistica.solicitacao_frete WHERE id = %s FOR UPDATE", (solicitacao_id,))
        if solicitacao is None:
            raise Problema(404, "SOLICITACAO_NAO_ENCONTRADA", "Solicitação não encontrada",
                           f"Não existe solicitação de frete {solicitacao_id}.")
        if solicitacao["status"] != "COTADA":
            raise Problema(409, "FRETE_NAO_DISPONIVEL_PARA_ESCOLHA", "Escolha não permitida",
                           f"A solicitação está {solicitacao['status']}; só é possível escolher quando está COTADA.")

        linhas = await buscar_todos(conn, """
            SELECT id, transportadora_id, preco, prazo_dias, data_entrega_prevista
              FROM logistica.cotacao WHERE solicitacao_id = %s AND status = 'VALIDA'
        """, (solicitacao_id,))
        candidatas = {l["id"]: CotacaoCandidata(l["id"], l["transportadora_id"], l["preco"], l["prazo_dias"])
                      for l in linhas}
        if cotacao_id is not None:
            if cotacao_id not in candidatas:
                raise Problema(404, "COTACAO_NAO_ENCONTRADA", "Cotação não encontrada",
                               f"A cotação {cotacao_id} não é uma cotação válida desta solicitação.")
            vencedora = candidatas[cotacao_id]
        else:
            vencedora = escolher_automaticamente(list(candidatas.values()), await self._pontualidade(conn))

        alterada = await conn.execute("""
            UPDATE logistica.solicitacao_frete
               SET status = 'SELECIONADA', cotacao_escolhida_id = %s, criterio = %s, atualizado_em = now()
             WHERE id = %s AND status = 'COTADA'
        """, (vencedora.id, criterio, solicitacao_id))
        if alterada.rowcount != 1:
            raise Problema(409, "FRETE_JA_ESCOLHIDO", "Frete já escolhido",
                           f"A solicitação {solicitacao_id} já teve o frete escolhido.")

        data_prevista = next(l["data_entrega_prevista"] for l in linhas if l["id"] == vencedora.id)
        entrega_id = str(uuid.uuid4())
        await conn.execute("""
            INSERT INTO logistica.entrega (id, pedido_id, tentativa, solicitacao_id, cotacao_id,
                                           transportadora_id, status, prazo_prometido)
            VALUES (%s, %s, 1, %s, %s, %s, 'AGUARDANDO_ALOCACAO', %s)
        """, (entrega_id, solicitacao["pedido_id"], solicitacao_id, vencedora.id,
              vencedora.transportadora_id, data_prevista))

        payload = {
            "pedidoId": solicitacao["pedido_id"],
            "solicitacaoFreteId": solicitacao_id,
            "entregaId": entrega_id,
            "tentativa": 1,
            "cotacaoId": vencedora.id,
            "transportadoraId": vencedora.transportadora_id,
            "preco": float(vencedora.preco),
            "prazoDias": vencedora.prazo_dias,
            "dataEntregaPrevista": data_prevista.isoformat() if data_prevista else None,
            "criterio": criterio,
            "status": "FRETE_SELECIONADO",
        }
        validar_payload("frete_selecionado", payload)
        await gravar_evento(conn, SCHEMA, SERVICO, "frete_selecionado", solicitacao["pedido_id"], payload,
                            solicitacao["correlation_id"])
        log.info("Frete escolhido", extra={"dados": {
            "solicitacaoFreteId": solicitacao_id, "pedidoId": solicitacao["pedido_id"],
            "transportadoraId": vencedora.transportadora_id, "preco": float(vencedora.preco),
            "criterio": criterio, "cotacoesConsideradas": len(candidatas)}})
        return payload

    async def _pontualidade(self, conn: AsyncConnection) -> dict[str, float]:
        linhas = await buscar_todos(conn, """
            SELECT transportadora_id, entregas, entregas_no_prazo FROM logistica.desempenho_transportadora
             WHERE entregas > 0
        """)
        return {l["transportadora_id"]: l["entregas_no_prazo"] / l["entregas"] for l in linhas}

    # ------------------------------------------------------------------ rotina de prazos
    async def verificar_prazos(self, db: BancoDeDados) -> None:
        """Roda a cada segundo, nas duas cópias do serviço.

        FOR UPDATE SKIP LOCKED: se a outra cópia já está tratando uma
        solicitação, esta pula para a próxima. Assim nenhuma é tratada duas
        vezes (decisão D14).
        """
        agora = await self.relogio.agora()

        async with db.transacao() as conn:
            sem_cotacao = await buscar_todos(conn, """
                UPDATE logistica.solicitacao_frete SET status = 'SEM_COTACAO', atualizado_em = now()
                 WHERE status = 'ABERTA' AND rodada_ate <= %s
                RETURNING id, pedido_id, correlation_id
            """, (agora,))
        for linha in sem_cotacao:
            with correlacao(linha["correlation_id"]):
                log.warning("Rodada automática terminou sem cotação", extra={"dados": {
                    "solicitacaoFreteId": linha["id"], "pedidoId": linha["pedido_id"]}})

        while await self._escolher_proxima_vencida(db, agora):
            pass
        while await self._encerrar_proxima_sem_cotacao(db, agora):
            pass

    async def _escolher_proxima_vencida(self, db: BancoDeDados, agora: datetime) -> bool:
        async with db.transacao() as conn:
            linha = await buscar_um(conn, """
                SELECT id, correlation_id FROM logistica.solicitacao_frete
                 WHERE status = 'COTADA' AND prazo_decisao_em <= %s
                 ORDER BY prazo_decisao_em LIMIT 1
                 FOR UPDATE SKIP LOCKED
            """, (agora,))
            if linha is None:
                return False
            with correlacao(linha["correlation_id"]):
                await self.escolher(conn, linha["id"], None, AUTOMATICO)
            return True

    async def _encerrar_proxima_sem_cotacao(self, db: BancoDeDados, agora: datetime) -> bool:
        async with db.transacao() as conn:
            linha = await buscar_um(conn, """
                SELECT id, pedido_id, correlation_id FROM logistica.solicitacao_frete
                 WHERE status = 'SEM_COTACAO' AND prazo_decisao_em <= %s
                 ORDER BY prazo_decisao_em LIMIT 1
                 FOR UPDATE SKIP LOCKED
            """, (agora,))
            if linha is None:
                return False
            with correlacao(linha["correlation_id"]):
                await self._encerrar_sem_cotacao(conn, linha, agora)
            return True

    async def _encerrar_sem_cotacao(self, conn: AsyncConnection, linha: dict, agora: datetime) -> None:
        await conn.execute(
            "UPDATE logistica.solicitacao_frete SET status = 'INDISPONIVEL', atualizado_em = now() "
            "WHERE id = %s AND status = 'SEM_COTACAO'", (linha["id"],))
        await gravar_evento(conn, SCHEMA, SERVICO, "frete_indisponivel", linha["pedido_id"], {
            "pedidoId": linha["pedido_id"],
            "solicitacaoFreteId": linha["id"],
            "motivo": "SEM_COTACAO",
            "detalhe": "Nenhuma transportadora cotou dentro do prazo de decisão",
            "ocorridoEm": _iso(agora),
        }, linha["correlation_id"])
        log.warning("Frete indisponível: prazo venceu sem cotação", extra={"dados": {
            "solicitacaoFreteId": linha["id"], "pedidoId": linha["pedido_id"]}})


def para_json(valor):
    """Converte valores do banco (Decimal, datas) para JSON."""
    if isinstance(valor, Decimal):
        return float(valor)
    if isinstance(valor, datetime):
        return _iso(valor)
    if hasattr(valor, "isoformat"):
        return valor.isoformat()
    return valor


def linha_para_json(linha: dict) -> dict:
    return {chave: para_json(valor) for chave, valor in linha.items()}
