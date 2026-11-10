# 05. Plano de trabalho

Ordem de trabalho conforme as decisões da [pauta](06-pauta-de-decisoes.md). O prazo é "até dezembro", sem data exata (P5); as datas abaixo são sugestão e precisam ser ajustadas quando a data for confirmada. O código é gerado por IA (D16), e cada parte entregue vem com um arquivo de explicação em `docs/explicacoes/` (D24).

## 1. Etapas

A ordem coloca primeiro o que **não pode faltar**: o fluxo do frete integrado (prioridade definida pelo grupo), depois o rastreio visual. Nada foi cortado. Se o tempo apertar, os itens do fim da etapa 4 são os que correm mais risco.

| Etapa | Entrega | Pronto quando | Sugestão de data |
|---|---|---|---|
| **0. Alinhamento** | Contrato enviado ao grupo de Pedidos; tópicos propostos à Infra; perguntas ao professor; responsáveis definidos | Grupo de Pedidos respondeu à [proposta](contratos/proposta-grupo-pedidos.md) | 09/11 a 16/11 |
| **1. Base e fluxo automático** ✅ | Os 2 serviços sobre o boilerplate corrigido; banco, outbox, consumidor idempotente, retry e DLT; JWT e RBAC; script de pedido falso (D23); cotação simulada; escolha automática pela regra do kit | Um `pedido_criado` do script termina em `frete_selecionado` sozinho | **concluída em 09/11** ([explicação](explicacoes/01-base-e-fluxo-automatico.md)) |
| **2. Escolha e prazos** ✅ (falta a integração real) | Relógio do módulo (D18); escolha pelo comprador e botão "automático" (D5); rodada de 10 s, prazo de 12 h, `SEM_COTACAO`, `frete_indisponivel` (D4); cancelamento; notificações (D22); "Pedidos falso" (D23); integração real com o grupo de Pedidos | O pedido real do grupo de Pedidos muda de status pelos nossos eventos | **concluída em 09/11** com o "Pedidos falso" ([explicação](explicacoes/02-escolha-relogio-notificacoes.md)). A integração real depende do acordo com o grupo de Pedidos (etapa 0) |
| **3. Rastreio visual** ✅ | Cadastro de motoristas e veículos (API), escala sorteada e recusa de viagem (D19, D20); simulador de viagem; `rastreio_atualizado` e `entrega_concluida`; portal com lista de entregas e tela de rastreamento com mapa | Viagem Sorriso → Santos roda inteira na tela com o relógio acelerado e o pedido termina `ENTREGUE` | **concluída em 10/11** ([explicação](explicacoes/03-rastreio-visual.md)) |
| **4. Comparação e restante do mockup** ✅ | Tela de comparação com selos e gráfico; ranking; cotação digitada e tela "Solicitações de frete"; telas de cadastro; documentos demonstrativos (D21); ocorrências | Todas as telas do mockup funcionando com dados reais | **concluída em 10/11** ([explicação](explicacoes/04-comparacao-cotacao-documentos.md)) |
| **5. Prova e ensaio** | Os 3 testes distribuídos (seção 4.1); demais testes; relatório técnico com ADRs; slides; ensaio da demonstração | Os 3 testes passam sobre Redpanda e PostgreSQL reais; demonstração ensaiada | até a apresentação |

Os testes de cada parte são escritos junto com ela, não só na etapa 5. A etapa 5 junta tudo e prova os cenários distribuídos.

## 2. Responsáveis

Em aberto (D17). Como o código é gerado por IA, o papel de cada membro é **revisar, testar e entender** a sua parte, usando os arquivos de explicação.

| Parte | Responsável |
|---|---|
| Contato com o grupo de Pedidos (etapa 0) | a definir |
| Contato com Infra, Banco, Produtos e Autenticação (etapa 0) | a definir |
| Etapas 1 e 2 | a definir |
| Etapa 3 | a definir |
| Etapa 4 | a definir |
| Apresentação | a definir |

## 3. Tarefas da etapa 0

- [ ] Reunião do grupo: definir os responsáveis da seção 2.
- [ ] Preencher o contato e enviar a [proposta de contrato](contratos/proposta-grupo-pedidos.md) ao grupo de Pedidos.
- [ ] Levar ao professor as perguntas P1, P2, P3 e P5 da pauta.
- [ ] Propor à Infra os tópicos `rastreio_atualizado`, `entrega_concluida`, `frete_indisponivel` e `relogio_ajustado`.
- [ ] Responder ao grupo de Produtos as pendências P-06 (tipos de transporte) e P-27 (como recebemos o tipo).
- [ ] Pedir à Autenticação o tipo e o endereço da empresa em `empresa_cadastrada`.
- [ ] Avisar os grupos de UX e de Testes das decisões D5 e D11.
- [ ] Subir o kit localmente e confirmar os itens K1 a K4 e L1 a L5 da [análise](04-analise-do-kit.md).

