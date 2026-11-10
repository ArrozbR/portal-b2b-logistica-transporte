"""Regras de negócio da logística.

Fluxo:
    pedido_criado ──► abrir_solicitacao ──► solicitacao_frete_criada
    cotacao_recebida ──► registrar_cotacao (a primeira avisa o comprador)
    rodada de 10 s sem cotação ──► SEM_COTACAO (avisa comprador e fornecedor)
    comprador escolhe, clica em "automático" ou o prazo de 12 h vence
        ──► escolher ──► frete_selecionado
    prazo de 12 h vence sem cotação ──► frete_indisponivel
    pedido_atualizado CANCELADO ──► cancelar_pedido
    administrador ajusta o relógio ──► relogio_ajustado

Todas as funções recebem a conexão `conn` já dentro de uma transação. Quem
chama (consumidor, rotina de prazos ou rota da API) faz o commit; se qualquer
coisa falhar, nada é gravado, nem o evento na outbox nem a notificação.
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
from comum.relogio import EstadoRelogio, Relogio, gravar_estado, reajustar

from . import SCHEMA, SERVICO
from .notificacoes import (COMPRADOR, FORNECEDOR, notificar, texto_cotacoes_disponiveis, texto_frete_escolhido,
                           texto_frete_indisponivel, texto_sem_cotacao, texto_sem_transportadora,
                           texto_transportadora_trocada)
from .regras import CotacaoCandidata, escolher_automaticamente

log = logging.getLogger(__name__)

ESCOLHA_COMPRADOR = "ESCOLHA_COMPRADOR"
AUTOMATICO = "AUTOMATICO_MENOR_PRECO"

STATUS_ABERTOS = ("ABERTA", "COTADA", "SEM_COTACAO")
STATUS_ENTREGA_ATIVA = ("AGUARDANDO_ALOCACAO", "AGUARDANDO_COLETA", "EM_TRANSITO")


@dataclass(frozen=True)
class Prazos:
    rodada_segundos: int = 10          # rodada automática (tempo do kit), em HORA REAL
    decisao_segundos: int = 12 * 3600  # prazo para o comprador decidir (D4), no relógio do módulo


def iso(momento: datetime) -> str:
    return momento.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def agora_real() -> datetime:
    return datetime.now(timezone.utc)


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

        if await buscar_um(conn, "SELECT 1 FROM logistica.pedido_cancelado WHERE pedido_id = %s",
                           (pedido["pedidoId"],)):
            log.info("Pedido já tinha sido cancelado; solicitação não aberta",
                     extra={"dados": {"pedidoId": pedido["pedidoId"]}})
            return None

        agora = await self.relogio.agora(conn)
        solicitacao_id = str(uuid.uuid4())
        distancia = distancia_estrada_km(origem, destino)
        coleta = proximo_dia_util(agora.date())
        rodada_ate = agora_real() + timedelta(seconds=self.prazos.rodada_segundos)
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
            "prazoDecisaoEm": iso(prazo_decisao),
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
        solicitacao = await buscar_um(conn, """
            SELECT id, pedido_id, comprador_id, status, prazo_decisao_em
              FROM logistica.solicitacao_frete WHERE id = %s FOR UPDATE
        """, (cotacao["solicitacaoFreteId"],))
        if solicitacao is None:
            raise EventoInvalido(f"Solicitação desconhecida: {cotacao['solicitacaoFreteId']}")

        aberta = solicitacao["status"] in STATUS_ABERTOS
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
            mudou = await conn.execute(
                "UPDATE logistica.solicitacao_frete SET status = 'COTADA', atualizado_em = now() "
                "WHERE id = %s AND status IN ('ABERTA', 'SEM_COTACAO')", (solicitacao["id"],))
            if mudou.rowcount == 1:  # primeira cotação: avisa o comprador
                await notificar(conn, empresa_id=solicitacao["comprador_id"], papel=COMPRADOR,
                                tipo="COTACOES_DISPONIVEIS",
                                texto=texto_cotacoes_disponiveis(solicitacao["pedido_id"],
                                                                 solicitacao["prazo_decisao_em"]),
                                pedido_id=solicitacao["pedido_id"], solicitacao_id=solicitacao["id"], agora=agora)

        log.info("Cotação recebida", extra={"dados": {
            "solicitacaoFreteId": cotacao["solicitacaoFreteId"], "transportadoraId": cotacao["transportadoraId"],
            "preco": cotacao["preco"], "prazoDias": cotacao["prazoDias"], "situacao": status}})
        return status

    # ------------------------------------------------------------------ escolha do frete
    async def escolher(self, conn: AsyncConnection, solicitacao_id: str, cotacao_id: str | None,
                       criterio: str, escolhida_por: str | None = None) -> dict:
        """Escolhe o frete. Sem `cotacao_id`, aplica a regra automática.

        `escolhida_por` é o usuário que escolheu (None = rotina de prazos).

        Garantia de escolha única (arquitetura, seção 11.1): a gravação só muda
        o status se ele ainda for COTADA. Quem chegar depois recebe 409.
        """
        solicitacao = await buscar_um(
            conn, "SELECT * FROM logistica.solicitacao_frete WHERE id = %s FOR UPDATE", (solicitacao_id,))
        if solicitacao is None:
            raise Problema(404, "SOLICITACAO_NAO_ENCONTRADA", "Solicitação não encontrada",
                           f"Não existe solicitação de frete {solicitacao_id}.")
        self._conferir_status_para_escolha(solicitacao)

        agora = await self.relogio.agora(conn)
        if criterio == ESCOLHA_COMPRADOR and agora > solicitacao["prazo_decisao_em"]:
            raise Problema(409, "PRAZO_DE_ESCOLHA_ENCERRADO", "Prazo de escolha encerrado",
                           "O prazo para escolher uma cotação acabou; o frete será escolhido pela regra automática.")

        linhas = await buscar_todos(conn, """
            SELECT id, transportadora_id, transportadora_nome, preco, prazo_dias, data_entrega_prevista
              FROM logistica.cotacao WHERE solicitacao_id = %s AND status = 'VALIDA'
        """, (solicitacao_id,))
        cotacoes = {l["id"]: l for l in linhas}
        candidatas = [CotacaoCandidata(l["id"], l["transportadora_id"], l["preco"], l["prazo_dias"]) for l in linhas]
        if cotacao_id is not None:
            if cotacao_id not in cotacoes:
                raise Problema(404, "COTACAO_NAO_ENCONTRADA", "Cotação não encontrada",
                               f"A cotação {cotacao_id} não é uma cotação válida desta solicitação.")
            vencedora_id = cotacao_id
        else:
            vencedora_id = escolher_automaticamente(candidatas, await self._pontualidade(conn)).id
        vencedora = cotacoes[vencedora_id]

        alterada = await conn.execute("""
            UPDATE logistica.solicitacao_frete
               SET status = 'SELECIONADA', cotacao_escolhida_id = %s, criterio = %s,
                   escolhida_por = %s, escolhida_em = %s, atualizado_em = now()
             WHERE id = %s AND status = 'COTADA'
        """, (vencedora_id, criterio, escolhida_por, agora, solicitacao_id))
        if alterada.rowcount != 1:
            raise Problema(409, "FRETE_JA_ESCOLHIDO", "Frete já escolhido",
                           f"A solicitação {solicitacao_id} já teve o frete escolhido.")

        payload = await self._criar_entrega_e_publicar(conn, solicitacao, vencedora, criterio, tentativa=1)

        texto = texto_frete_escolhido(solicitacao["pedido_id"], vencedora["transportadora_nome"]
                                      or vencedora["transportadora_id"], vencedora["preco"],
                                      vencedora["prazo_dias"], automatico=criterio == AUTOMATICO)
        destinatarios = [(solicitacao["fornecedor_id"], FORNECEDOR)]
        if escolhida_por is None:  # o comprador não clicou: precisa ser avisado
            destinatarios.append((solicitacao["comprador_id"], COMPRADOR))
        for empresa_id, papel in destinatarios:
            await notificar(conn, empresa_id=empresa_id, papel=papel, tipo="FRETE_ESCOLHIDO", texto=texto,
                            pedido_id=solicitacao["pedido_id"], solicitacao_id=solicitacao_id, agora=agora)

        log.info("Frete escolhido", extra={"dados": {
            "solicitacaoFreteId": solicitacao_id, "pedidoId": solicitacao["pedido_id"],
            "transportadoraId": vencedora["transportadora_id"], "preco": float(vencedora["preco"]),
            "criterio": criterio, "escolhidaPor": escolhida_por, "cotacoesConsideradas": len(candidatas)}})
        return {**payload, "transportadoraNome": vencedora["transportadora_nome"]}

    async def _criar_entrega_e_publicar(self, conn: AsyncConnection, solicitacao: dict, cotacao: dict,
                                        criterio: str, tentativa: int) -> dict:
        """Cria a entrega da cotação escolhida e grava o frete_selecionado na outbox."""
        entrega_id = str(uuid.uuid4())
        await conn.execute("""
            INSERT INTO logistica.entrega (id, pedido_id, tentativa, solicitacao_id, cotacao_id, transportadora_id,
                                           transportadora_nome, status, prazo_prometido)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'AGUARDANDO_ALOCACAO', %s)
        """, (entrega_id, solicitacao["pedido_id"], tentativa, solicitacao["id"], cotacao["id"],
              cotacao["transportadora_id"], cotacao["transportadora_nome"], cotacao["data_entrega_prevista"]))

        data_prevista = cotacao["data_entrega_prevista"]
        payload = {
            "pedidoId": solicitacao["pedido_id"],
            "solicitacaoFreteId": solicitacao["id"],
            "entregaId": entrega_id,
            "tentativa": tentativa,
            "cotacaoId": cotacao["id"],
            "transportadoraId": cotacao["transportadora_id"],
            "preco": float(cotacao["preco"]),
            "prazoDias": cotacao["prazo_dias"],
            "dataEntregaPrevista": data_prevista.isoformat() if data_prevista else None,
            "criterio": criterio,
            "status": "FRETE_SELECIONADO",
        }
        validar_payload("frete_selecionado", payload)
        await gravar_evento(conn, SCHEMA, SERVICO, "frete_selecionado", solicitacao["pedido_id"], payload,
                            solicitacao["correlation_id"])
        return payload

    # ------------------------------------------------------------------ viagem recusada (D20)
    async def trocar_transportadora(self, conn: AsyncConnection, entrega: dict) -> str:
        """A transportadora escolhida recusou a viagem (sem motorista ou caminhão livre).

        Passa para a próxima cotação pela regra automática. Sem cotação
        restante, o frete fica indisponível. A troca é uma gravação condicional
        (`WHERE cotacao_escolhida_id = <cotação recusada>`): se a mesma recusa
        chegar duas vezes, a segunda não troca de novo.
        """
        await conn.execute("UPDATE logistica.entrega SET status = 'RECUSADA', atualizado_em = now() WHERE id = %s",
                           (entrega["id"],))
        await conn.execute("UPDATE logistica.cotacao SET status = 'VIAGEM_RECUSADA' WHERE id = %s",
                           (entrega["cotacao_id"],))
        solicitacao = await buscar_um(
            conn, "SELECT * FROM logistica.solicitacao_frete WHERE id = %s FOR UPDATE", (entrega["solicitacao_id"],))
        agora = await self.relogio.agora(conn)
        linhas = await buscar_todos(conn, """
            SELECT id, transportadora_id, transportadora_nome, preco, prazo_dias, data_entrega_prevista
              FROM logistica.cotacao WHERE solicitacao_id = %s AND status = 'VALIDA'
        """, (solicitacao["id"],))
        destinatarios = ((solicitacao["comprador_id"], COMPRADOR), (solicitacao["fornecedor_id"], FORNECEDOR))

        if not linhas:
            alterada = await conn.execute(
                "UPDATE logistica.solicitacao_frete SET status = 'INDISPONIVEL', atualizado_em = now() "
                "WHERE id = %s AND status = 'SELECIONADA' AND cotacao_escolhida_id = %s",
                (solicitacao["id"], entrega["cotacao_id"]))
            if alterada.rowcount == 1:
                await self._publicar_frete_indisponivel(conn, solicitacao, "SEM_TRANSPORTADORA_DISPONIVEL",
                                                        "Nenhuma transportadora que cotou tem frota livre", agora)
                for empresa_id, papel in destinatarios:
                    await notificar(conn, empresa_id=empresa_id, papel=papel, tipo="FRETE_INDISPONIVEL",
                                    texto=texto_sem_transportadora(solicitacao["pedido_id"]),
                                    pedido_id=solicitacao["pedido_id"], solicitacao_id=solicitacao["id"], agora=agora)
            return "indisponivel"

        candidatas = [CotacaoCandidata(l["id"], l["transportadora_id"], l["preco"], l["prazo_dias"]) for l in linhas]
        nova_id = escolher_automaticamente(candidatas, await self._pontualidade(conn)).id
        nova = next(l for l in linhas if l["id"] == nova_id)
        alterada = await conn.execute("""
            UPDATE logistica.solicitacao_frete
               SET cotacao_escolhida_id = %s, criterio = %s, atualizado_em = now()
             WHERE id = %s AND status = 'SELECIONADA' AND cotacao_escolhida_id = %s
        """, (nova_id, AUTOMATICO, solicitacao["id"], entrega["cotacao_id"]))
        if alterada.rowcount != 1:
            log.info("Troca de transportadora já feita antes", extra={"dados": {"entregaId": entrega["id"]}})
            return "ja_trocada"

        await self._criar_entrega_e_publicar(conn, solicitacao, nova, AUTOMATICO, tentativa=entrega["tentativa"] + 1)
        texto = texto_transportadora_trocada(solicitacao["pedido_id"], entrega["transportadora_nome"]
                                             or entrega["transportadora_id"], nova["transportadora_nome"]
                                             or nova["transportadora_id"], nova["preco"], nova["prazo_dias"])
        for empresa_id, papel in destinatarios:
            await notificar(conn, empresa_id=empresa_id, papel=papel, tipo="TRANSPORTADORA_TROCADA", texto=texto,
                            pedido_id=solicitacao["pedido_id"], solicitacao_id=solicitacao["id"], agora=agora)
        log.warning("Transportadora trocada após recusa da viagem", extra={"dados": {
            "pedidoId": solicitacao["pedido_id"], "recusou": entrega["transportadora_id"],
            "nova": nova["transportadora_id"], "tentativa": entrega["tentativa"] + 1}})
        return "trocada"

    async def _publicar_frete_indisponivel(self, conn: AsyncConnection, solicitacao: dict, motivo: str,
                                           detalhe: str, agora: datetime) -> None:
        payload = {"pedidoId": solicitacao["pedido_id"], "solicitacaoFreteId": solicitacao["id"],
                   "motivo": motivo, "detalhe": detalhe, "ocorridoEm": iso(agora)}
        validar_payload("frete_indisponivel", payload)
        await gravar_evento(conn, SCHEMA, SERVICO, "frete_indisponivel", solicitacao["pedido_id"], payload,
                            solicitacao["correlation_id"])

    @staticmethod
    def _conferir_status_para_escolha(solicitacao: dict) -> None:
        status = solicitacao["status"]
        if status == "COTADA":
            return
        if status == "SELECIONADA":
            raise Problema(409, "FRETE_JA_ESCOLHIDO", "Frete já escolhido",
                           f"A solicitação {solicitacao['id']} já teve o frete escolhido.")
        if status in ("ABERTA", "SEM_COTACAO"):
            raise Problema(409, "SEM_COTACAO_PARA_ESCOLHER", "Ainda não há cotação",
                           "Nenhuma transportadora cotou esta solicitação ainda.")
        raise Problema(409, "SOLICITACAO_ENCERRADA", "Solicitação encerrada",
                       f"A solicitação está {status} e não aceita mais escolha de frete.")

    async def _pontualidade(self, conn: AsyncConnection) -> dict[str, float]:
        linhas = await buscar_todos(conn, """
            SELECT transportadora_id, entregas, entregas_no_prazo FROM logistica.desempenho_transportadora
             WHERE entregas > 0
        """)
        return {l["transportadora_id"]: l["entregas_no_prazo"] / l["entregas"] for l in linhas}

    # ------------------------------------------------------------------ pedido_atualizado
    async def cancelar_pedido(self, conn: AsyncConnection, envelope: dict) -> str:
        """Pedido cancelado pelo grupo de Pedidos: encerra a solicitação ou a entrega."""
        dados = validar_payload("pedido_atualizado", envelope["payload"])
        novo_status = (dados.get("novoStatus") or dados.get("status") or "").upper()
        if novo_status != "CANCELADO":
            return "ignorado"  # outras mudanças de status do pedido não afetam a logística
        pedido_id = dados["pedidoId"]

        solicitacao = await buscar_um(
            conn, "SELECT id, status FROM logistica.solicitacao_frete WHERE pedido_id = %s FOR UPDATE",
            (pedido_id,))
        if solicitacao is None:
            # O cancelamento chegou antes do pedido_criado (tópicos diferentes não têm ordem
            # garantida entre si). Guarda para não abrir a solicitação quando o pedido chegar.
            await conn.execute(
                "INSERT INTO logistica.pedido_cancelado (pedido_id) VALUES (%s) ON CONFLICT DO NOTHING",
                (pedido_id,))
            log.info("Cancelamento recebido antes do pedido; registrado", extra={"dados": {"pedidoId": pedido_id}})
            return "registrado"

        if solicitacao["status"] in STATUS_ABERTOS:
            await conn.execute(
                "UPDATE logistica.solicitacao_frete SET status = 'CANCELADA', atualizado_em = now() "
                "WHERE id = %s", (solicitacao["id"],))
        entregas = await conn.execute("""
            UPDATE logistica.entrega SET status = 'CANCELADA', atualizado_em = now()
             WHERE pedido_id = %s AND status = ANY(%s)
        """, (pedido_id, list(STATUS_ENTREGA_ATIVA)))
        log.info("Pedido cancelado", extra={"dados": {
            "pedidoId": pedido_id, "statusSolicitacao": solicitacao["status"],
            "entregasCanceladas": entregas.rowcount}})
        return "cancelado"

    # ------------------------------------------------------------------ relógio do módulo
    async def ajustar_relogio(self, conn: AsyncConnection, fator: float, avancar: timedelta,
                              ajustado_por: str) -> EstadoRelogio:
        """Muda a velocidade do relógio (e, se pedido, avança) sem salto para trás (D18)."""
        # Trava: dois administradores ajustando ao mesmo tempo não geram a mesma versão.
        await conn.execute("SELECT pg_advisory_xact_lock(hashtext('relogio:logistica'))")
        self.relogio.invalidar()
        atual = await self.relogio.estado(conn)
        novo = reajustar(atual, agora_real(), fator, avancar)
        await gravar_estado(conn, SCHEMA, novo)
        await gravar_evento(conn, SCHEMA, SERVICO, "relogio_ajustado", "relogio",
                            {**novo.para_evento(), "ajustadoPor": ajustado_por})
        self.relogio.invalidar()
        log.warning("Relógio do módulo ajustado", extra={"dados": {
            "fator": fator, "avancarHoras": avancar.total_seconds() / 3600, "versao": novo.versao,
            "horaDoModulo": iso(novo.base_virtual), "ajustadoPor": ajustado_por}})
        return novo

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
                RETURNING id, pedido_id, comprador_id, fornecedor_id, prazo_decisao_em, correlation_id
            """, (agora_real(),))
            for linha in sem_cotacao:
                with correlacao(linha["correlation_id"]):
                    texto = texto_sem_cotacao(linha["pedido_id"], linha["prazo_decisao_em"])
                    for empresa_id, papel in ((linha["comprador_id"], COMPRADOR), (linha["fornecedor_id"], FORNECEDOR)):
                        await notificar(conn, empresa_id=empresa_id, papel=papel, tipo="SEM_COTACAO", texto=texto,
                                        pedido_id=linha["pedido_id"], solicitacao_id=linha["id"], agora=agora)
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
                SELECT id, pedido_id, comprador_id, fornecedor_id, correlation_id FROM logistica.solicitacao_frete
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
        await self._publicar_frete_indisponivel(conn, linha, "SEM_COTACAO",
                                                "Nenhuma transportadora cotou dentro do prazo de decisão", agora)
        texto = texto_frete_indisponivel(linha["pedido_id"])
        for empresa_id, papel in ((linha["comprador_id"], COMPRADOR), (linha["fornecedor_id"], FORNECEDOR)):
            await notificar(conn, empresa_id=empresa_id, papel=papel, tipo="FRETE_INDISPONIVEL", texto=texto,
                            pedido_id=linha["pedido_id"], solicitacao_id=linha["id"], agora=agora)
        log.warning("Frete indisponível: prazo venceu sem cotação", extra={"dados": {
            "solicitacaoFreteId": linha["id"], "pedidoId": linha["pedido_id"]}})


def para_json(valor):
    """Converte valores do banco (Decimal, datas) para JSON."""
    if isinstance(valor, Decimal):
        return float(valor)
    if isinstance(valor, datetime):
        return iso(valor)
    if hasattr(valor, "isoformat"):
        return valor.isoformat()
    return valor


def linha_para_json(linha: dict) -> dict:
    return {chave: para_json(valor) for chave, valor in linha.items()}
