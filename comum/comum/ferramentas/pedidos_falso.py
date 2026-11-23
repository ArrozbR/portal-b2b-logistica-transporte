"""SOMENTE DESENVOLVIMENTO: faz o papel do grupo de Pedidos (decisão D23).

Enquanto o pedidos-service real não está integrado, este serviço faz as duas
pontas do que o grupo de Pedidos faria:

1. **Cria pedidos.** O administrador cria um pedido de teste pela tela de
   solicitações (botão "Novo pedido de teste"), que chama
   `POST /api/v1/pedidos-falso/pedidos`. O serviço publica um `pedido_criado`
   no Kafka, igual ao do `publicar_pedido_falso`: a logística recebe o pedido
   pelo evento, como receberia do grupo de Pedidos. Nenhum serviço nosso é
   chamado por HTTP.
2. **Reage aos nossos eventos** (ver docs/contratos/proposta-grupo-pedidos.md, seção 2):

       solicitacao_frete_criada        → pedido vai a AGUARDANDO_FRETE
       frete_selecionado               → pedido vai a FRETE_SELECIONADO
       entrega_concluida               → pedido vai a ENTREGUE
       frete_indisponivel              → pedido continua AGUARDANDO_FRETE: a logística abre
                                         uma nova cotação (D27; ESP-PED-001, RN-22)

Também cancela um pedido (`POST /api/v1/pedidos-falso/pedidos/{id}/cancelamento`,
publica `pedido_atualizado` CANCELADO), o que o teste de carga de escrita usa
para limpar o que criou.

Pedido de leilão (D26): com `"leilao": true`, o `pedido_criado` sai sem comprador
nem destino, como o professor definiu (o pedido nasce na abertura do leilão), e
o leilão fecha sozinho `fechamentoEmSegundos` depois, num `pedido_atualizado`
com comprador e destino. `POST /api/v1/pedidos-falso/pedidos/{id}/fechamento`
fecha na hora. O status do fechamento (`LEILAO_FECHADO`) é provisório.

As rotas são só do administrador da plataforma. O status dos pedidos fica
só em memória e cada mudança vai para o log. Desligue o serviço quando o
pedidos-service real estiver integrado.

    uvicorn comum.ferramentas.pedidos_falso:app --port 8102
"""

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from typing import Literal

from aiokafka import AIOKafkaConsumer
from fastapi import Depends, FastAPI
from pydantic import BaseModel, Field

from comum import config
from comum.auth import Usuario, exigir_perfis
from comum.erros import Problema, registrar_tratadores
from comum.eventos import erros_do_payload, montar_envelope
from comum.ferramentas.publicar_pedido_falso import montar_pedido
from comum.geo import buscar_cidade, cidades
from comum.kafka import iniciar_produtor, servidores
from comum.logs import configurar_logs, correlacao
from comum.web import instalar_middleware

log = logging.getLogger("pedidos-falso")

SERVICO = "pedidos-falso"
TRANSICOES = {
    "solicitacao_frete_criada": "AGUARDANDO_FRETE",
    "frete_selecionado": "FRETE_SELECIONADO",
    "entrega_concluida": "ENTREGUE",
    "frete_indisponivel": "AGUARDANDO_FRETE",  # não cancela: a venda já foi concluída (D27)
}

# Status de cada pedido (só em memória; é uma ferramenta de desenvolvimento).
status: dict[str, str] = {}
kafka: dict = {}


async def publicar(topico: str, envelope: dict) -> None:
    produtor = kafka.get("produtor")
    if produtor is None:
        raise Problema(503, "KAFKA_INDISPONIVEL", "Kafka indisponível",
                       "O pedidos-falso ainda não se conectou ao Redpanda. Tente de novo em instantes.")
    try:
        await asyncio.wait_for(produtor.send_and_wait(
            topico, json.dumps(envelope, ensure_ascii=False).encode("utf-8"),
            key=envelope["aggregateId"].encode("utf-8")), timeout=10)
    except Exception as exc:
        log.warning("Falha ao publicar", extra={"dados": {"topico": topico, "erro": str(exc)}})
        raise Problema(503, "KAFKA_INDISPONIVEL", "Kafka indisponível",
                       f"Não foi possível publicar o evento {topico}. Tente de novo em instantes.")


async def reagir(produtor, mensagem) -> None:
    envelope = json.loads(mensagem.value)
    payload = envelope.get("payload", {})
    pedido_id = payload.get("pedidoId")
    if not pedido_id:
        return
    anterior = status.get(pedido_id)
    novo = TRANSICOES[mensagem.topic]
    status[pedido_id] = novo
    with correlacao(envelope.get("correlationId")):
        log.info("Pedido mudou de status", extra={"dados": {
            "pedidoId": pedido_id, "evento": mensagem.topic, "statusAnterior": anterior, "novoStatus": novo,
            "transportadoraId": payload.get("transportadoraId"), "criterio": payload.get("criterio")}})
        if mensagem.topic == "frete_indisponivel":
            log.info("Frete indisponível: o pedido espera a nova cotação da logística", extra={"dados": {
                "pedidoId": pedido_id, "motivo": payload.get("motivo")}})


