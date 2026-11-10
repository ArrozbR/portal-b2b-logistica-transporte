# 01. Contexto e escopo

## 1. O Portal B2B

O portal conecta empresas compradoras, fornecedoras e transportadoras. É dividido entre 9 grupos da turma, cada um com seus microsserviços, e os serviços conversam por eventos num cluster Redpanda (compatível com a API do Kafka). Nenhum serviço chama outro por HTTP para avançar o fluxo de negócio, e nenhum lê o schema de outro no banco.

O fluxo principal, segundo o diagrama do professor (resumido no repositório do grupo de Fornecimento e Produtos):

1. O fornecedor publica um fornecimento.
2. O comprador registra uma demanda.
3. Os eventos são publicados no Kafka.
4. O matching de Mercado compara oferta e demanda.
5. O modo de negociação é definido (venda direta, leilão direto ou reverso).
6. A negociação ocorre e o vencedor é definido.
7. O pedido é criado.
8. **A logística é acionada para o frete.** ← nosso grupo
9. **As transportadoras enviam cotações.** ← nosso grupo
10. **O frete é selecionado e a entrega é realizada.** ← nosso grupo

O grupo entra no passo 8 e vai até o fim do fluxo.

## 2. O que o kit de infraestrutura já define

Fonte: [portal-b2b-kit-infra](https://github.com/Printf-PedroCardoso/portal-b2b-kit-infra), commit `630515c` (25/10/2026), arquivos `README.md`, `ORIENTACOES-ARQUITETURA-GRUPOS.md`, `CONTRACTS.md`, `database/01-init.sql`, `gateway/` e `services/`.

| Item | Valor definido |
|---|---|
| Serviços | `logistica-service` (8108) e `transportadoras-service` (8109) |
| Schemas e usuários | `logistica` com `svc_logistica`; `transportadoras` com `svc_transportadoras` |
| Rotas no gateway | `/api/v1/logistica/*` e `/api/v1/transportadoras/*`, com duas instâncias de cada serviço (`app1` e `app2`) atrás do Nginx |
| Front-end | Subcaminho `/logistica/` no gateway (o guia diz `/app/logistica`). A tela atual do kit é um formulário genérico |
| Tópicos que publicamos | `solicitacao_frete_criada` (logística), `cotacao_recebida` (transportadoras), `frete_selecionado` (logística) |
| Tópicos que consumimos | `pedido_criado`, `pedido_atualizado` (logística); `solicitacao_frete_criada`, `empresa_cadastrada` (transportadoras); `cotacao_recebida` (logística) |
| Tópicos de falha | `logistica.dlt` e `transportadoras.dlt` |
| Regra de seleção | Logística espera as cotações por até **10 s** e escolhe o **menor preço**, com desempate pelo **menor prazo em dias úteis**. O guia chama a regra de "inegociável" |
| Estados do pedido | `CRIADO → AGUARDANDO_FRETE → FRETE_SELECIONADO → ENTREGUE`, ou `CANCELADO` (pertencem ao `pedidos-service`) |
| Perfil `transportadora` | No RBAC do guia, "só pode submeter cotações em solicitações de frete" |
| Tabelas já criadas | `logistica.solicitacao_frete`, `logistica.cotacao`, `logistica.idempotency_keys`, `logistica.processed_events`, `transportadoras.transportadora`, `transportadoras.regra_cotacao`, `transportadoras.processed_events` |
| Regras gerais | Prefixo `/api/v1/`, `/health`, `/health/ready`, `/metrics` e `/docs` obrigatórios, erros RFC 7807, `X-Correlation-Id` em logs e eventos, logs JSON, paginação com `size ≤ 100` (acima disso, 422), pool de até 5 conexões, idempotência no consumo, 3 tentativas e DLT |
| Metas de qualidade cobradas pelo QA | p95 de leitura ≤ 500 ms, p95 de escrita ≤ 1000 ms, menos de 1% de 5xx sob carga, idempotência real e 403 no RBAC |

## 3. O que o professor pediu além do kit

O enunciado do grupo pede um módulo de logística e transporte **com rastreio visual e comparação entre empresas de entrega**. O kit não cobre nenhuma das duas coisas:

| Pedido | O que falta no kit |
|---|---|
| Rastreio visual | Não há tópico de entrega nem de rastreio. Nenhum serviço gera posição, linha do tempo ou previsão de chegada. Nenhum evento leva o pedido de `FRETE_SELECIONADO` para `ENTREGUE` |
| Comparação entre transportadoras | O seed tem 2 transportadoras com preço e prazo fixos, que não dependem de distância, peso ou tipo de carga. Não há dados de desempenho para comparar |
| Base para os dois | O `pedido_criado` não traz origem, destino, tipo de carga nem peso. Sem isso não há como cotar nem desenhar a rota |

O grupo de UX/UI já desenhou as duas telas que dependem de nós ([portal-b2b-UI-UX](https://github.com/HugoParzival007/portal-b2b-UI-UX), pasta `02_ESTUDO_DE_CASO_UX`):

- **Solicitações de frete** (`/fretes/solicitacoes`, perfil transportadora): lista de cargas com origem, destino, carga, peso, data de coleta e prazo, e formulário para enviar cotação com valor, prazo estimado, validade e observações.
- **Rastreamento da entrega** (`/fretes/entregas/{id}`, perfil comprador): status, progresso em %, previsão de chegada, transportadora, veículo, mapa com rota percorrida e restante, linha do tempo (coleta, em trânsito, parada, previsão atualizada, entrega), dados da carga, motorista e documentos.

Nos mockups, mapa, motorista e documentos são marcados como dados demonstrativos. O grupo decidiu ir além: motorista, veículo, produto e valor da carga são dados reais do sistema (D19), a posição do caminhão é simulada (D8) e os documentos são modelos demonstrativos (D21).

## 4. Escopo

Conforme as decisões da [pauta](06-pauta-de-decisoes.md).

### 4.1 Dentro do escopo

- Abrir a solicitação de frete a partir do `pedido_criado`, com origem, destino, tipo de carga, peso, produto e valor da carga.
- Cadastro das transportadoras homologadas, com tipos de carga, UFs atendidas e tabela de preços.
- Cadastro de motoristas e veículos, e escala sorteada entre os livres e compatíveis (D19, D20).
- Cotações simuladas e cotações digitadas pela transportadora (D3).
- Escolha do frete pelo comprador em até 12 h, botão "automático" e regra do kit como padrão (D4, D5).
- Comparação das cotações lado a lado e ranking de desempenho das transportadoras (D6).
- Simulação da viagem com posição a cada 30 s, linha do tempo e previsão de chegada (D8, D10).
- Relógio do módulo, acelerável pelo administrador (D18).
- Telas sobre o mockup do UX: rastreamento com mapa, solicitações de frete, comparação, ranking, cadastros e relógio (D11).
- Notificações no portal para comprador e fornecedor (D22).
- Documentos da entrega como modelos demonstrativos (D21).
- Eventos para o `pedidos-service`: frete selecionado, entrega concluída e frete indisponível (D12).
- Cancelamento: pedido cancelado cancela a solicitação ou a entrega e libera motorista e veículo.
- Script de contingência que publica pedidos falsos (D23).
- Requisitos transversais do kit (RFC 7807, health, métricas, idempotência, DLT, RBAC, paginação).

### 4.2 Fora do escopo

- GPS real, aplicativo de motorista ou integração com rastreadores.
- Integração real com transportadoras ou agregadores de frete (pode virar extra, D7).
- Pagamento do frete e emissão de CT-e, nota fiscal ou qualquer documento fiscal com validade.
- Notificação por e-mail ou SMS.
- Roteirização com várias paradas, consolidação de cargas ou frete fracionado.
- Rota por estrada (a rota é uma linha interpolada; estrada é extra, D9).
- Relógio acelerado nos serviços dos outros grupos (a diferença foi aceita, D18).

## 5. Atores

| Ator | O que faz no nosso módulo |
|---|---|
| Comprador | Compara as cotações do seu pedido, escolhe o frete (ou deixa no automático), acompanha a entrega no mapa, recebe notificações e reporta ocorrências |
| Fornecedor | Acompanha a coleta e a entrega dos seus pedidos e recebe notificações |
| Transportadora | Mantém o perfil operacional, cadastra motoristas e veículos, vê as cargas compatíveis e envia cotações |
| Admin | Consulta tudo, vê o ranking e controla o relógio do módulo |
| Sistema | Gera cotações simuladas, controla os prazos, aplica a escolha automática, sorteia motorista e veículo e simula a viagem |

## 6. Glossário

| Termo | Significado |
|---|---|
| Solicitação de frete | Pedido de transporte aberto pela logística para um pedido de compra. Tem origem, destino, tipo de carga, peso e prazos de cotação |
| Cotação | Proposta de uma transportadora para uma solicitação: preço, prazo em dias úteis, data prevista de entrega e validade. Pode ser simulada ou digitada |
| Rodada automática | Os primeiros 10 s depois da abertura, em que as cotações simuladas chegam (o tempo do kit). Sem cotação nesse tempo, a solicitação vai a `SEM_COTACAO` |
| Prazo de decisão | 12 h depois da abertura. Até lá, o comprador escolhe; depois, vale a regra automática |
| Escolha do frete | Escolha da cotação vencedora, feita pelo comprador ou pela regra automática do kit: menor preço, desempate por menor prazo |
| Relógio do módulo | Hora usada pelos dois serviços em todas as regras de tempo. O administrador pode acelerá-la |
| Escala | Sorteio do motorista e do veículo da transportadora vencedora, entre os livres e compatíveis |
| Entrega | Execução do transporte depois da seleção. Uma por pedido |
| Evento de rastreio | Fato da viagem: coleta realizada, em trânsito, posição, parada, previsão atualizada, ocorrência, entrega realizada |
| Previsão de chegada (ETA) | Data e hora estimadas de chegada, recalculadas durante a viagem |
| Transportadora homologada | Empresa com perfil `transportadora` e perfil operacional cadastrado no `transportadoras-service` |
| Tipo de carga | Como o produto precisa ser transportado. `GRANEL`, `REFRIGERADO`, `CARGA_SECA`, `PERIGOSO` (lista do kit, confirmada com o grupo de Produtos em 10/11/2026) |
| Simulador de viagem | Rotina do `transportadoras-service` que avança a viagem em tempo acelerado e publica os eventos de rastreio |
