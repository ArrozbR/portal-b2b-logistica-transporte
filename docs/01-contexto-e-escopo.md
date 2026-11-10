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

Nos mockups, mapa, motorista e documentos são marcados como dados demonstrativos. Isso combina com a proposta de simular a viagem em vez de usar GPS real.

## 4. Escopo proposto

### 4.1 Dentro do escopo

- Abrir a solicitação de frete a partir do `pedido_criado`, com origem, destino, tipo de carga e peso.
- Cadastro das transportadoras homologadas, com tipos de carga atendidos, estados (UFs) atendidos, capacidade e tabela de preços.
- Cotação automática (simulada) pelas transportadoras compatíveis e cotação manual pelo usuário com perfil `transportadora`.
- Janela de cotação, seleção automática pela regra do kit e publicação de `frete_selecionado`.
- Comparação das cotações de uma solicitação (lado a lado) e ranking de desempenho das transportadoras.
- Simulação da viagem com posição, eventos de linha do tempo e previsão de chegada.
- API de rastreio e uma tela com mapa (Leaflet + OpenStreetMap).
- Conclusão da entrega com evento para o `pedidos-service` mover o pedido para `ENTREGUE`.
- Cancelamento: pedido cancelado cancela a solicitação ou a entrega.
- Requisitos transversais do kit (RFC 7807, health, métricas, idempotência, DLT, RBAC, paginação).

### 4.2 Fora do escopo (proposta)

- GPS real, aplicativo de motorista ou integração com rastreadores.
- Integração real com transportadoras ou agregadores de frete (pode virar extra, ver D7 na pauta).
- Pagamento do frete, emissão de CT-e, nota fiscal ou qualquer documento fiscal real.
- Roteirização com várias paradas, consolidação de cargas ou frete fracionado.
- Cálculo de rota por estrada no MVP (a rota é uma linha interpolada; a rota por estrada é extra, ver D9).

## 5. Atores

| Ator | O que faz no nosso módulo |
|---|---|
| Comprador | Vê as cotações do seu pedido, compara e acompanha a entrega no mapa |
| Fornecedor | Vê a coleta prevista e o andamento da entrega dos seus pedidos (a confirmar) |
| Transportadora | Mantém seu perfil operacional, vê as cargas compatíveis, envia cotação e, opcionalmente, informa eventos da viagem |
| Admin | Consulta tudo e o ranking de transportadoras |
| Sistema | Gera cotações simuladas, fecha a janela de cotação, seleciona o frete e simula a viagem |

## 6. Glossário

| Termo | Significado |
|---|---|
| Solicitação de frete | Pedido de transporte aberto pela logística para um pedido de compra. Tem origem, destino, tipo de carga, peso e janela de cotação |
| Cotação | Proposta de uma transportadora para uma solicitação: preço, prazo em dias úteis, data prevista de entrega e validade |
| Janela de cotação | Tempo em que a logística aceita cotações antes de selecionar. Kit: 10 s |
| Seleção de frete | Escolha da cotação vencedora. Regra do kit: menor preço, desempate por menor prazo |
| Entrega | Execução do transporte depois da seleção. Uma por pedido |
| Evento de rastreio | Fato da viagem: coleta realizada, em trânsito, posição, parada, previsão atualizada, ocorrência, entrega realizada |
| Previsão de chegada (ETA) | Data e hora estimadas de chegada, recalculadas durante a viagem |
| Transportadora homologada | Empresa com perfil `transportadora` e perfil operacional cadastrado no `transportadoras-service` |
| Tipo de carga | Como o produto precisa ser transportado. Sugestão do kit: `GRANEL`, `REFRIGERADO`, `CARGA_SECA`, `PERIGOSO` (pendência P-06 do grupo de Produtos) |
| Simulador de viagem | Rotina do `transportadoras-service` que avança a viagem em tempo acelerado e publica os eventos de rastreio |
