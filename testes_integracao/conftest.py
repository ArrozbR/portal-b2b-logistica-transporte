"""Fixtures dos testes de integração (as funções de apoio ficam em apoio.py).

Estes testes rodam contra o ambiente do docker-compose NO AR (Postgres,
Redpanda e as duas cópias de cada serviço) e conferem o resultado no banco e
nos tópicos do Kafka. Se o ambiente não estiver no ar, são pulados.

    docker compose up -d --build
    .venv/Scripts/python -m pytest testes_integracao -v
"""

import httpx
import pytest

from apoio import COPIAS_LOGISTICA, COPIAS_TRANSPORTADORAS, PORTAL, consultar, limpar_pedidos_de_teste


def cnhs_vencidas() -> list[str]:
    """Motoristas do seed com a CNH vencida na hora do módulo.

    Cada rodada da suíte acelera o relógio (até fator 100000) e o relógio só anda para a
    frente (D18). Depois de muitas rodadas no mesmo ambiente, a hora do módulo passa da
    validade das CNHs do seed, esses motoristas deixam de ser escalados, a transportadora
    deixa de cotar e os testes que esperam 3 cotações falham sem motivo aparente.
    """
    return [f"{l['nome']} ({l['transportadora_id']}, {l['cnh_validade']})" for l in consultar("""
        SELECT m.nome, m.transportadora_id, m.cnh_validade
          FROM transportadoras.motorista m, transportadoras.relogio r
         WHERE m.ativo AND m.transportadora_id IN ('transp-economica', 'transp-graneleira', 'transp-expressa')
           AND m.cnh_validade < (r.base_virtual + (now() - r.base_real) * r.fator)::date
    """)]


@pytest.fixture(scope="session", autouse=True)
def ambiente_no_ar():
    try:
        prontos = [httpx.get(f"{base}/health/ready", timeout=3).status_code
                   for base in (*COPIAS_LOGISTICA, *COPIAS_TRANSPORTADORAS)]
        httpx.get(f"{PORTAL}/api/v1/usuarios/demonstracao", timeout=3).raise_for_status()
    except httpx.HTTPError:
        pytest.skip("Ambiente fora do ar. Rode: docker compose up -d --build")
    if prontos != [200, 200, 200, 200]:
        pytest.skip(f"Alguma cópia não está pronta: {prontos}")
    vencidas = cnhs_vencidas()
    if vencidas:
        pytest.exit("O relógio do módulo passou da validade das CNHs do seed (rodadas anteriores o aceleraram): "
                    + "; ".join(vencidas) + ". Recrie o ambiente: docker compose down -v && docker compose up -d --build",
                    returncode=1)


@pytest.fixture(autouse=True)
def sem_pedidos_de_teste_em_aberto(ambiente_no_ar):
    """Cada teste começa e termina sem pedidos de teste em andamento (frota toda livre)."""
    limpar_pedidos_de_teste()
    yield
    limpar_pedidos_de_teste()


@pytest.fixture(scope="session")
def api():
    with httpx.Client(base_url=PORTAL, timeout=15) as cliente:
        yield cliente


class Sessoes:
    """Cabeçalhos com o token de cada usuário de demonstração (login pelo "Usuários falso")."""

    def __init__(self, cliente: httpx.Client):
        self._cliente = cliente
        self._cache: dict[str, dict] = {}

    def __call__(self, usuario_id: str) -> dict:
        if usuario_id not in self._cache:
            resposta = self._cliente.post("/api/v1/usuarios/demonstracao/login", json={"usuarioId": usuario_id})
            resposta.raise_for_status()
            self._cache[usuario_id] = {"Authorization": f"Bearer {resposta.json()['accessToken']}"}
        return self._cache[usuario_id]


@pytest.fixture(scope="session")
def entrar(api):
    return Sessoes(api)


@pytest.fixture
def relogio(api, entrar):
    """Muda a velocidade do relógio do módulo e garante a volta ao tempo real no fim do teste."""
    def ajustar(fator: float):
        resposta = api.post("/api/v1/logistica/admin/relogio", json={"fator": fator}, headers=entrar("usr-admin"))
        resposta.raise_for_status()
    ajustar(1)
    yield ajustar
    ajustar(1)
