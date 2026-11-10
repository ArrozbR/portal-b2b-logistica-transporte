"""Funções de apoio dos testes de integração: banco, Kafka, ambiente e métricas.

Os testes conferem o resultado onde ele realmente fica: nas tabelas do banco
e nos tópicos do Kafka, não só na resposta da API.
"""

import asyncio
import json
import os
import subprocess
import time
import uuid
from pathlib import Path

import httpx
import psycopg
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer, TopicPartition
from psycopg.rows import dict_row

from comum.eventos import montar_envelope

RAIZ = Path(__file__).resolve().parent.parent
PORTAL = "http://localhost:8088"
COPIAS_LOGISTICA = ("http://localhost:8108", "http://localhost:8118")
COPIAS_TRANSPORTADORAS = ("http://localhost:8109", "http://localhost:8119")
KAFKA = "localhost:29092"


def _variavel(nome: str, padrao: str) -> str:
    """Lê do ambiente, depois do .env da raiz (o mesmo que o docker compose usa), depois o padrão."""
    if nome in os.environ:
        return os.environ[nome]
    arquivo = RAIZ / ".env"
    if arquivo.exists():
        for linha in arquivo.read_text(encoding="utf-8").splitlines():
            if linha.startswith(f"{nome}="):
                return linha.split("=", 1)[1].strip()
    return padrao


CONNINFO = (f"host=localhost port=15432 dbname=portal_b2b user=portal_admin "
            f"password={_variavel('POSTGRES_PASSWORD', 'dev-admin')}")


# ------------------------------------------------------------------ banco

def consultar(sql: str, parametros: tuple | dict = ()) -> list[dict]:
    with psycopg.connect(CONNINFO, row_factory=dict_row) as conn:
        return conn.execute(sql, parametros).fetchall()


def executar(sql: str, parametros: tuple = ()) -> None:
    with psycopg.connect(CONNINFO, autocommit=True) as conn:
        conn.execute(sql, parametros)


# ------------------------------------------------------------------ Kafka

async def _publicar(topico: str, envelope: dict | list[dict], vezes: int = 1) -> None:
    produtor = AIOKafkaProducer(bootstrap_servers=KAFKA, acks="all", enable_idempotence=True)
    await produtor.start()
    try:
        for item in envelope if isinstance(envelope, list) else [envelope]:
            corpo = json.dumps(item).encode()
            for _ in range(vezes):
                await produtor.send_and_wait(topico, corpo, key=item["aggregateId"].encode())
    finally:
        await produtor.stop()


def publicar(topico: str, payload: dict, chave: str) -> dict:
    """Publica um evento qualquer (envelope do kit) e devolve o envelope."""
    envelope = montar_envelope(topico, "testes-integracao", chave, payload)
    asyncio.run(_publicar(topico, envelope))
    return envelope


def publicar_pedido(pedido_id: str | None = None, vezes: int = 1, **mudancas) -> dict:
    """Publica um pedido_criado (o MESMO evento `vezes` vezes) e devolve o envelope."""
    pedido_id = pedido_id or f"ped-it-{uuid.uuid4().hex[:8]}"
    payload = {
        "pedidoId": pedido_id, "compradorId": "emp-comprador-1", "fornecedorId": "emp-fornecedor-1",
        "produtoId": "prod-soja", "fornecimentoId": "forn-soja-1", "produtoNome": "Soja em grão", "quantidade": 24000, "unidade": "KG",
        "pesoKg": 24000, "tipoTransporte": "GRANEL", "valorTotal": 192000.0,
        "origem": {"cidade": "Sorriso", "uf": "MT"}, "destino": {"cidade": "Santos", "uf": "SP"},
        **mudancas,
    }
    envelope = montar_envelope("pedido_criado", "testes-integracao", pedido_id, payload)
    asyncio.run(_publicar("pedido_criado", envelope, vezes))
    return envelope


