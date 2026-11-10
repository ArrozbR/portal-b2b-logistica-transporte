# Logística e Transporte | Portal B2B Distribuído

Microsserviços de **Logística** e **Transportadoras** do Portal B2B Distribuído, trabalho da disciplina de Sistemas Distribuídos (2026). O grupo cuida do que acontece depois que o pedido é criado: cotar o frete com as transportadoras, comparar as propostas, escolher a vencedora e acompanhar a entrega num mapa até a chegada.

> **Situação:** decisões tomadas, ainda sem código. Próximo passo: enviar a [proposta de contrato](docs/contratos/proposta-grupo-pedidos.md) ao grupo de Pedidos e definir os responsáveis. **Comece pela [Pauta de decisões](docs/06-pauta-de-decisoes.md).**

## Integrantes

Conforme o guia do kit de infraestrutura (confirmar):

- Gabriel Borges
- Pedro Blamires
- Gabriel Rodrigues
- Heitor Deodato
- Jefferson Felex

## O que o grupo entrega

| Serviço | Porta | Schema | Papel |
|---|:---:|---|---|
| `logistica-service` | 8108 | `logistica` | Abre a solicitação de frete, recebe as cotações, mostra a comparação, registra a escolha do comprador (ou aplica a regra automática), mantém a entrega e o rastreio, notifica e controla o relógio do módulo |
| `transportadoras-service` | 8109 | `transportadoras` | Transportadoras, motoristas e veículos; cotações simuladas e digitadas; escala do motorista; simulação da viagem e indicadores de desempenho |

Porta, schema, usuário de banco e tópicos já foram definidos pelo [kit de infraestrutura](https://github.com/Printf-PedroCardoso/portal-b2b-kit-infra). O trabalho tem três frentes:

| Frente | Origem | Situação no kit |
|---|---|---|
| **1. Cotação e seleção de frete** | Kit (seção 8 do guia) | Tópicos e regra definidos (menor preço, desempate por menor prazo, janela de 10 s). Boilerplate incompleto |
| **2. Comparação entre transportadoras** | Pedido do professor | Não existe. O kit só tem 2 transportadoras com preço fixo |
| **3. Rastreio visual da entrega** | Pedido do professor | Não existe. Não há tópico de entrega nem de rastreio, e nenhum serviço leva o pedido a `ENTREGUE` por evento |

## Fluxo resumido

```mermaid
flowchart LR
    PED[pedidos-service] -->|pedido_criado| LOG[logistica-service]
    LOG -->|solicitacao_frete_criada| TRP[transportadoras-service]
    TRP -->|cotacao_recebida| LOG
    LOG -->|frete_selecionado| PED
    LOG -->|frete_selecionado| TRP
    TRP -->|rastreio_atualizado *| LOG
    LOG -->|entrega_concluida *<br/>frete_indisponivel *| PED
    FE[Telas sobre o<br/>mockup do UX] -->|/api/v1/logistica| LOG
```

`*` tópicos novos, que precisam ser propostos ao grupo de Infraestrutura. Todas as setas entre serviços passam pelo Redpanda. O detalhe está em [Arquitetura](docs/02-arquitetura-proposta.md).

## Documentação

| Documento | Conteúdo |
|---|---|
| [01. Contexto e escopo](docs/01-contexto-e-escopo.md) | O Portal B2B, o que o kit já define para o grupo, o que o professor acrescentou e o que fica fora |
| [02. Arquitetura](docs/02-arquitetura-proposta.md) | Responsabilidades, fluxo, estados, escolha do frete, rastreio, relógio, notificações, modelo de dados, API e pontos de sistemas distribuídos |
| [03. Eventos e integrações](docs/03-eventos-e-integracoes.md) | Payloads, tópicos novos e o que precisamos pedir a cada grupo |
| [04. Análise do kit](docs/04-analise-do-kit.md) | Problemas encontrados nos boilerplates de logística e transportadoras |
| [05. Plano de trabalho](docs/05-plano-de-trabalho.md) | Etapas, testes e roteiro da demonstração |
| [06. Pauta de decisões](docs/06-pauta-de-decisoes.md) | Decisões D1 a D24 e perguntas para o professor |
| [Proposta ao grupo de Pedidos](docs/contratos/proposta-grupo-pedidos.md) | Documento pronto para enviar: campos do `pedido_criado` e eventos que eles precisam consumir |

## Repositórios de referência

| Repositório | Grupo | Uso aqui |
|---|---|---|
| [portal-b2b-kit-infra](https://github.com/Printf-PedroCardoso/portal-b2b-kit-infra) | Infraestrutura | Base: portas, schemas, tópicos, envelope de eventos, boilerplates e regra de seleção de frete (commit `630515c`) |
| [Sistema-MicServ-SD](https://github.com/davicalvarenga/Sistema-MicServ-SD) | Fornecimento e Produtos | Modelo de organização da documentação e análise do kit (itens K1 a K11). Têm pendências abertas com o nosso grupo (P-06, P-27) |
| [portal-b2b-UI-UX](https://github.com/HugoParzival007/portal-b2b-UI-UX) | UX/UI | Mockups das telas de fretes e de rastreamento, que a nossa API precisa alimentar |
| [AED---Processo-e-Artefato-SD-](https://github.com/AmandaBfa/AED---Processo-e-Artefato-SD-) | Teste e Qualidade | Modelo ERS-LLM para as especificações dos serviços, que o QA usa para testar |

## Como subir o ambiente

O ambiente local vem do kit. É preciso ter Docker e Docker Compose.

```bash
git clone https://github.com/Printf-PedroCardoso/portal-b2b-kit-infra
cd portal-b2b-kit-infra
make env        # copia .env.example para .env
make infra-up   # PostgreSQL, Redpanda, gateway, PgAdmin e Kafka UI
```

| Ferramenta | Endereço |
|---|---|
| Gateway (APIs e front-ends) | http://localhost:8080 |
| Kafka UI | http://localhost:8090 |
| PgAdmin | http://localhost:5050 |
| Redpanda (clientes Kafka) | localhost:19092 |
| PostgreSQL | localhost:5432 |

As instruções para rodar os nossos serviços entram aqui quando o primeiro estiver implementado. Antes disso, veja a [Análise do kit](docs/04-analise-do-kit.md): os boilerplates não consomem Kafka e não gravam no banco.

## Estrutura do repositório

```
.
├── README.md
├── CLAUDE.md                     # orientações para o Claude Code
├── docs/
│   ├── 01-contexto-e-escopo.md
│   ├── 02-arquitetura-proposta.md
│   ├── 03-eventos-e-integracoes.md
│   ├── 04-analise-do-kit.md
│   ├── 05-plano-de-trabalho.md
│   ├── 06-pauta-de-decisoes.md
│   └── contratos/
│       └── proposta-grupo-pedidos.md
└── services/
    ├── logistica-service/        # ainda sem código
    └── transportadoras-service/  # ainda sem código
```
