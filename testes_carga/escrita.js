// Teste de carga de escrita: o fluxo inteiro do frete, de ponta a ponta, com vários pedidos ao mesmo tempo.
//
// Cada iteração faz o que acontece na demonstração:
//   1. o admin cria um pedido de teste (pedidos-falso publica pedido_criado no Kafka);
//   2. espera a logística abrir a solicitação e as transportadoras cotarem (status COTADA);
//   3. o comprador escolhe a cotação mais barata (POST selecionar-frete, com Idempotency-Key);
//   4. espera a transportadora escalar motorista e caminhão (entrega sai de AGUARDANDO_ALOCACAO);
//   5. cancela o pedido (pedido_atualizado CANCELADO), o que libera a frota para os próximos.
//
// Critérios (thresholds):
//   - criar pedido e escolher o frete: p95 <= 500 ms (são as gravações do usuário);
//   - do pedido às cotações: p95 <= 20 s (a rodada de cotação dura 10 s, D4);
//   - nenhuma solicitação duplicada (cada pedido abre exatamente uma);
//   - menos de 1% de erros HTTP.
// A frota do seed é pequena: com muitos pedidos ao mesmo tempo, parte das escolhas fica sem caminhão
// livre. Isso não é erro: o contador "sem_frota" mostra quantas foram (a logística tenta a próxima
// cotação e, sem nenhuma, publica frete_indisponivel).
//
// Antes de rodar: relógio do módulo em 1x (senão o prazo de 12 h vence e a escolha automática
// passa na frente do comprador). Roda dentro do Docker, na rede do ambiente:
//   docker run --rm -i --network logistica-grupo5_default grafana/k6:0.54.0 run - < testes_carga/escrita.js
// Variáveis: TAXA (pedidos por segundo, padrão 1), DURACAO (padrão 60s).
import http from 'k6/http';
import { check, fail, sleep } from 'k6';
import exec from 'k6/execution';
import { Counter, Trend } from 'k6/metrics';

const BASE = __ENV.BASE || 'http://portal';
const ESPERA_MAXIMA_S = 40;

const pedidoAteCotacoes = new Trend('pedido_ate_cotacoes', true);
const escolhaAteAlocacao = new Trend('escolha_ate_alocacao', true);
const duplicadas = new Counter('solicitacoes_duplicadas');
const semCotacao = new Counter('sem_cotacao');
const semFrota = new Counter('sem_frota');
const alocadas = new Counter('viagens_alocadas');

export const options = {
  scenarios: {
    escrita: {
      executor: 'constant-arrival-rate',
      rate: Number(__ENV.TAXA || 1), timeUnit: '1s', duration: __ENV.DURACAO || '60s',
      preAllocatedVUs: 40, maxVUs: 120,
    },
  },
  thresholds: {
    'http_req_duration{rota:criar_pedido}': ['p(95)<500'],
    'http_req_duration{rota:escolher}': ['p(95)<500'],
    pedido_ate_cotacoes: ['p(95)<20000'],
    solicitacoes_duplicadas: ['count==0'],
    http_req_failed: ['rate<0.01'],
  },
};

function entrar(usuarioId) {
  const r = http.post(`${BASE}/api/v1/usuarios/demonstracao/login`, JSON.stringify({ usuarioId }),
    { headers: { 'Content-Type': 'application/json' } });
  if (r.status !== 200) fail(`Login de ${usuarioId} falhou: HTTP ${r.status}`);
  return r.json('accessToken');
}

function uuid() {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = Math.random() * 16 | 0;
    return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16);
  });
}

export function setup() {
  const admin = entrar('usr-admin');
  const comprador = entrar('usr-comprador-1');
  const relogio = http.get(`${BASE}/api/v1/logistica/relogio`, { headers: { Authorization: `Bearer ${admin}` } });
  if (Number(relogio.json('fator')) !== 1) {
    fail(`Relógio do módulo em ${relogio.json('fator')}x: volte para 1x pela tela (admin) antes de rodar.`);
  }
  return { admin, comprador, rodada: `${Date.now().toString(36)}` };
}

