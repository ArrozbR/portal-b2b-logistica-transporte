// Teste de carga das leituras da logística (critério do kit, guia seção 10.2):
//   p95 de leitura <= 500 ms com 200 requisições simultâneas; menos de 1% de erros.
//
// Roda dentro do Docker, na rede do ambiente (não precisa instalar o k6):
//   docker run --rm -i --network logistica-grupo5_default grafana/k6:0.54.0 run - < testes_carga/leitura.js
//
// 200 usuários virtuais chamam, sem pausa, a lista de entregas, o rastreio (o
// que a tela consulta a cada 5 s) e a comparação de cotações, pelo portal
// (Nginx), que reparte entre as duas cópias da logística.
import http from 'k6/http';
import { check, fail } from 'k6';

const BASE = __ENV.BASE || 'http://portal';

export const options = {
  scenarios: {
    leitura: { executor: 'constant-vus', vus: Number(__ENV.VUS || 200), duration: __ENV.DURACAO || '30s' },
  },
  thresholds: {
    'http_req_duration{rota:entregas}': ['p(95)<500'],
    'http_req_duration{rota:rastreio}': ['p(95)<500'],
    'http_req_duration{rota:comparacao}': ['p(95)<500'],
    http_req_failed: ['rate<0.01'],
  },
};

export function setup() {
  const login = http.post(`${BASE}/api/v1/usuarios/demonstracao/login`, JSON.stringify({ usuarioId: 'usr-comprador-1' }),
    { headers: { 'Content-Type': 'application/json' } });
  const token = login.json('accessToken');
  const cabecalhos = { headers: { Authorization: `Bearer ${token}` } };
  const entregas = http.get(`${BASE}/api/v1/logistica/entregas?size=1`, cabecalhos).json('items');
  if (!entregas || !entregas.length) fail('Nenhuma entrega no ambiente: rode os testes de integração ou crie uma pela tela.');
  const detalhe = http.get(`${BASE}/api/v1/logistica/entregas/${entregas[0].id}`, cabecalhos);
  return { token, entregaId: entregas[0].id, solicitacaoId: detalhe.json('solicitacao_id') };
}

export default function (dados) {
  const cabecalhos = { headers: { Authorization: `Bearer ${dados.token}` } };
  const lista = http.get(`${BASE}/api/v1/logistica/entregas?size=20`, { ...cabecalhos, tags: { rota: 'entregas' } });
  check(lista, { 'entregas 200': (r) => r.status === 200 });
  const rastreio = http.get(`${BASE}/api/v1/logistica/entregas/${dados.entregaId}/rastreio`, { ...cabecalhos, tags: { rota: 'rastreio' } });
  check(rastreio, { 'rastreio 200': (r) => r.status === 200 });
  const comparacao = http.get(`${BASE}/api/v1/logistica/solicitacoes/${dados.solicitacaoId}/comparacao`, { ...cabecalhos, tags: { rota: 'comparacao' } });
  check(comparacao, { 'comparacao 200': (r) => r.status === 200 });
}
