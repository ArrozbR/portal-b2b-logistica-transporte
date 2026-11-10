# CLAUDE.md

Orientações para o Claude Code neste repositório.

## Projeto

Grupo 5 (Logística e Transporte) do **Portal B2B Distribuído**, trabalho da disciplina de Sistemas Distribuídos (2026). O portal é dividido entre 9 grupos, e os microsserviços conversam por eventos num cluster Redpanda (API do Kafka).

| Serviço | Porta | Schema | Usuário do banco |
|---|:---:|---|---|
| `logistica-service` | 8108 | `logistica` | `svc_logistica` |
| `transportadoras-service` | 8109 | `transportadoras` | `svc_transportadoras` |

Além do que o kit define (cotação e seleção de frete), o professor pediu **rastreio visual da entrega** e **comparação entre transportadoras**.

**Situação:** planejamento. Ainda não há código. As decisões em aberto estão em `docs/06-pauta-de-decisoes.md` (D1 a D17, perguntas P1 a P5). Não trate uma recomendação da pauta como decisão tomada: confira a coluna "Decisão" antes de implementar.

## Git

- **Não faça commit, push, merge, rebase nem crie branches ou repositórios remotos.** O usuário faz todos os commits.
- Ao terminar uma alteração, entregue só os comandos prontos (`git add <arquivos>` e `git commit -m "..."`), sem seções extras de "mensagem" e "arquivos". Mensagem em português, no formato `tipo: descrição` (`docs`, `feat`, `fix`, `refactor`, `test`, `chore`). Se fizer sentido, separe em mais de um commit, na ordem certa.
- Não inclua `Co-Authored-By`, `Claude-Session` nem qualquer menção ao Claude na mensagem.
- Pode usar `git status`, `git diff` e `git log` para consultar.

## Documentação

| Arquivo | Conteúdo |
|---|---|
| `docs/01-contexto-e-escopo.md` | O que o kit define, o que o professor pediu, escopo e glossário |
| `docs/02-arquitetura-proposta.md` | Responsabilidades, fluxo, estados, comparação, rastreio, modelo de dados, API |
| `docs/03-eventos-e-integracoes.md` | Payloads, tópicos novos e pedidos a outros grupos |
| `docs/04-analise-do-kit.md` | Problemas do kit (K1 a K11 do grupo de Produtos; L1 a L15 nossos) |
| `docs/05-plano-de-trabalho.md` | Fases F0 a F6, frentes A a E, testes e roteiro da demonstração |
| `docs/06-pauta-de-decisoes.md` | Decisões e perguntas ao professor |

Convenções:

- Tudo em português do Brasil, frases curtas, tabelas quando houver comparação.
- O que ainda não foi decidido aparece como **proposta**. Ao mudar uma decisão, atualize a pauta e os documentos que apontam para ela (`D#`).
- Mantenha os identificadores estáveis (`D#`, `P#`, `K#`, `L#`). Não renumere; acrescente no fim.
- Quando uma decisão for aceita, ela vira ADR no relatório técnico (ainda a criar, no modelo do grupo de Fornecimento e Produtos).
- Contratos de eventos aprovados ganham JSON Schema e exemplo em `docs/contratos/`.
- Especificações dos serviços seguem o modelo ERS-LLM do grupo de QA (ESP-LOG-001 e ESP-TRP-001).

## Fontes e precedência

1. Orientação do professor.
2. Código e scripts do kit de infraestrutura (<https://github.com/Printf-PedroCardoso/portal-b2b-kit-infra>, commit `630515c`): `database/01-init.sql`, `scripts/init_topics.sh`, `services/`.
3. `CONTRACTS.md` do kit.
4. `ORIENTACOES-ARQUITETURA-GRUPOS.md` do kit.

Quando duas fontes divergirem, siga a de maior precedência e registre a divergência em `docs/04-analise-do-kit.md`.

Repositórios dos outros grupos usados como referência (só leitura):

- Fornecimento e Produtos: <https://github.com/davicalvarenga/Sistema-MicServ-SD>
- UX/UI (mockups das telas de fretes e rastreamento): <https://github.com/HugoParzival007/portal-b2b-UI-UX>
- Teste e Qualidade (modelo ERS-LLM): <https://github.com/AmandaBfa/AED---Processo-e-Artefato-SD->

## Regras de arquitetura do kit (valem para todo código)

- Rotas de negócio em `/api/v1/logistica/...` e `/api/v1/transportadoras/...`.
- `/health`, `/health/ready` (testando banco e Redpanda), `/metrics` e `/docs` em cada serviço.
- Erros em RFC 7807 (`application/problem+json`, com `type`, `title`, `status`, `detail`, `correlationId`, `timestamp`).
- `X-Correlation-Id` lido da requisição (ou gerado) e repassado em logs e eventos.
- Logs em JSON no stdout. Nada de `print()`.
- Listagens paginadas com `?page=&size=`; `size > 100` retorna 422.
- Pool de no máximo 5 conexões por instância.
- **Nunca** ler ou escrever no schema de outro serviço. Dados de outros domínios chegam por evento.
- **Nunca** avançar o fluxo de negócio chamando outro serviço por HTTP.
- Eventos com o envelope do kit (`eventId`, `eventType`, `eventVersion`, `timestamp`, `source`, `correlationId`, `aggregateId`, `payload`) e `aggregateId` como chave de partição.
- Consumo idempotente com `processed_events` gravado na mesma transação da alteração; 3 tentativas (1 s, 2 s, 4 s) e depois `logistica.dlt` ou `transportadoras.dlt`.
- Cada serviço roda em duas instâncias (`app1` e `app2`). Nada de estado só em memória; tarefas com hora marcada não podem rodar duas vezes.
- Tópicos novos (`rastreio_atualizado`, `entrega_concluida`) são proposta até a Infraestrutura aprovar.

## Stack (proposta, D16)

Python 3.12, FastAPI, `aiokafka`, `psycopg2`, `pytest` com `httpx`, k6 para carga. Tela de rastreio com HTML, JavaScript e Leaflet sobre OpenStreetMap, salvo decisão diferente com o grupo de UX (D11).

Os boilerplates do kit não consomem Kafka, guardam dados em memória e têm os problemas listados em `docs/04-analise-do-kit.md`. Ao copiar código do kit, aplique as correções e registre o que foi mudado.

## Ambiente local

O ambiente vem do kit (precisa de Docker):

```bash
git clone https://github.com/Printf-PedroCardoso/portal-b2b-kit-infra
cd portal-b2b-kit-infra
make env
make infra-up
```

Gateway em `http://localhost:8080`, Kafka UI em `http://localhost:8090`, PgAdmin em `http://localhost:5050`, Redpanda em `localhost:19092`, PostgreSQL em `localhost:5432`. As credenciais do `.env.example` do kit são só de desenvolvimento; não copie senhas para este repositório.

Comandos para rodar e testar os nossos serviços entram aqui quando existir código.