const json = (token, extras = {}) => ({ headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json', ...extras } });

// Consulta até a condição valer ou o tempo acabar. Devolve o último valor (ou null).
function esperar(consultar, pronto) {
  const limite = Date.now() + ESPERA_MAXIMA_S * 1000;
  let valor = null;
  while (Date.now() < limite) {
    valor = consultar();
    if (valor && pronto(valor)) return valor;
    sleep(0.5);
  }
  return valor;
}

// Passos 2 a 4. Fica numa função à parte, sem try/finally: o k6 0.54 (motor sobek) trava com
// "index out of range" quando um return sai de dentro de um try/finally com várias VUs.
function acompanhar(dados, pedidoId, inicio) {
  const comprador = json(dados.comprador);
  const consulta = { ...comprador, tags: { rota: 'consultar_solicitacao' } };

  // 2. Solicitação aberta pela logística e cotada pelas transportadoras.
  const lista = esperar(
    () => http.get(`${BASE}/api/v1/logistica/solicitacoes?pedido_id=${pedidoId}`, consulta).json(),
    (r) => r.items && r.items.length && r.items[0].status !== 'ABERTA',
  );
  if (lista && lista.total > 1) duplicadas.add(lista.total - 1);
  const solicitacao = lista && lista.items && lista.items[0];
  if (!check(solicitacao, { 'solicitação aberta': (s) => !!s })) return;
  if (solicitacao.status !== 'COTADA') { semCotacao.add(1); return; }
  pedidoAteCotacoes.add(Date.now() - inicio);

  // 3. O comprador escolhe a mais barata (as cotações vêm ordenadas por preço).
  const detalhe = http.get(`${BASE}/api/v1/logistica/solicitacoes/${solicitacao.id}`, consulta).json();
  const cotacao = (detalhe.cotacoes || []).find((c) => c.status === 'VALIDA');
  if (!cotacao) { semCotacao.add(1); return; }
  const inicioEscolha = Date.now();
  const escolha = http.post(`${BASE}/api/v1/logistica/solicitacoes/${solicitacao.id}/selecionar-frete`,
    JSON.stringify({ cotacaoId: cotacao.id }), { ...json(dados.comprador, { 'Idempotency-Key': uuid() }), tags: { rota: 'escolher' } });
  if (!check(escolha, { 'escolha 200': (r) => r.status === 200 })) return;

  // 4. A transportadora escala motorista e caminhão (ou recusa, sem frota livre).
  const entrega = esperar(
    () => {
      const r = http.get(`${BASE}/api/v1/logistica/pedidos/${pedidoId}/entrega`,
        { ...comprador, tags: { rota: 'consultar_entrega' }, responseCallback: http.expectedStatuses(200, 404) });
      return r.status === 200 ? r.json() : null;
    },
    // Se a transportadora recusar, a logística tenta a próxima cotação (nova tentativa da entrega).
    (e) => e.status !== 'AGUARDANDO_ALOCACAO',
  );
  if (entrega && ['AGUARDANDO_COLETA', 'EM_TRANSITO'].includes(entrega.status)) {
    alocadas.add(1);
    escolhaAteAlocacao.add(Date.now() - inicioEscolha);
  } else {
    semFrota.add(1);
  }
}

export default function (dados) {
  const pedidoId = `ped-k6-${dados.rodada}-${exec.scenario.iterationInTest}`;

  // 1. Pedido de teste (papel do grupo de Pedidos).
  const inicio = Date.now();
  const criado = http.post(`${BASE}/api/v1/pedidos-falso/pedidos`, JSON.stringify({
    pedidoId, origem: { cidade: 'Sorriso', uf: 'MT' }, destino: { cidade: 'Santos', uf: 'SP' },
    tipoTransporte: 'GRANEL', pesoKg: 24000, produtoNome: 'Soja em grão (carga k6)', valorTotal: 192000,
  }), { ...json(dados.admin), tags: { rota: 'criar_pedido' } });
  if (!check(criado, { 'pedido criado 202': (r) => r.status === 202 })) return;

  acompanhar(dados, pedidoId, inicio);

  // 5. Limpa: cancela o pedido e libera a frota.
  const cancelado = http.post(`${BASE}/api/v1/pedidos-falso/pedidos/${pedidoId}/cancelamento`, null,
    { ...json(dados.admin), tags: { rota: 'cancelar_pedido' } });
  check(cancelado, { 'cancelamento 202': (r) => r.status === 202 });
}