async def escutar(produtor) -> None:
    """Consome os eventos da logística. Se o Redpanda cair, tenta de novo."""
    while True:
        consumidor = AIOKafkaConsumer(*TRANSICOES, bootstrap_servers=servidores(), group_id=SERVICO,
                                      client_id=SERVICO, auto_offset_reset="latest", enable_auto_commit=True)
        try:
            await consumidor.start()
            log.info("Pedidos falso escutando", extra={"dados": {"topicos": list(TRANSICOES)}})
            async for mensagem in consumidor:
                await reagir(produtor, mensagem)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("Consumo interrompido, tentando de novo", extra={"dados": {"erro": str(exc)}})
            await asyncio.sleep(5)
        finally:
            await consumidor.stop()


@asynccontextmanager
async def ciclo_de_vida(_: FastAPI):
    configurar_logs(SERVICO, config.texto("LOG_LEVEL", "INFO"))
    kafka["produtor"] = await iniciar_produtor(SERVICO)
    tarefa = asyncio.create_task(escutar(kafka["produtor"]))
    try:
        yield
    finally:
        tarefa.cancel()
        await kafka.pop("produtor").stop()


app = FastAPI(title="Pedidos falso (somente desenvolvimento)", version="0.2.0", lifespan=ciclo_de_vida)
registrar_tratadores(app)
instalar_middleware(app, SERVICO)
admin = exigir_perfis("admin")


class Local(BaseModel):
    cidade: str = Field(..., min_length=1, max_length=80, examples=["Sorriso"])
    uf: str = Field(..., pattern=r"^[A-Za-z]{2}$", examples=["MT"])


class NovoPedido(BaseModel):
    origem: Local
    destino: Local
    tipoTransporte: Literal["GRANEL", "REFRIGERADO", "CARGA_SECA", "PERIGOSO"] = "GRANEL"
    pesoKg: float = Field(24000, gt=0, le=100_000)
    produtoNome: str = Field("Soja em grão", min_length=1, max_length=120)
    valorTotal: float = Field(192000, ge=0, le=100_000_000)
    compradorId: str = Field("emp-comprador-1", min_length=1, max_length=64)
    fornecedorId: str = Field("emp-fornecedor-1", min_length=1, max_length=64)
    pedidoId: str | None = Field(None, pattern=r"^[A-Za-z0-9_-]{3,64}$",
                                 description="Padrão: gerado (ped-xxxxxxxx)")
    leilao: bool = Field(False, description="Pedido de leilão: nasce sem comprador nem destino, e o "
                                            "leilão fecha `fechamentoEmSegundos` depois (D26)")
    fechamentoEmSegundos: int = Field(5, ge=1, le=600)


class Fechamento(BaseModel):
    compradorId: str = Field("emp-comprador-1", min_length=1, max_length=64)
    destino: Local
    valorTotal: float | None = Field(None, ge=0, le=100_000_000, description="Lance vencedor (opcional)")


# Status com que o grupo de Pedidos publica a carga completa, com comprador e destino
# (ESP-PED-001 v2.1, D-03). A logística aceita qualquer status que traga comprador ou destino.
STATUS_FECHAMENTO = "AGUARDANDO_FRETE"
_tarefas: set[asyncio.Task] = set()  # fechamentos agendados (referência para não serem coletados)


def _cidade(local: Local, papel: str) -> dict:
    cidade = buscar_cidade(local.cidade, local.uf)
    if cidade is None:
        raise Problema(422, "CIDADE_DESCONHECIDA", "Cidade desconhecida",
                       f"A cidade de {papel} {local.cidade}/{local.uf.upper()} não está na lista da simulação. "
                       "Veja GET /api/v1/pedidos-falso/cidades.")
    return {"cidade": cidade.nome, "uf": cidade.uf}


@app.get("/health")
async def saude():
    return {"status": "UP" if "produtor" in kafka else "DOWN", "service": SERVICO}


@app.get("/api/v1/pedidos-falso/cidades", summary="Cidades que a simulação conhece")
async def listar_cidades(_: Usuario = Depends(admin)):
    return [{"cidade": c.nome, "uf": c.uf} for c in sorted(cidades(), key=lambda c: (c.uf, c.nome))]


