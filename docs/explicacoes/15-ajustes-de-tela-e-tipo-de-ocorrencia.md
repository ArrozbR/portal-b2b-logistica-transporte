# 15. Ajustes de tela e tipo da ocorrência

Em 23/11/2026, depois da revisão visual (explicação 14), quatro pedidos do grupo e uma comparação com a versão publicada do mockup do grupo de UX (<https://portal-b2b-ui-ux-public.vercel.app>).

## 1. O que mudou

| Pedido | O que foi feito |
|---|---|
| Atualizar a localização da carga, sem derrubar o sistema | Botão **Atualizar localização** no canto do mapa. Atualiza na hora e centraliza o caminhão. Depois espera 15 s (5 s desde a [explicação 17](17-logo-linha-do-tempo-e-caminhao-continuo.md)), mostrando a contagem ("de novo em 12 s"). Só aparece com o caminhão na estrada (aguardando coleta ou em trânsito). |
| Limpar as notificações | Botão **Marcar todas como lidas** no topo do painel do sino, que só aparece quando há notificação não lida. Usa uma rota nova: `POST /api/v1/logistica/notificacoes/marcar-todas-lidas` (API-19). |
| Ícones da linha do tempo tortos | A linha vertical passa a ser centralizada pelo meio do círculo, e não por uma distância fixa. O título fica na altura do centro do ícone. |
| Tipo da ocorrência (mockup do UX) | O formulário "Reportar ocorrência" pede o tipo: Atraso, Avaria na carga, Desvio de rota ou Outro. O tipo aparece na linha do tempo e na notificação da outra parte ("O comprador reportou uma ocorrência (avaria na carga)..."). |
| Contador do sino mostrando "0" (achado ao testar) | Elementos com o atributo `hidden` agora sempre ficam escondidos. O mesmo defeito fazia "Reportar ocorrência" aparecer em entrega cancelada e "Novo pedido de teste" aparecer com o `pedidos-falso` fora do ar. |

## 2. Onde está cada coisa

| Arquivo | O que mudou |
|---|---|
| `services/logistica-service/logistica/api.py` | Rota `marcar-todas-lidas`; campo `tipo` na ocorrência |
| `services/logistica-service/logistica/notificacoes.py` | `TIPOS_OCORRENCIA` e o tipo na mensagem |
| `services/logistica-service/migracoes/008_tipo_ocorrencia.sql` | Coluna `tipo` na tabela `ocorrencia` (padrão `OUTRO`) |
| `frontend/assets/rastreio.js` | Botão do mapa, tipo no formulário e na linha do tempo |
| `frontend/assets/portal.js`, `portal.css` | Botão do sino, linha do tempo, regra do `hidden` |
| `docs/especificacoes/ESP-LOG-001_Logistica.md` | Versão 1.6: API-19, CA-89 e CA-90 |
| `testes_integracao/test_ocorrencias_e_notificacoes.py` | Testes das duas mudanças, conferindo o banco e as notificações |

## 3. Perguntas que o professor pode fazer

**Como o botão do mapa evita sobrecarregar o serviço?**
Com dois limites. O primeiro é uma consulta por vez: se uma atualização ainda está em andamento (a automática, de 5 s, ou a do botão), a outra espera por ela em vez de abrir uma consulta nova. O segundo é a espera de 15 s entre um clique e o próximo. Mesmo clicando sem parar, cada tela faz no máximo uma consulta a cada 5 s, mais uma a cada 15 s.

**Por que não colocar o limite no servidor?**
O teste de carga faz 200 acessos ao mesmo tempo, todos vindos do mesmo endereço (o contêiner do k6). Um limite por endereço no servidor recusaria esse teste. A consulta do rastreio é uma leitura leve, e o teste de carga mostrou que o serviço aguenta. Se o portal fosse para a internet, o limite por usuário ficaria no gateway, que é da Infraestrutura.

**A rota "marcar todas" pode marcar a notificação de outra empresa?**
Não. A gravação filtra pela empresa e pelo perfil que vêm do token (`WHERE empresa_id = ... AND papel = ...`), como a lista do sino. O teste de integração confere que as do comprador continuam não lidas quando o fornecedor marca as dele.

**Por que o tipo da ocorrência é opcional?**
Para não quebrar quem já chamava a rota só com a descrição. Sem tipo, a ocorrência fica como `OUTRO`, e as gravadas antes da mudança também. A tela sempre manda o tipo.

**Por que o tipo vai como código (`AVARIA`) e não como texto ("Avaria na carga")?**
O código não muda se alguém reescrever o texto da tela, e a API recusa qualquer valor fora da lista (422). O texto é só para mostrar.

## 4. Diferenças que continuam entre o mockup publicado e a nossa API

| Ponto | Mockup | Nossa API |
|---|---|---|
| Descrição da ocorrência | 1 a 500 caracteres | 5 a 500, sem contar os espaços das pontas (RN-33) |
| Validade da cotação | Data ("último dia") | Data e hora (`validaAte`), na hora do módulo |
| Prazo de entrega da carga | A entrega estimada não pode passar dele | A transportadora não recebe esse prazo |
| Motorista no rastreio | Sem telefone nem CNH | Telefone e CNH mascarada (`*******0001`) |
| Identificador da entrega | `FR-1084` | UUID; a tela mostra o número do pedido |
