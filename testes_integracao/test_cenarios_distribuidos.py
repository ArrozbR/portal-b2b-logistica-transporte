"""Os três cenários distribuídos do plano de trabalho (seção 4.1).

Rodam sobre o Redpanda e o PostgreSQL de verdade, com as duas cópias de cada
serviço no ar, e conferem o resultado no banco e nos tópicos do Kafka.

1. Mensagem duplicada: o mesmo evento 5 vezes tem efeito uma vez só.
2. Várias coisas ao mesmo tempo: escolhas simultâneas nas duas cópias, mais o
   prazo vencendo, geram um único frete_selecionado.
3. Uma cópia caindo no meio da viagem: a outra assume, e a sequência de
   rastreio não tem buraco nem repetição.
4. Mensagens fora de ordem entre tópicos: o cancelamento do pedido chega às
   transportadoras antes do frete_selecionado, e nenhuma viagem é agendada.
"""

import asyncio
import time
import uuid

import httpx

from apoio import (COPIAS_LOGISTICA, COPIAS_TRANSPORTADORAS, PORTAL, consultar, docker_compose, esperar,
                   mensagens_do_topico, metrica, publicar, publicar_pedido)


def solicitacao_cotada(pedido_id: str, cotacoes: int = 3) -> str | None:
    """Id da solicitação quando ela está COTADA com `cotacoes` cotações válidas."""
    linhas = consultar("""
        SELECT s.id FROM logistica.solicitacao_frete s
         WHERE s.pedido_id = %s AND s.status = 'COTADA'
           AND (SELECT count(*) FROM logistica.cotacao c WHERE c.solicitacao_id = s.id AND c.status = 'VALIDA') = %s
    """, (pedido_id, cotacoes))
    return linhas[0]["id"] if linhas else None


def status_da_entrega(entrega_id: str) -> str:
    return consultar("SELECT status FROM logistica.entrega WHERE id = %s", (entrega_id,))[0]["status"]


# --------------------------------------------------------------------------- 1. mensagem duplicada

def test_mensagem_duplicada_tem_efeito_uma_vez_so():
    rotulos = {"topic": "pedido_criado", "resultado": "duplicado"}
    antes = sum(metrica(base, "eventos_consumidos_total", rotulos) for base in COPIAS_LOGISTICA)

    envelope = publicar_pedido(vezes=5)
    pedido_id = envelope["aggregateId"]

    # O Kafka recebeu as 5 cópias do mesmo evento (mesmo eventId)...
    no_topico = [m for m in mensagens_do_topico("pedido_criado", pedido_id) if m["eventId"] == envelope["eventId"]]
    assert len(no_topico) == 5

    # ...mas o efeito aconteceu uma vez só.
    solicitacao_id = esperar(lambda: solicitacao_cotada(pedido_id), mensagem="solicitação não ficou COTADA")
    esperar(lambda: sum(metrica(b, "eventos_consumidos_total", rotulos) for b in COPIAS_LOGISTICA) - antes >= 4,
            segundos=20, mensagem="as 4 repetições não foram contadas como duplicadas")
    assert len(consultar("SELECT 1 FROM logistica.solicitacao_frete WHERE pedido_id = %s", (pedido_id,))) == 1
    assert consultar("SELECT count(*) AS n FROM logistica.processed_events WHERE event_id = %s",
                     (envelope["eventId"],))[0]["n"] == 1
    assert consultar("SELECT count(*) AS n FROM logistica.outbox WHERE topico = 'solicitacao_frete_criada' "
                     "AND chave = %s", (solicitacao_id,))[0]["n"] == 1
    assert len(mensagens_do_topico("solicitacao_frete_criada", solicitacao_id)) == 1
    assert consultar("SELECT count(*) AS n FROM logistica.cotacao WHERE solicitacao_id = %s",
                     (solicitacao_id,))[0]["n"] == 3  # uma por transportadora compatível, não 15


# --------------------------------------------------------------------------- 2. ao mesmo tempo

