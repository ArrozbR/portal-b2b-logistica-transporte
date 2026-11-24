"""Ajustes do mockup do UX e rota pelas estradas.

- telefone e CNH do motorista conforme o perfil (ESP-LOG-001, RN-37, CA-91);
- prazo desejado do comprador chegando à transportadora, e validade da cotação só com a data
  (ESP-TRP-001);
- rota da viagem pelas estradas, e não em linha reta (D9).
"""

import math
import uuid
from datetime import date, datetime, timedelta, timezone

from apoio import consultar, esperar, publicar_pedido

SORRISO, SANTOS = (-12.5453, -55.7114), (-23.9608, -46.3336)


def _distancia_da_reta_km(ponto, a=SORRISO, b=SANTOS) -> float:
    """Distância aproximada (km) do ponto à linha reta entre a e b."""
    escala_lon = math.cos(math.radians((a[0] + b[0]) / 2))
    ax, ay, bx, by = a[1] * escala_lon, a[0], b[1] * escala_lon, b[0]
    px, py = ponto[1] * escala_lon, ponto[0]
    dx, dy = bx - ax, by - ay
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy)) * 111.0


def _entrega_alocada(api, comprador, **pedido) -> tuple[str, str]:
    pedido_id = publicar_pedido(**pedido)["aggregateId"]
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


def test_dados_do_motorista_conforme_o_perfil_e_rota_pelas_estradas(api, entrar):
    comprador, fornecedor, admin = entrar("usr-comprador-1"), entrar("usr-fornecedor-1"), entrar("usr-admin")
    pedido_id, entrega_id = _entrega_alocada(api, comprador)

    vistas = {nome: api.get(f"/api/v1/logistica/entregas/{entrega_id}", headers=cabecalho).json()
              for nome, cabecalho in (("comprador", comprador), ("fornecedor", fornecedor), ("admin", admin))}
    assert all(v["motorista_nome"] for v in vistas.values())
    assert vistas["admin"]["motorista_telefone"] and vistas["admin"]["motorista_cnh_mascarada"]
    assert vistas["fornecedor"]["motorista_telefone"] and vistas["fornecedor"]["motorista_cnh_mascarada"] is None
    assert vistas["comprador"]["motorista_telefone"] is None and vistas["comprador"]["motorista_cnh_mascarada"] is None
    assert vistas["comprador"]["transportadora_telefone"]  # o comprador fala com a transportadora
    do_pedido = api.get(f"/api/v1/logistica/pedidos/{pedido_id}/entrega", headers=comprador).json()
    assert do_pedido["motorista_telefone"] is None and do_pedido["motorista_cnh_mascarada"] is None

    # Rota pelas estradas: começa e termina nas cidades, e se afasta da linha reta
    rota = api.get(f"/api/v1/logistica/entregas/{entrega_id}/rastreio", headers=comprador).json()["rota"]
    assert tuple(rota[0]) == SORRISO and tuple(rota[-1]) == SANTOS
    assert len(rota) > 60
    assert max(_distancia_da_reta_km(p) for p in rota) > 50


def test_prazo_desejado_chega_a_transportadora_e_validade_so_com_a_data(api, entrar):
    rodovia = entrar("usr-transp-rodovia")
    desejada = (date.today() + timedelta(days=400)).isoformat()  # bem depois da hora do módulo
    pedido_id = publicar_pedido(dataEntregaDesejada=desejada)["aggregateId"]
    solicitacao_id = esperar(lambda: consultar(
        "SELECT id FROM transportadoras.solicitacao_recebida WHERE pedido_id = %s", (pedido_id,)),
        mensagem="a transportadora não recebeu a solicitação")[0]["id"]
    assert str(consultar("SELECT data_entrega_desejada FROM transportadoras.solicitacao_recebida WHERE id = %s",
                         (solicitacao_id,))[0]["data_entrega_desejada"]) == desejada

    cargas = api.get("/api/v1/transportadoras/solicitacoes", headers=rodovia, params={"size": 100}).json()["items"]
    carga = next(c for c in cargas if c["id"] == solicitacao_id)
    assert carga["data_entrega_desejada"] == desejada

    # Validade só com a data: vale até 23:59:59 desse dia, no horário de Brasília
    hoje = datetime.fromisoformat(api.get("/api/v1/logistica/relogio", headers=rodovia).json()["horaDoModulo"]
                                  .replace("Z", "+00:00")).astimezone(timezone(timedelta(hours=-3))).date()
    entrega = (date.fromisoformat(carga["data_coleta_prevista"]) + timedelta(days=6)).isoformat()
    resposta = api.post(f"/api/v1/transportadoras/solicitacoes/{solicitacao_id}/cotacoes", headers=rodovia,
                        json={"valor": 5800.00, "dataEntregaPrevista": entrega, "validaAte": hoje.isoformat()})
    assert resposta.status_code == 201, resposta.text
    valida_ate = datetime.fromisoformat(resposta.json()["validaAte"].replace("Z", "+00:00"))
    fim_do_dia = datetime.combine(hoje, datetime.max.time().replace(microsecond=0), tzinfo=timezone(timedelta(hours=-3)))
    assert valida_ate == fim_do_dia


def test_passo_da_viagem_acompanha_a_velocidade_do_relogio(api, entrar, relogio):
    comprador = entrar("usr-comprador-1")
    _, entrega_id = _entrega_alocada(api, comprador)

    def espera_ate_o_proximo_passo() -> float:
        return consultar("SELECT EXTRACT(EPOCH FROM proximo_passo_em - now()) AS s FROM transportadoras.viagem "
                         "WHERE entrega_id = %s", (entrega_id,))[0]["s"]

    assert espera_ate_o_proximo_passo() > 5  # em tempo real, o próximo passo é em até 30 s

    # Acelerado: a viagem dá um passo logo depois do ajuste, e os próximos a cada 2 s reais.
    sequencia_antes = consultar("SELECT sequencia FROM transportadoras.viagem WHERE entrega_id = %s",
                                (entrega_id,))[0]["sequencia"]
    relogio(3600)
    esperar(lambda: consultar("SELECT sequencia FROM transportadoras.viagem WHERE entrega_id = %s",
                              (entrega_id,))[0]["sequencia"] > sequencia_antes, segundos=6,
            mensagem="a viagem não deu passo depois do ajuste do relógio")
    assert espera_ate_o_proximo_passo() <= 2.5
