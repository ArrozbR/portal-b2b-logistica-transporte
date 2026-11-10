"""Regras de negócio das transportadoras.

    solicitacao_frete_criada ──► cotar_automaticamente ──► cotacao_recebida (uma por transportadora)
    frete_selecionado        ──► escalar ──► rastreio_atualizado (VIAGEM_ALOCADA ou VIAGEM_RECUSADA)
    a cada 30 s              ──► avancar_viagens ──► rastreio_atualizado (coleta, posição, parada, atraso, entrega)
    pedido_atualizado        ──► cancelar_viagem (libera motorista e veículo)
    relogio_ajustado         ──► sincronizar_relogio

Só as transportadoras simuladas (D3) cotam sozinhas, e só se tiverem um
motorista e um veículo livres e compatíveis com a carga (D20).
"""

import logging
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from psycopg import AsyncConnection
from psycopg.types.json import Jsonb

from comum.db import BancoDeDados, buscar_todos, buscar_um
from comum.eventos import EventoInvalido, validar_payload
from comum.geo import Cidade, interpolar_rota, somar_dias_uteis
from comum.logs import correlacao
from comum.outbox import gravar_evento
from comum.relogio import EstadoRelogio, Relogio, gravar_estado

from . import SCHEMA, SERVICO
from .cotacao import PerfilTransportadora, RegraCotacao, atende, calcular
from .simulacao import EstadoViagem, EventoViagem, cnh_permite, embaralhar, mascarar_cnh, passo, planejar

log = logging.getLogger(__name__)

# Namespace fixo: a mesma solicitação + transportadora gera sempre o mesmo cotacaoId.
NAMESPACE_COTACAO = uuid.UUID("6f1d2c3e-4b5a-4c7d-9e8f-0a1b2c3d4e5f")

# Há um par motorista + veículo livre e compatível? (D20)
FROTA_LIVRE = """
    EXISTS (
        SELECT 1 FROM transportadoras.veiculo v
          JOIN transportadoras.motorista m ON m.transportadora_id = v.transportadora_id
         WHERE v.transportadora_id = t.id
           AND v.ativo AND v.viagem_atual_id IS NULL
           AND %(tipo_carga)s = ANY(v.tipos_carga) AND v.capacidade_kg >= %(peso_kg)s
           AND m.ativo AND m.viagem_atual_id IS NULL AND m.cnh_validade >= %(hoje)s
           AND m.cnh_categoria >= v.categoria_cnh_exigida
    )
"""


def id_da_cotacao(solicitacao_id: str, transportadora_id: str) -> str:
    return str(uuid.uuid5(NAMESPACE_COTACAO, f"{solicitacao_id}:{transportadora_id}"))


def iso(momento: datetime) -> str:
    return momento.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _ponto(lat_lon) -> dict:
    return {"lat": float(lat_lon[0]), "lon": float(lat_lon[1])}