def test_escolhas_simultaneas_nas_duas_copias_geram_um_frete_so(entrar, relogio):
    pedido_id = publicar_pedido()["aggregateId"]
    solicitacao_id = esperar(lambda: solicitacao_cotada(pedido_id), mensagem="solicitação não ficou COTADA")
    cotacoes = [c["id"] for c in consultar("SELECT id FROM logistica.cotacao WHERE solicitacao_id = %s ORDER BY id",
                                           (solicitacao_id,))]
    comprador, admin = entrar("usr-comprador-1"), entrar("usr-admin")

    async def corrida():
        async with httpx.AsyncClient(timeout=15) as cliente:
            pedidos = []
            for i in range(6):  # 6 escolhas, alternando as duas cópias e os tipos de escolha
                corpo = {"modo": "AUTOMATICO"} if i % 3 == 0 else {"cotacaoId": cotacoes[i % len(cotacoes)]}
                pedidos.append(cliente.post(
                    f"{COPIAS_LOGISTICA[i % 2]}/api/v1/logistica/solicitacoes/{solicitacao_id}/selecionar-frete",
                    json=corpo, headers={**comprador, "Idempotency-Key": str(uuid.uuid4())}))
            # Ao mesmo tempo, o relógio dispara: as 12 h de prazo vencem em menos de 1 s,
            # e a rotina de prazos das duas cópias também tenta escolher pela regra automática.
            pedidos.append(cliente.post(f"{PORTAL}/api/v1/logistica/admin/relogio", json={"fator": 100000},
                                        headers=admin))
            return await asyncio.gather(*pedidos)

    respostas = asyncio.run(corrida())
    codigos = [r.status_code for r in respostas[:-1]]
    assert set(codigos) <= {200, 409}, codigos
    assert codigos.count(200) <= 1, codigos  # 0 se a rotina de prazos ganhou a corrida

    esperar(lambda: consultar("SELECT status FROM logistica.solicitacao_frete WHERE id = %s",
                              (solicitacao_id,))[0]["status"] == "SELECIONADA", segundos=15)
    relogio(1)
    esperar(lambda: mensagens_do_topico("frete_selecionado", pedido_id), segundos=15,
            mensagem="frete_selecionado não chegou ao Kafka")
    time.sleep(2)  # tempo para uma eventual segunda publicação aparecer, se existisse
    assert consultar("SELECT count(*) AS n FROM logistica.outbox WHERE topico = 'frete_selecionado' AND chave = %s",
                     (pedido_id,))[0]["n"] == 1
    assert len(mensagens_do_topico("frete_selecionado", pedido_id)) == 1
    assert consultar("SELECT count(*) AS n FROM logistica.entrega WHERE pedido_id = %s",
                     (pedido_id,))[0]["n"] == 1


# --------------------------------------------------------------------------- 3. uma cópia caindo

def _aguardar_copias_prontas():
    esperar(lambda: all(httpx.get(f"{b}/health/ready", timeout=3).status_code == 200
                        for b in (*COPIAS_LOGISTICA, *COPIAS_TRANSPORTADORAS)),
            segundos=90, intervalo=2, mensagem="as cópias não voltaram")


