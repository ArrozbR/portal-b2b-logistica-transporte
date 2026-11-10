# Logística e Transporte | Portal B2B Distribuído

Microsserviços de **Logística** e **Transportadoras** do Portal B2B Distribuído, trabalho da disciplina de Sistemas Distribuídos (2026). O grupo cuida do que acontece depois que o pedido é criado: cotar o frete com as transportadoras, comparar as propostas, escolher a vencedora e acompanhar a entrega num mapa até a chegada.

> **Situação:** etapas 1 a 5 concluídas e validadas no Docker. O pedido entra, as transportadoras cotam (sozinhas ou digitando), o comprador compara e escolhe pela tela, o motorista é escalado e o caminhão anda no mapa até a entrega, com ranking, documentos e ocorrências, em <http://localhost:8088>. Os 3 cenários distribuídos (mensagem duplicada, escolhas simultâneas e cópia caindo) têm teste automático, o teste de carga passa no critério do kit e o [relatório técnico](docs/07-relatorio-tecnico.md) reúne as decisões em ADRs. Faltam os slides e o ensaio da apresentação. Pendente com outros grupos: enviar a [proposta de contrato](docs/contratos/proposta-grupo-pedidos.md) ao grupo de Pedidos. **Decisões em [Pauta de decisões](docs/06-pauta-de-decisoes.md); explicações do código em [`docs/explicacoes/`](docs/explicacoes/).**

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
| [06. Pauta de decisões](docs/06-pauta-de-decisoes.md) | Decisões D1 a D25 e perguntas para o professor |
| [07. Relatório técnico](docs/07-relatorio-tecnico.md) | Arquitetura, testes e resultados, limitações e as decisões em ADRs |
| [Proposta ao grupo de Pedidos](docs/contratos/proposta-grupo-pedidos.md) | Documento pronto para enviar: campos do `pedido_criado` e eventos que eles precisam consumir |

## Repositórios de referência

| Repositório | Grupo | Uso aqui |
|---|---|---|
| [portal-b2b-kit-infra](https://github.com/Printf-PedroCardoso/portal-b2b-kit-infra) | Infraestrutura | Base: portas, schemas, tópicos, envelope de eventos, boilerplates e regra de seleção de frete (commit `630515c`) |
| [Sistema-MicServ-SD](https://github.com/davicalvarenga/Sistema-MicServ-SD) | Fornecimento e Produtos | Modelo de organização da documentação e análise do kit (itens K1 a K11). Têm pendências abertas com o nosso grupo (P-06, P-27) |
| [portal-b2b-UI-UX](https://github.com/HugoParzival007/portal-b2b-UI-UX) | UX/UI | Mockups das telas de fretes e de rastreamento, que a nossa API precisa alimentar |
| [AED---Processo-e-Artefato-SD-](https://github.com/AmandaBfa/AED---Processo-e-Artefato-SD-) | Teste e Qualidade | Modelo ERS-LLM para as especificações dos serviços, que o QA usa para testar |

## Como rodar

O repositório tem um ambiente de desenvolvimento próprio (`docker-compose.yml`): Postgres, Redpanda, Redpanda Console, as **duas cópias** de cada serviço (como no kit) e o portal com as telas. As portas não conflitam com as do kit. É preciso ter o Docker Desktop aberto.

**Telas:** <http://localhost:8088>. Entre com um usuário de demonstração:

| Usuário | Perfil | O que ver |
|---|---|---|
| João Silva | comprador | Solicitações de frete, comparação e escolha, entregas e rastreamento |
| Maria Souza | fornecedor | As mesmas telas, só leitura na escolha; recebe os avisos |
| Rafael Moreira | transportadora real (Rodovia Sul) | Cargas disponíveis e cotação digitada, minha frota |
| Carla Expressa | transportadora simulada (Expressa) | Minha frota (as cotações dela são automáticas) |
| Administrador | admin | Tudo, e os botões de velocidade do relógio no topo |

```bash
cp .env.example .env               # opcional: troque as senhas
docker compose up -d --build       # sobe tudo
docker compose ps                  # aguarde tudo ficar healthy/running

# publica um pedido falso (Sorriso/MT → Santos/SP, 24 t de soja)
docker compose exec logistica-1 python -m comum.ferramentas.publicar_pedido_falso

docker compose logs -f logistica-1 transportadoras-1
docker compose down -v             # derruba e apaga os dados
```

| Ferramenta | Endereço |
|---|---|
| **Portal (telas)** | http://localhost:8088 |
| Logística (cópias 1 e 2) | http://localhost:8108/docs e http://localhost:8118/docs |
| Transportadoras (cópias 1 e 2) | http://localhost:8109/docs e http://localhost:8119/docs |
| Redpanda Console (mensagens) | http://localhost:8091 |
| Redpanda (clientes Kafka) | localhost:29092 |
| PostgreSQL | localhost:15432 (banco `portal_b2b`) |

Token para chamar a API: `docker compose exec logistica-1 python -m comum.ferramentas.gerar_token --perfil admin`.

O contêiner `pedidos-falso` faz o papel do grupo de Pedidos (`docker compose logs -f pedidos-falso`). Para cancelar um pedido de teste: `docker compose exec logistica-1 python -m comum.ferramentas.cancelar_pedido_falso --pedido-id <id>`.

Quando uma migração nova é adicionada, o banco de desenvolvimento precisa ser recriado: `docker compose down -v && docker compose up -d --build`.

Testes unitários, sem Docker:

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -e "comum[testes]"    # Linux/Mac: .venv/bin/python
.venv/Scripts/python -m pytest
```

Testes de integração e de carga, com o ambiente no ar (eles aceleram o relógio e derrubam contêineres; não rode durante uma demonstração):

```bash
.venv/Scripts/python -m pytest testes_integracao -v      # os 3 cenários distribuídos e o fluxo completo (~3 min)
docker run --rm -i --network logistica-grupo5_default grafana/k6:0.54.0 run - < testes_carga/leitura.js
```

O que já funciona e como cada parte foi feita está em [`docs/explicacoes/`](docs/explicacoes/).

## Estrutura do repositório

```
.
├── README.md
├── CLAUDE.md                     # orientações para o Claude Code
├── docker-compose.yml            # ambiente de desenvolvimento
├── comum/                        # código compartilhado pelos dois serviços
│   ├── comum/                    # eventos, outbox, consumidor, relógio, JWT, erros, logs
│   │   ├── contratos/            # JSON Schemas dos eventos
│   │   └── ferramentas/          # pedido falso (D23) e gerador de token
│   └── tests/
├── services/
│   ├── logistica-service/
│   │   ├── logistica/            # código do serviço
│   │   ├── migracoes/            # tabelas do schema logistica
│   │   └── tests/
│   └── transportadoras-service/
│       ├── transportadoras/
│       ├── migracoes/
│       └── tests/
├── frontend/                     # telas (HTML, CSS, JavaScript e mapa Leaflet)
├── infra/                        # Postgres, tópicos e portal (Nginx)
├── testes_integracao/            # cenários distribuídos contra o ambiente no ar
├── testes_carga/                 # cenário do k6
└── docs/
    ├── 01-contexto-e-escopo.md ... 07-relatorio-tecnico.md
    ├── contratos/                # propostas de contrato com outros grupos
    └── explicacoes/              # explicação de cada parte implementada
```