@app.post("/api/v1/pedidos-falso/pedidos", status_code=202, summary="Cria um pedido de teste (publica pedido_criado)")
async def criar_pedido(corpo: NovoPedido, usuario: Usuario = Depends(admin)):
    origem, destino = _cidade(corpo.origem, "origem"), _cidade(corpo.destino, "destino")
    if origem == destino:
        raise Problema(422, "ORIGEM_IGUAL_AO_DESTINO", "Origem igual ao destino",
                       "Escolha cidades diferentes para a origem e o destino.")
    if corpo.pedidoId and corpo.pedidoId in status:
        raise Problema(409, "PEDIDO_JA_EXISTE", "Pedido já existe", f"O pedido {corpo.pedidoId} já foi criado.")
    payload = montar_pedido(origem=origem, destino=destino, tipo=corpo.tipoTransporte, peso=corpo.pesoKg,
                            produto=corpo.produtoNome, valor=corpo.valorTotal, comprador=corpo.compradorId,
                            fornecedor=corpo.fornecedorId, pedido_id=corpo.pedidoId)
    if corpo.leilao:
        # O pedido nasce na abertura do leilão: comprador e destino só no fechamento (professor, 12/11).
        payload["compradorId"] = None
        payload["destino"] = None
    erros = erros_do_payload("pedido_criado", payload)
    if erros:  # não deve acontecer: a rota já confere os campos
        raise Problema(422, "PEDIDO_FORA_DO_CONTRATO", "Pedido fora do contrato", "; ".join(erros))
    envelope = montar_envelope("pedido_criado", SERVICO, payload["pedidoId"], payload)
    await publicar("pedido_criado", envelope)
    status[payload["pedidoId"]] = "CRIADO"
    log.info("pedido_criado publicado", extra={"dados": {
        "pedidoId": payload["pedidoId"], "criadoPor": usuario.id, "origem": origem, "destino": destino,
        "leilao": corpo.leilao}})
    resposta = {"pedidoId": payload["pedidoId"], "eventId": envelope["eventId"],
                "correlationId": envelope["correlationId"], "pedido": payload}
    if corpo.leilao:
        fechamento = {"compradorId": corpo.compradorId, "destino": destino}
        tarefa = asyncio.create_task(_fechar_depois(payload["pedidoId"], fechamento, corpo.fechamentoEmSegundos,
                                                    envelope["correlationId"]))
        _tarefas.add(tarefa)
        tarefa.add_done_callback(_tarefas.discard)
        resposta["fechamentoEmSegundos"] = corpo.fechamentoEmSegundos
    return resposta


def _envelope_de_fechamento(pedido_id: str, fechamento: dict, correlation_id: str | None) -> dict:
    payload = {"pedidoId": pedido_id, "statusAnterior": status.get(pedido_id), "status": STATUS_FECHAMENTO,
               **fechamento}
    erros = erros_do_payload("pedido_atualizado", payload)
    if erros:
        raise Problema(422, "PEDIDO_FORA_DO_CONTRATO", "Fechamento fora do contrato", "; ".join(erros))
    return montar_envelope("pedido_atualizado", SERVICO, pedido_id, payload, correlation_id)


async def _fechar_depois(pedido_id: str, fechamento: dict, segundos: int, correlation_id: str) -> None:
    await asyncio.sleep(segundos)
    try:
        with correlacao(correlation_id):
            if status.get(pedido_id) == "CANCELADO":
                return
            await publicar("pedido_atualizado", _envelope_de_fechamento(pedido_id, fechamento, correlation_id))
            status[pedido_id] = STATUS_FECHAMENTO
            log.info("Leilão fechado (pedido_atualizado publicado)", extra={"dados": {
                "pedidoId": pedido_id, "compradorId": fechamento["compradorId"]}})
    except Exception:
        log.exception("Falha ao publicar o fechamento do leilão", extra={"dados": {"pedidoId": pedido_id}})


@app.post("/api/v1/pedidos-falso/pedidos/{pedido_id}/fechamento", status_code=202,
          summary="Fecha o leilão de um pedido (publica pedido_atualizado com comprador e destino)")
async def fechar_leilao(pedido_id: str, corpo: Fechamento, usuario: Usuario = Depends(admin)):
    fechamento = {"compradorId": corpo.compradorId, "destino": _cidade(corpo.destino, "destino")}
    if corpo.valorTotal is not None:
        fechamento["valorTotal"] = corpo.valorTotal
    envelope = _envelope_de_fechamento(pedido_id, fechamento, None)
    await publicar("pedido_atualizado", envelope)
    status[pedido_id] = STATUS_FECHAMENTO
    log.info("Leilão fechado (pedido_atualizado publicado)", extra={"dados": {
        "pedidoId": pedido_id, "criadoPor": usuario.id}})
    return {"pedidoId": pedido_id, "novoStatus": STATUS_FECHAMENTO, "eventId": envelope["eventId"]}


@app.post("/api/v1/pedidos-falso/pedidos/{pedido_id}/cancelamento", status_code=202,
          summary="Cancela um pedido (publica pedido_atualizado CANCELADO)")
async def cancelar_pedido(pedido_id: str, usuario: Usuario = Depends(admin)):
    anterior = status.get(pedido_id)
    envelope = montar_envelope("pedido_atualizado", SERVICO, pedido_id, {
        "pedidoId": pedido_id, "statusAnterior": anterior, "novoStatus": "CANCELADO",
        "motivo": "Cancelado pelo administrador (pedido de teste)"})
    await publicar("pedido_atualizado", envelope)
    status[pedido_id] = "CANCELADO"
    log.info("pedido_atualizado CANCELADO publicado", extra={"dados": {"pedidoId": pedido_id, "criadoPor": usuario.id}})
    return {"pedidoId": pedido_id, "novoStatus": "CANCELADO", "eventId": envelope["eventId"]}


def main() -> None:
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8102, log_config=None)


if __name__ == "__main__":
    main()