## 4. Testes

### 4.1 Os 3 testes distribuídos

Rodam sobre o **Redpanda e o PostgreSQL de verdade** (Docker), com as duas cópias de cada serviço no ar, seguindo o modelo de testes do repositório `ProcessoeArtefatoAED`: os serviços sobem como processos e o teste confere o resultado pelo banco e pelos tópicos.

| Teste | Como | Passa se |
|---|---|---|
| **Mensagem duplicada** | Publicar o mesmo `pedido_criado` (mesmo `eventId`) 5 vezes | Existe exatamente **1** solicitação no banco e **1** `solicitacao_frete_criada` no tópico |
| **Duas coisas ao mesmo tempo** | Disparar no mesmo instante a escolha do comprador, o botão "automático" e o vencimento do prazo, com `app1` e `app2` no ar | O tópico tem exatamente **1** `frete_selecionado` e a solicitação tem **1** cotação escolhida |
| **Uma cópia caindo** | Derrubar `app1-logistica` e `app1-transportadoras` no meio da viagem | O caminhão continua andando pela `app2`, a entrega é concluída, e a sequência de rastreio não tem buraco nem repetição |

### 4.2 Demais testes

| Teste | O que prova |
|---|---|
| Regra automática | Menor preço vence; empate vai para o menor prazo, depois pontualidade, depois `transportadoraId` |
| Prazos | Rodada de 10 s sem cotação → `SEM_COTACAO`; 12 h com cotação → escolha automática; 12 h sem cotação → `frete_indisponivel` |
| Relógio | Acelerar o relógio acelera a viagem, os prazos e o cálculo de atraso; a transportadora recebe o ajuste |
| Cotação tardia | Cotação depois da escolha é recusada (409 ou `RECUSADA_TARDE`) |
| Escala | Duas viagens ao mesmo tempo nunca pegam o mesmo caminhão; sem caminhão livre → `VIAGEM_RECUSADA` → próxima cotação |
| Compatibilidade | Carga `REFRIGERADO` só recebe cotação de quem tem veículo refrigerado livre |
| Rastreio fora de ordem | Evento com `sequencia` antiga não move o caminhão para trás |
| RBAC | Comprador cotando → 403; transportadora cotando em nome de outra → 403; não administrador mexendo no relógio → 403 |
| LGPD | Telefone e CNH do motorista não aparecem para quem não é comprador ou fornecedor da entrega |
| Paginação | `size=101` → 422 |
| Falha permanente | Payload inválido vai para a DLT depois de 3 tentativas |
| Contrato | O script de pedido falso e o consumidor usam o mesmo JSON Schema |
| Carga | p95 da leitura do rastreio ≤ 500 ms com muitas telas consultando a cada 5 s |

## 5. Roteiro da demonstração

Cerca de 10 minutos, com o relógio em fator 360 (3 dias de viagem em uns 12 minutos):

1. Kafka UI aberto nos tópicos do grupo.
2. Um pedido de soja em grão, 24 t, Sorriso (MT) → Santos (SP) chega pelo fluxo dos outros grupos. Se a integração não estiver pronta, o script de contingência publica o pedido (D23).
3. `solicitacao_frete_criada` e as cotações chegam, uma por transportadora compatível; a refrigerada não cota. O comprador recebe a notificação.
4. Uma transportadora entra na tela "Solicitações de frete" e digita uma cotação.
5. O comprador abre a comparação: selos, gráfico preço × prazo e pontualidade. Escolhe a Expressa, que não é a mais barata. O pedido vai a `FRETE_SELECIONADO`.
6. O motorista e o caminhão são sorteados e aparecem na tela.
7. O administrador acelera o relógio. No rastreio, o caminhão sai de Sorriso, para em Campo Grande, a previsão é atualizada e ele chega a Santos.
8. `entrega_concluida` aparece e o pedido termina `ENTREGUE`. Os documentos demonstrativos ficam disponíveis.
9. O ranking mostra a entrega contabilizada.
10. Resiliência: derrubar `app1-logistica` no meio de outra viagem e mostrar que o rastreio continua pela `app2`.
