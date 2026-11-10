"""Alteração de motorista e veículo com CNH ou placa que já pertence a outro cadastro.

Achado ao escrever a ESP-TRP-001: o cadastro (POST) já respondia 409, mas a
alteração (PUT) deixava a restrição UNIQUE do banco estourar e respondia 500.
Usa a frota da Rodovia Sul (seed 902) e confere no banco que nada mudou.
"""

from apoio import consultar

BASE = "/api/v1/transportadoras/transp-rodovia"


def _motorista(motorista_id: str) -> dict:
    m = consultar("SELECT nome, telefone, cnh_numero, cnh_categoria, cnh_validade FROM transportadoras.motorista "
                  "WHERE id = %s", (motorista_id,))[0]
    return {"nome": m["nome"], "telefone": m["telefone"], "cnhNumero": m["cnh_numero"],
            "cnhCategoria": m["cnh_categoria"], "cnhValidade": m["cnh_validade"].isoformat()}


def _veiculo(veiculo_id: str) -> dict:
    v = consultar("SELECT placa, tipo, capacidade_kg, tipos_carga, categoria_cnh_exigida FROM transportadoras.veiculo "
                  "WHERE id = %s", (veiculo_id,))[0]
    return {"placa": v["placa"], "tipo": v["tipo"], "capacidadeKg": float(v["capacidade_kg"]),
            "tiposCarga": list(v["tipos_carga"]), "categoriaCnhExigida": v["categoria_cnh_exigida"]}


def test_alterar_com_cnh_ou_placa_de_outro_cadastro_responde_409(api, entrar):
    rodovia = entrar("usr-transp-rodovia")
    motorista, outro_motorista = _motorista("mot-rod-2"), _motorista("mot-rod-1")
    veiculo, outro_veiculo = _veiculo("vei-rod-2"), _veiculo("vei-rod-1")

    resposta = api.put(f"{BASE}/motoristas/mot-rod-2", headers=rodovia,
                       json={**motorista, "cnhNumero": outro_motorista["cnhNumero"]})
    assert resposta.status_code == 409 and resposta.json()["codigo"] == "MOTORISTA_DUPLICADO"
    assert _motorista("mot-rod-2") == motorista

    resposta = api.put(f"{BASE}/veiculos/vei-rod-2", headers=rodovia,
                       json={**veiculo, "placa": outro_veiculo["placa"]})
    assert resposta.status_code == 409 and resposta.json()["codigo"] == "PLACA_DUPLICADA"
    assert _veiculo("vei-rod-2") == veiculo

    # A própria CNH e a própria placa não contam como duplicidade
    assert api.put(f"{BASE}/motoristas/mot-rod-2", headers=rodovia, json=motorista).status_code == 200
    assert api.put(f"{BASE}/veiculos/vei-rod-2", headers=rodovia, json=veiculo).status_code == 200

    # Cadastro inexistente: 404 vem antes da duplicidade
    resposta = api.put(f"{BASE}/motoristas/nao-existe", headers=rodovia,
                       json={**motorista, "cnhNumero": outro_motorista["cnhNumero"]})
    assert resposta.status_code == 404 and resposta.json()["codigo"] == "MOTORISTA_NAO_ENCONTRADO"