class Transportadoras:
    def __init__(self, relogio: Relogio, intervalo_rastreio_segundos: int = 30):
        self.relogio = relogio
        self.intervalo = intervalo_rastreio_segundos

    # ------------------------------------------------------------------ cotação
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
        emitidas, sem_frota = 0, []
        for perfil, regra, tem_frota in await self._transportadoras_simuladas(
                conn, solicitacao["tipoCarga"], solicitacao["pesoKg"], agora.date()):
            if not atende(perfil, solicitacao["tipoCarga"], origem["uf"], destino["uf"]):
                continue
            if not tem_frota:
                sem_frota.append(perfil.id)
                continue
            preco, prazo = calcular(regra, solicitacao["distanciaKm"], solicitacao["pesoKg"], solicitacao["tipoCarga"])
            await self._emitir(conn, sid, perfil, preco, prazo, somar_dias_uteis(coleta, prazo),
                               solicitacao["prazoDecisaoEm"], agora, envelope.get("correlationId"))
            emitidas += 1

        log.info("Cotações simuladas emitidas", extra={"dados": {
            "solicitacaoFreteId": sid, "tipoCarga": solicitacao["tipoCarga"], "quantidade": emitidas,
            "semFrotaLivre": sem_frota}})
        return emitidas

    async def _transportadoras_simuladas(self, conn: AsyncConnection, tipo_carga: str, peso_kg: float,
                                         hoje: date) -> list[tuple[PerfilTransportadora, RegraCotacao, bool]]:
        linhas = await buscar_todos(conn, f"""
            SELECT t.id, t.nome, t.tipos_carga, t.ufs_atendidas,
                   r.preco_minimo, r.tarifa_km, r.tarifa_ton, r.fator_tipo_carga, r.km_por_dia, r.prazo_base_dias,
                   {FROTA_LIVRE} AS tem_frota
              FROM transportadoras.transportadora t
              JOIN transportadoras.regra_cotacao r ON r.transportadora_id = t.id
             WHERE t.ativa AND t.simulada
             ORDER BY t.id
        """, {"tipo_carga": tipo_carga, "peso_kg": peso_kg, "hoje": hoje})
        resultado = []
        for l in linhas:
            perfil = PerfilTransportadora(
                id=l["id"], nome=l["nome"], tipos_carga=tuple(l["tipos_carga"]),
                ufs_atendidas=tuple(l["ufs_atendidas"]) if l["ufs_atendidas"] else None)
            regra = RegraCotacao(
                preco_minimo=l["preco_minimo"], tarifa_km=l["tarifa_km"], tarifa_ton=l["tarifa_ton"],
                km_por_dia=l["km_por_dia"], prazo_base_dias=l["prazo_base_dias"],
                fator_tipo_carga={k: Decimal(str(v)) for k, v in (l["fator_tipo_carga"] or {}).items()})
            resultado.append((perfil, regra, l["tem_frota"]))
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

    # ------------------------------------------------------------------ escala (frete_selecionado)
    async def escalar(self, conn: AsyncConnection, envelope: dict) -> str:
        """A transportadora venceu: sorteia motorista e veículo livres e compatíveis e agenda a viagem (D19, D20)."""
        frete = validar_payload("frete_selecionado", envelope["payload"])
        transportadora = await buscar_um(conn, """
            SELECT t.id, t.nome, t.telefone_contato, t.prob_atraso, r.km_por_dia
              FROM transportadoras.transportadora t
              JOIN transportadoras.regra_cotacao r ON r.transportadora_id = t.id
             WHERE t.id = %s
        """, (frete["transportadoraId"],))
        if transportadora is None:
            log.info("Frete de transportadora que não é deste serviço", extra={"dados": frete})
            return "ignorado"
        if await buscar_um(conn, "SELECT 1 FROM transportadoras.viagem WHERE entrega_id = %s", (frete["entregaId"],)):
            return "ja_escalada"

        solicitacao = await buscar_um(conn, "SELECT * FROM transportadoras.solicitacao_recebida WHERE id = %s",
                                      (frete["solicitacaoFreteId"],))
        if solicitacao is None:
            raise EventoInvalido(f"Solicitação desconhecida: {frete['solicitacaoFreteId']}")

        agora = await self.relogio.agora(conn)
        id_correlacao = envelope.get("correlationId")
        base = {"pedidoId": frete["pedidoId"], "entregaId": frete["entregaId"],
                "transportadoraId": transportadora["id"]}

        veiculos = await buscar_todos(conn, """
            SELECT id, placa, tipo, categoria_cnh_exigida FROM transportadoras.veiculo
             WHERE transportadora_id = %s AND ativo AND viagem_atual_id IS NULL
               AND %s = ANY(tipos_carga) AND capacidade_kg >= %s
             ORDER BY id
        """, (transportadora["id"], solicitacao["tipo_carga"], solicitacao["peso_kg"]))
        motoristas = await buscar_todos(conn, """
            SELECT id, nome, telefone, cnh_numero, cnh_categoria FROM transportadoras.motorista
             WHERE transportadora_id = %s AND ativo AND viagem_atual_id IS NULL AND cnh_validade >= %s
             ORDER BY id
        """, (transportadora["id"], agora.date()))

        viagem_id = str(uuid.uuid4())
        veiculo, motorista = await self._reservar_frota(conn, viagem_id, frete["entregaId"], veiculos, motoristas)
        if veiculo is None or motorista is None:
            motivo = "SEM_VEICULO" if not veiculos else "SEM_MOTORISTA"
            await self._publicar(conn, {**base, "sequencia": 1, "tipo": "VIAGEM_RECUSADA", "motivo": motivo,
                                        "descricao": "A transportadora não tem motorista e veículo livres para esta carga.",
                                        "ocorridoEm": iso(agora)}, id_correlacao)
            log.warning("Viagem recusada: sem frota livre", extra={"dados": {**base, "motivo": motivo}})
            return "recusada"

        semente = frete["entregaId"]
        data_prometida = date.fromisoformat(frete["dataEntregaPrevista"]) if frete.get("dataEntregaPrevista") else None
        plano = planejar(semente, agora, float(solicitacao["distancia_km"]), transportadora["km_por_dia"],
                         float(transportadora["prob_atraso"]), data_prometida)
        origem = Cidade(solicitacao["origem_cidade"], solicitacao["origem_uf"],
                        float(solicitacao["origem_lat"]), float(solicitacao["origem_lon"]))
        destino = Cidade(solicitacao["destino_cidade"], solicitacao["destino_uf"],
                         float(solicitacao["destino_lat"]), float(solicitacao["destino_lon"]))
        rota = interpolar_rota(origem, destino)

        await conn.execute("""
            INSERT INTO transportadoras.viagem (
                id, entrega_id, pedido_id, solicitacao_id, transportadora_id, motorista_id, veiculo_id, rota,
                data_prometida, coleta_em, chegada_prevista, atraso_horas, marco_tempo, sequencia, status,
                proximo_passo_em, correlation_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1, 'AGENDADA',
                    now() + make_interval(secs => %s), %s)
        """, (viagem_id, frete["entregaId"], frete["pedidoId"], solicitacao["id"], transportadora["id"],
              motorista["id"], veiculo["id"], Jsonb(rota), data_prometida, plano.coleta_em,
              plano.chegada_planejada, plano.atraso_horas, plano.coleta_em, self.intervalo, id_correlacao))

        await self._publicar(conn, {
            **base, "sequencia": 1, "tipo": "VIAGEM_ALOCADA",
            "descricao": f"Motorista {motorista['nome']} e veículo {veiculo['placa']} escalados.",
            "motorista": {"nome": motorista["nome"], "telefone": motorista["telefone"],
                          "cnhMascarada": mascarar_cnh(motorista["cnh_numero"])},
            "veiculo": {"placa": veiculo["placa"], "tipo": veiculo["tipo"]},
            "transportadora": {"nome": transportadora["nome"], "telefone": transportadora["telefone_contato"]},
            "coletaPrevista": iso(plano.coleta_em),
            "previsaoChegada": iso(plano.chegada_planejada),
            "rota": [list(p) for p in rota],
            "posicao": _ponto(rota[0]),
            "progresso": 0.0,
            "ocorridoEm": iso(agora),
        }, id_correlacao)
        log.info("Viagem agendada", extra={"dados": {
            **base, "motorista": motorista["nome"], "veiculo": veiculo["placa"],
            "coleta": iso(plano.coleta_em), "chegadaPlanejada": iso(plano.chegada_planejada),
            "atrasoSorteadoHoras": plano.atraso_horas}})
        return "agendada"

    async def _reservar_frota(self, conn: AsyncConnection, viagem_id: str, semente: str,
                              veiculos: list[dict], motoristas: list[dict]) -> tuple[dict | None, dict | None]:
        """Sorteia e reserva um veículo e um motorista compatíveis.

        A reserva é uma gravação condicional (`WHERE viagem_atual_id IS NULL`):
        se outra viagem, na outra cópia do serviço, pegou o mesmo caminhão um
        instante antes, a gravação não altera nada e o próximo do sorteio é
        tentado. Assim o mesmo caminhão nunca fica em duas viagens.
        """
        for veiculo in embaralhar(semente, veiculos):
            aptos = [m for m in motoristas if cnh_permite(m["cnh_categoria"], veiculo["categoria_cnh_exigida"])]
            if not aptos or not await self._reservar(conn, "veiculo", veiculo["id"], viagem_id):
                continue
            for motorista in embaralhar(semente, aptos):
                if await self._reservar(conn, "motorista", motorista["id"], viagem_id):
                    return veiculo, motorista
            await conn.execute(  # nenhum motorista: devolve o veículo
                "UPDATE transportadoras.veiculo SET viagem_atual_id = NULL WHERE id = %s AND viagem_atual_id = %s",
                (veiculo["id"], viagem_id))
        return None, None

    @staticmethod
    async def _reservar(conn: AsyncConnection, tabela: str, item_id: str, viagem_id: str) -> bool:
        tabelas = {"veiculo": "transportadoras.veiculo", "motorista": "transportadoras.motorista"}
        cursor = await conn.execute(
            f"UPDATE {tabelas[tabela]} SET viagem_atual_id = %s WHERE id = %s AND viagem_atual_id IS NULL",
            (viagem_id, item_id))
        return cursor.rowcount == 1

    async def _publicar(self, conn: AsyncConnection, payload: dict, id_correlacao: str | None) -> None:
        validar_payload("rastreio_atualizado", payload)
        await gravar_evento(conn, SCHEMA, SERVICO, "rastreio_atualizado", payload["pedidoId"], payload, id_correlacao)

    # ------------------------------------------------------------------ simulação (a cada 30 s)
    async def avancar_viagens(self, db: BancoDeDados) -> None:
        """Roda a cada segundo nas duas cópias; cada viagem só anda quando chega a hora do próximo passo."""
        while await self._avancar_proxima(db):
            pass

    async def _avancar_proxima(self, db: BancoDeDados) -> bool:
        async with db.transacao() as conn:
            v = await buscar_um(conn, """
                SELECT * FROM transportadoras.viagem
                 WHERE status IN ('AGENDADA', 'EM_TRANSITO') AND proximo_passo_em <= now()
                 ORDER BY proximo_passo_em LIMIT 1
                 FOR UPDATE SKIP LOCKED
            """)
            if v is None:
                return False
            with correlacao(v["correlation_id"]):
                await self._dar_passo(conn, v)
            return True

    async def _dar_passo(self, conn: AsyncConnection, v: dict) -> None:
        agora = await self.relogio.agora(conn)
        estado = EstadoViagem(
            status=v["status"], rota=[tuple(p) for p in v["rota"]], coleta_em=v["coleta_em"],
            chegada_prevista=v["chegada_prevista"], atraso_horas=float(v["atraso_horas"]),
            atraso_revelado=v["atraso_revelado"], parada_publicada=v["parada_publicada"],
            marco_tempo=v["marco_tempo"], marco_progresso=float(v["marco_progresso"]),
            progresso=float(v["progresso"]), data_prometida=v["data_prometida"])
        novo, eventos = passo(estado, agora)

        sequencia = v["sequencia"]
        for evento in eventos:
            sequencia += 1
            await self._publicar(conn, self._payload(v, sequencia, evento), v["correlation_id"])

        entregue = novo.status == "ENTREGUE"
        no_prazo = next((e.extras["noPrazo"] for e in eventos if e.tipo == "ENTREGA_REALIZADA"), None)
        await conn.execute("""
            UPDATE transportadoras.viagem
               SET status = %s, chegada_prevista = %s, atraso_revelado = %s, parada_publicada = %s,
                   marco_tempo = %s, marco_progresso = %s, progresso = %s, sequencia = %s,
                   proximo_passo_em = now() + make_interval(secs => %s),
                   entregue_em = CASE WHEN %s THEN %s ELSE entregue_em END,
                   no_prazo = COALESCE(%s, no_prazo)
             WHERE id = %s
        """, (novo.status, novo.chegada_prevista, novo.atraso_revelado, novo.parada_publicada, novo.marco_tempo,
              novo.marco_progresso, novo.progresso, sequencia, self.intervalo, entregue, novo.chegada_prevista,
              no_prazo, v["id"]))
        if entregue:
            await self._liberar_frota(conn, v["id"])
            log.info("Entrega realizada", extra={"dados": {"entregaId": v["entrega_id"], "noPrazo": no_prazo}})

    @staticmethod
    def _payload(v: dict, sequencia: int, evento: EventoViagem) -> dict:
        payload = {
            "pedidoId": v["pedido_id"], "entregaId": v["entrega_id"], "transportadoraId": v["transportadora_id"],
            "sequencia": sequencia, "tipo": evento.tipo, "descricao": evento.descricao,
            "posicao": _ponto(evento.posicao), "progresso": round(evento.progresso, 4),
            "previsaoChegada": iso(evento.previsao), "ocorridoEm": iso(evento.ocorrido_em),
        }
        for chave, valor in evento.extras.items():
            payload[chave] = iso(valor) if isinstance(valor, datetime) else valor
        return payload

    async def _liberar_frota(self, conn: AsyncConnection, viagem_id: str) -> None:
        await conn.execute("UPDATE transportadoras.veiculo SET viagem_atual_id = NULL WHERE viagem_atual_id = %s",
                           (viagem_id,))
        await conn.execute("UPDATE transportadoras.motorista SET viagem_atual_id = NULL WHERE viagem_atual_id = %s",
                           (viagem_id,))

    # ------------------------------------------------------------------ cancelamento (pedido_atualizado)
    async def cancelar_viagem(self, conn: AsyncConnection, envelope: dict) -> str:
        dados = validar_payload("pedido_atualizado", envelope["payload"])
        if (dados.get("novoStatus") or dados.get("status") or "").upper() != "CANCELADO":
            return "ignorado"
        viagens = await buscar_todos(conn, """
            UPDATE transportadoras.viagem SET status = 'CANCELADA'
             WHERE pedido_id = %s AND status IN ('AGENDADA', 'EM_TRANSITO')
            RETURNING id
        """, (dados["pedidoId"],))
        for viagem in viagens:
            await self._liberar_frota(conn, viagem["id"])
        if viagens:
            log.info("Viagem cancelada; motorista e veículo liberados", extra={"dados": {"pedidoId": dados["pedidoId"]}})
        return "cancelada" if viagens else "sem_viagem"

    # ------------------------------------------------------------------ relógio
    async def sincronizar_relogio(self, conn: AsyncConnection, envelope: dict) -> bool:
        """relogio_ajustado: copia o relógio do módulo da logística (D18).

        As duas cópias deste serviço leem a mesma tabela `transportadoras.relogio`,
        então basta uma delas processar o evento. Um ajuste mais antigo que o
        gravado é ignorado (comparação de versão).
        """
        estado = EstadoRelogio.do_evento(validar_payload("relogio_ajustado", envelope["payload"]))
        gravou = await gravar_estado(conn, SCHEMA, estado)
        self.relogio.invalidar()
        log.info("Relógio do módulo sincronizado" if gravou else "Ajuste de relógio antigo ignorado",
                 extra={"dados": {"versao": estado.versao, "fator": estado.fator}})
        return gravou


def para_json(valor):
    if isinstance(valor, Decimal):
        return float(valor)
    if isinstance(valor, datetime):
        return iso(valor)
    if hasattr(valor, "isoformat"):
        return valor.isoformat()
    return valor


def linha_para_json(linha: dict) -> dict:
    return {chave: para_json(valor) for chave, valor in linha.items()}
