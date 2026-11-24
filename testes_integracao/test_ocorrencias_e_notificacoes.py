"""Tipo da ocorrência (CA-90) e "Marcar todas como lidas" (API-19, CA-89).

Um pedido é escolhido pela regra automática e, com a entrega aguardando a coleta, o
comprador reporta ocorrências. Depois o fornecedor marca todas as notificações como lidas.
Confere a resposta, o banco e as notificações de cada lado.
"""

import uuid

from apoio import consultar, esperar, publicar_pedido

NOTIFICACOES = "/api/v1/logistica/notificacoes"


def _entrega_aguardando_coleta(api, comprador) -> tuple[str, str]:
    pedido_id = publicar_pedido()["aggregateId"]
    solicitacao_id = esperar(lambda: consultar(
        "SELECT id FROM logistica.solicitacao_frete WHERE pedido_id = %s AND status = 'COTADA'", (pedido_id,)),
        mensagem="solicitação não ficou COTADA")[0]["id"]
    resposta = api.post(f"/api/v1/logistica/solicitacoes/{solicitacao_id}/selecionar-frete",
                        json={"modo": "AUTOMATICO"}, headers={**comprador, "Idempotency-Key": str(uuid.uuid4())})
    assert resposta.status_code == 200, resposta.text
    entrega_id = resposta.json()["entregaId"]
    esperar(lambda: consultar("SELECT status FROM logistica.entrega WHERE id = %s",
                              (entrega_id,))[0]["status"] == "AGUARDANDO_COLETA", segundos=20)
    return pedido_id, entrega_id


def test_ocorrencia_com_tipo(api, entrar):
    comprador, fornecedor = entrar("usr-comprador-1"), entrar("usr-fornecedor-1")
    pedido_id, entrega_id = _entrega_aguardando_coleta(api, comprador)
    rota = f"/api/v1/logistica/entregas/{entrega_id}/ocorrencias"

    # Com tipo: gravado, devolvido e citado na notificação da outra parte
    resposta = api.post(rota, json={"tipo": "AVARIA", "descricao": "Lona da carreta rasgada."}, headers=comprador)
    assert resposta.status_code == 201, resposta.text
    assert resposta.json()["tipo"] == "AVARIA"
    assert consultar("SELECT tipo FROM logistica.ocorrencia WHERE id = %s", (resposta.json()["id"],))[0]["tipo"] == "AVARIA"
    avisos = [n for n in api.get(NOTIFICACOES, headers=fornecedor, params={"size": 100}).json()["items"]
              if n["pedido_id"] == pedido_id and n["tipo"] == "OCORRENCIA"]
    assert len(avisos) == 1
    assert avisos[0]["mensagem"].startswith(
        f"O comprador reportou uma ocorrência (avaria na carga) na entrega do pedido {pedido_id}")

    # Sem tipo: OUTRO, sem parênteses na mensagem
    resposta = api.post(rota, json={"descricao": "Motorista parado no posto."}, headers=comprador)
    assert resposta.status_code == 201 and resposta.json()["tipo"] == "OUTRO"

    # Tipo fora da lista: 422 no campo tipo, nada gravado
    for tipo in ("Avaria na carga", "avaria", 1):
        resposta = api.post(rota, json={"tipo": tipo, "descricao": "Qualquer coisa"}, headers=comprador)
        assert resposta.status_code == 422, tipo
        assert resposta.json()["codigo"] == "DADOS_INVALIDOS"
        assert resposta.json()["erros"][0]["campo"] == "body.tipo"

    itens = api.get(rota, headers=fornecedor).json()["items"]
    assert [o["tipo"] for o in itens] == ["AVARIA", "OUTRO"]
    rastreio = api.get(f"/api/v1/logistica/entregas/{entrega_id}/rastreio", headers=comprador).json()
    assert [o["tipo"] for o in rastreio["ocorrencias"]] == ["AVARIA", "OUTRO"]


def test_marcar_todas_como_lidas(api, entrar):
    comprador, fornecedor = entrar("usr-comprador-1"), entrar("usr-fornecedor-1")
    _entrega_aguardando_coleta(api, comprador)  # gera FRETE_ESCOLHIDO e MOTORISTA_ESCALADO para os dois

    nao_lidas = api.get(NOTIFICACOES, headers=fornecedor).json()["naoLidas"]
    do_comprador = api.get(NOTIFICACOES, headers=comprador).json()["naoLidas"]
    assert nao_lidas >= 2 and do_comprador >= 1

    resposta = api.post(f"{NOTIFICACOES}/marcar-todas-lidas", headers=fornecedor)
    assert resposta.status_code == 200
    assert resposta.json() == {"marcadas": nao_lidas, "naoLidas": 0}
    assert api.get(NOTIFICACOES, headers=fornecedor, params={"lida": "false"}).json()["total"] == 0

    # Só as do fornecedor mudam: o comprador continua com as dele
    assert api.get(NOTIFICACOES, headers=comprador).json()["naoLidas"] >= do_comprador

    # De novo: nada para marcar
    assert api.post(f"{NOTIFICACOES}/marcar-todas-lidas", headers=fornecedor).json() == {"marcadas": 0, "naoLidas": 0}

    # Admin e transportadora não têm notificações
    for usuario in ("usr-admin", "usr-transp-rodovia"):
        resposta = api.post(f"{NOTIFICACOES}/marcar-todas-lidas", headers=entrar(usuario))
        assert resposta.status_code == 403 and resposta.json()["codigo"] == "PERFIL_NAO_PERMITIDO", usuario