async def _ler(topico: str) -> list:
    consumidor = AIOKafkaConsumer(bootstrap_servers=KAFKA, group_id=None, enable_auto_commit=False,
                                  auto_offset_reset="earliest")
    await consumidor.start()
    try:
        metadados = await consumidor._client.fetch_all_metadata()  # partições do tópico no cluster
        particoes = [TopicPartition(topico, p) for p in metadados.partitions_for_topic(topico) or []]
        if not particoes:
            raise AssertionError(f"O tópico {topico} não existe no Redpanda")
        consumidor.assign(particoes)
        inicio = await consumidor.beginning_offsets(particoes)
        fim = await consumidor.end_offsets(particoes)
        for particao in particoes:
            consumidor.seek(particao, inicio[particao])
        mensagens = []
        while any([await consumidor.position(p) < fim[p] for p in particoes]):
            for lote in (await consumidor.getmany(timeout_ms=1000)).values():
                mensagens.extend(lote)
        return mensagens
    finally:
        await consumidor.stop()


def mensagens_do_topico(topico: str, chave: str | None = None) -> list[dict]:
    """Todos os envelopes do tópico, do começo ao fim, filtrados pela chave da mensagem."""
    return [json.loads(m.value) for m in asyncio.run(_ler(topico))
            if chave is None or (m.key and m.key.decode() == chave)]


# ------------------------------------------------------------------ limpeza entre testes

PEDIDO_DE_TESTE = "ped-it-%"


def pedidos_de_teste_em_aberto() -> list[str]:
    """Pedidos dos testes com cotação ou entrega ainda em andamento."""
    return [r["pedido_id"] for r in consultar("""
        SELECT pedido_id FROM logistica.solicitacao_frete
         WHERE pedido_id LIKE %(p)s AND status IN ('ABERTA', 'COTADA', 'SEM_COTACAO')
        UNION
        SELECT pedido_id FROM logistica.entrega
         WHERE pedido_id LIKE %(p)s AND status IN ('AGUARDANDO_ALOCACAO', 'AGUARDANDO_COLETA', 'EM_TRANSITO')
        UNION
        SELECT pedido_id FROM transportadoras.viagem
         WHERE pedido_id LIKE %(p)s AND status IN ('AGENDADA', 'EM_TRANSITO')
    """, {"p": PEDIDO_DE_TESTE})]


def limpar_pedidos_de_teste() -> None:
    """Cancela os pedidos de teste que ficaram em aberto, como o grupo de Pedidos faria.

    Sem isso, um teste interfere no seguinte: ao acelerar o relógio, o prazo de
    12 h das solicitações que sobraram vence, a regra automática escolhe a mais
    barata e o caminhão dela fica ocupado, e o teste seguinte recebe menos cotações.
    """
    abertos = pedidos_de_teste_em_aberto()
    if not abertos:
        return
    asyncio.run(_publicar("pedido_atualizado", [
        montar_envelope("pedido_atualizado", "testes-integracao", p, {"pedidoId": p, "status": "CANCELADO"})
        for p in abertos]))
    esperar(lambda: not pedidos_de_teste_em_aberto(), segundos=60, intervalo=1,
            mensagem=f"os pedidos de teste {abertos} não foram cancelados")


# ------------------------------------------------------------------ utilitários

def esperar(condicao, segundos: float = 30, intervalo: float = 0.5, mensagem: str = "condição não atingida"):
    """Repete `condicao()` até ela devolver algo verdadeiro; falha depois de `segundos`."""
    limite = time.time() + segundos
    ultimo_erro = None
    while time.time() < limite:
        try:
            resultado = condicao()
            if resultado:
                return resultado
        except Exception as exc:  # o recurso pode ainda não existir
            ultimo_erro = exc
        time.sleep(intervalo)
    raise AssertionError(f"{mensagem} em {segundos} s" + (f" (último erro: {ultimo_erro!r})" if ultimo_erro else ""))


def docker_compose(*argumentos: str) -> None:
    subprocess.run(["docker", "compose", *argumentos], cwd=RAIZ, check=True, capture_output=True)


def metrica(base: str, nome: str, rotulos: dict) -> float:
    """Lê um contador Prometheus de uma cópia do serviço (0 se ainda não existe)."""
    for linha in httpx.get(f"{base}/metrics", timeout=5).text.splitlines():
        if linha.startswith(nome + "{") and all(f'{k}="{v}"' in linha for k, v in rotulos.items()):
            return float(linha.rsplit(" ", 1)[1])
    return 0.0