def test_copia_caindo_no_meio_da_viagem(api, entrar, relogio):
    pedido_id = publicar_pedido()["aggregateId"]
    solicitacao_id = esperar(lambda: solicitacao_cotada(pedido_id), mensagem="solicitação não ficou COTADA")
    resposta = api.post(f"/api/v1/logistica/solicitacoes/{solicitacao_id}/selecionar-frete", json={"modo": "AUTOMATICO"},
                        headers={**entrar("usr-comprador-1"), "Idempotency-Key": str(uuid.uuid4())})
    entrega_id = resposta.json()["entregaId"]

    relogio(3600)  # a coleta (2 h depois da escala) acontece em segundos
    esperar(lambda: status_da_entrega(entrega_id) == "EM_TRANSITO", segundos=90, intervalo=1,
            mensagem="o caminhão não saiu")

    docker_compose("stop", "logistica-1", "transportadoras-1")  # derruba uma cópia de cada serviço
    try:
        relogio(20000)  # pelo portal: o Nginx manda para a cópia que sobrou
        esperar(lambda: status_da_entrega(entrega_id) == "ENTREGUE", segundos=240, intervalo=2,
                mensagem="a entrega não terminou só com as cópias 2")
    finally:
        docker_compose("start", "logistica-1", "transportadoras-1")
        _aguardar_copias_prontas()

    # No banco da logística: todos os eventos, cada um uma vez, sem buraco.
    sequencias = [r["sequencia"] for r in consultar(
        "SELECT sequencia FROM logistica.evento_rastreio WHERE entrega_id = %s ORDER BY sequencia", (entrega_id,))]
    assert sequencias == list(range(1, len(sequencias) + 1))
    viagem = consultar("SELECT sequencia, status FROM transportadoras.viagem WHERE entrega_id = %s", (entrega_id,))[0]
    assert viagem == {"sequencia": len(sequencias), "status": "ENTREGUE"}  # nada se perdeu no caminho
    tipos = [r["tipo"] for r in consultar(
        "SELECT tipo FROM logistica.evento_rastreio WHERE entrega_id = %s ORDER BY sequencia", (entrega_id,))]
    assert tipos[0] == "VIAGEM_ALOCADA" and tipos[1] == "COLETA_REALIZADA" and tipos[-1] == "ENTREGA_REALIZADA"

    # No Kafka: todas as sequências estão no tópico (repetição é aceita: a entrega é "pelo menos uma vez").
    no_topico = {m["payload"]["sequencia"] for m in mensagens_do_topico("rastreio_atualizado", pedido_id)
                 if m["payload"]["entregaId"] == entrega_id}
    assert no_topico == set(sequencias)
    assert consultar("SELECT count(*) AS n FROM logistica.outbox WHERE topico = 'entrega_concluida' AND chave = %s",
                     (pedido_id,))[0]["n"] == 1
    assert len(mensagens_do_topico("entrega_concluida", pedido_id)) >= 1


# --------------------------------------------------------------------------- 4. fora de ordem entre tópicos

def test_cancelamento_antes_do_frete_selecionado_nao_prende_caminhao():
    """pedido_atualizado e frete_selecionado são tópicos diferentes, sem ordem entre eles.

    Se o comprador escolhe o frete e o pedido é cancelado logo em seguida, as
    transportadoras podem receber o cancelamento primeiro. A escala que vem
    depois não pode agendar viagem, senão caminhão e motorista ficam presos.
    """
    pedido_id = publicar_pedido()["aggregateId"]
    solicitacao_id = esperar(lambda: solicitacao_cotada(pedido_id), mensagem="solicitação não ficou COTADA")
    cotacao = consultar("SELECT id, transportadora_id, preco, prazo_dias FROM logistica.cotacao "
                        "WHERE solicitacao_id = %s ORDER BY preco LIMIT 1", (solicitacao_id,))[0]

    publicar("pedido_atualizado", {"pedidoId": pedido_id, "status": "CANCELADO"}, pedido_id)
    esperar(lambda: consultar("SELECT cancelada FROM transportadoras.solicitacao_recebida WHERE id = %s",
                              (solicitacao_id,))[0]["cancelada"], segundos=15,
            mensagem="as transportadoras não registraram o cancelamento")

    # O frete_selecionado que saiu antes do cancelamento, mas chegou depois.
    entrega_id = str(uuid.uuid4())
    atrasado = publicar("frete_selecionado", {
        "pedidoId": pedido_id, "solicitacaoFreteId": solicitacao_id, "entregaId": entrega_id, "tentativa": 1,
        "cotacaoId": cotacao["id"], "transportadoraId": cotacao["transportadora_id"],
        "preco": float(cotacao["preco"]), "prazoDias": cotacao["prazo_dias"],
        "criterio": "AUTOMATICO_MENOR_PRECO", "status": "FRETE_SELECIONADO"}, pedido_id)

    esperar(lambda: consultar("SELECT 1 FROM transportadoras.processed_events WHERE event_id = %s",
                              (atrasado["eventId"],)), segundos=15, mensagem="o frete_selecionado não foi processado")
    assert not consultar("SELECT 1 FROM transportadoras.viagem WHERE entrega_id = %s", (entrega_id,))
    assert consultar("SELECT status FROM logistica.solicitacao_frete WHERE id = %s",
                     (solicitacao_id,))[0]["status"] == "CANCELADA"
