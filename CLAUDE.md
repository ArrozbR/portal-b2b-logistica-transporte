# CLAUDE.md

Orientações para o Claude Code neste repositório.

## Projeto

Grupo 5 (Logística e Transporte) do **Portal B2B Distribuído**, trabalho da disciplina de Sistemas Distribuídos (2026). O portal é dividido entre 9 grupos, e os microsserviços conversam por eventos num cluster Redpanda (API do Kafka).

| Serviço | Porta | Schema | Usuário do banco |
|---|:---:|---|---|
| `logistica-service` | 8108 | `logistica` | `svc_logistica` |
| `transportadoras-service` | 8109 | `transportadoras` | `svc_transportadoras` |

Além do que o kit define (cotação e seleção de frete), o professor pediu **rastreio visual da entrega** e **comparação entre transportadoras**.

**Situação:** etapas 1 a 5 concluídas (fluxo do frete, escolha pelo comprador, relógio, notificações, cancelamento, motoristas e veículos, viagem simulada, comparação, cotação digitada, ranking, documentos, ocorrências, todas as telas do mockup, testes de integração dos 3 cenários distribuídos, teste de carga e relatório técnico). Faltam slides e ensaio da apresentação, e as pendências com outros grupos (relatório, seção 15). As decisões estão em `docs/06-pauta-de-decisoes.md` (D1 a D25, perguntas P1 a P5). Confira a coluna "Situação" antes de implementar: as marcadas "depende de" ainda podem mudar por causa de outro grupo ou do professor. A ordem de trabalho está em `docs/05-plano-de-trabalho.md` (etapas 0 a 5).

O código é gerado por IA, com conhecimento do professor. Cada parte entregue precisa vir com um arquivo em `docs/explicacoes/` (D24): o que a parte faz, em linguagem simples; por que foi feita assim; e as perguntas que o professor pode fazer, com as respostas. O grupo não tem experiência com as ferramentas, então explique sem jargão.

Regras de negócio que fogem do kit: o comprador escolhe o frete em até 12 h (a regra do menor preço vale no modo automático e quando o prazo vence); toda regra de tempo usa o relógio do módulo, nunca a hora do computador (D18).

## Git

- **Não faça commit, push, merge, rebase nem crie branches ou repositórios remotos.** O usuário faz todos os commits.
- Ao terminar uma alteração, entregue só os comandos prontos (`git add <arquivos>` e `git commit -m "..."`), sem seções extras de "mensagem" e "arquivos". Mensagem em português, no formato `tipo: descrição` (`docs`, `feat`, `fix`, `refactor`, `test`, `chore`). Se fizer sentido, separe em mais de um commit, na ordem certa.
- Não inclua `Co-Authored-By`, `Claude-Session` nem qualquer menção ao Claude na mensagem.
- Pode usar `git status`, `git diff` e `git log` para consultar.

## Documentação

| Arquivo | Conteúdo |
|---|---|
| `docs/01-contexto-e-escopo.md` | O que o kit define, o que o professor pediu, escopo e glossário |
| `docs/02-arquitetura-proposta.md` | Responsabilidades, fluxo, estados, escolha, rastreio, relógio, notificações, modelo de dados, API, pontos de sistemas distribuídos |
| `docs/03-eventos-e-integracoes.md` | Payloads, tópicos novos e pedidos a outros grupos |
| `docs/04-analise-do-kit.md` | Problemas do kit (K1 a K11 do grupo de Produtos; L1 a L16 nossos) |
| `docs/05-plano-de-trabalho.md` | Etapas 0 a 5, testes e roteiro da demonstração |
| `docs/06-pauta-de-decisoes.md` | Decisões D1 a D25 e perguntas ao professor |
| `docs/07-relatorio-tecnico.md` | Relatório técnico: arquitetura, testes e resultados, limitações, ADR-001 a ADR-025 |
| `docs/contratos/` | Propostas de contrato com outros grupos e, quando aprovados, JSON Schemas |
| `docs/explicacoes/` | Explicação de cada parte implementada, para o grupo estudar (uma por etapa) |

Convenções:

- Tudo em português do Brasil, frases curtas, tabelas quando houver comparação.
- O que ainda não foi decidido aparece como **proposta**. Ao mudar uma decisão, atualize a pauta e os documentos que apontam para ela (`D#`).
- Mantenha os identificadores estáveis (`D#`, `P#`, `K#`, `L#`). Não renumere; acrescente no fim.
- Quando uma decisão for aceita ou mudar, atualize o ADR correspondente no relatório técnico (`docs/07-relatorio-tecnico.md`, seção 12). ADRs novos entram no fim (ADR-026 em diante).
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
- Tópicos novos (`rastreio_atualizado`, `entrega_concluida`, `frete_indisponivel`, `relogio_ajustado`) são proposta até a Infraestrutura aprovar.

## Stack (D16)

Python 3.12 nos contêineres, FastAPI, `aiokafka`, `psycopg` 3 (assíncrono, com `psycopg_pool`), `jsonschema`, `prometheus-client`, `pytest`; k6 para carga. Telas em HTML, JavaScript e Leaflet sobre OpenStreetMap, seguindo o mockup do UX (D11).

## Organização do código

- `comum/comum/`: pacote compartilhado (instalado nas duas imagens). Use o que já existe antes de escrever de novo:
  - `outbox.gravar_evento(conn, ...)` para publicar qualquer evento, sempre dentro da transação da alteração;
  - `consumidor.ConsumidorIdempotente` para consumir; tratadores recebem `(conn, envelope)` e levantam `EventoInvalido` para mandar direto à DLT;
  - `erros.Problema(status, codigo, titulo, detalhe)` para erros de negócio (vira RFC 7807);
  - `auth.exigir_perfis(...)`, `web.paginacao`, `web.resposta_paginada`;
  - `relogio.Relogio.agora(conn)` para qualquer hora de negócio (nunca `datetime.now()` em regra de negócio). Exceção: tempos técnicos de espera da rede, como a rodada de 10 s, usam hora real. Não coloque cache no relógio: com fator alto, as cópias divergem;
  - `logs.correlacao(id)` em rotinas de segundo plano, para os logs levarem o `correlationId`;
  - notificações com `logistica/notificacoes.notificar(conn, ...)`, na mesma transação da mudança;
  - `eventos.validar_payload(nome, payload)` com os JSON Schemas de `comum/comum/contratos/`.
- `services/<servico>/<pacote>/`: `servico.py` (regras, recebe `conn`), `api.py` (rotas), `main.py` (montagem e rotinas). Regras puras ficam em módulos sem banco nem Kafka (`regras.py`, `cotacao.py`, `simulacao.py`) e têm teste unitário.
- Reserva de recurso disputado entre as cópias (caminhão, motorista, escolha do frete): gravação condicional (`UPDATE ... WHERE <ainda livre>` e conferir `rowcount`), não `FOR UPDATE` em listas inteiras.
- `frontend/`: telas estáticas (HTML, CSS, JS puro e Leaflet), servidas pelo contêiner `portal` (`infra/portal/`), que também faz o papel do gateway. `assets/portal.js` tem a sessão, a chamada à API (com erros RFC 7807), o relógio e o sino; cada página tem o seu `.js`. Não use `alert()` nem `confirm()`: use `Portal.avisoRapido` e `Portal.modal`. Arquivos com autenticação (PDF) são baixados com `Portal.baixar`. Cada página declara os perfis que a usam em `Portal.iniciar({ perfis })`. Teste a sintaxe com `node --check`.
- Transportadora `simulada = TRUE` cota sozinha; `simulada = FALSE` (Rodovia Sul, no seed) só cota digitando (`cotar_manualmente`).
- `testes_integracao/`: rodam contra o ambiente no ar. Use `apoio.py` (`consultar`, `publicar_pedido`, `mensagens_do_topico`, `esperar`, `docker_compose`, `metrica`) e as fixtures `api`, `entrar` e `relogio` do `conftest.py`. Confira o resultado no banco, na outbox e no tópico, não só na resposta da API.
- `services/<servico>/migracoes/NNN_*.sql`: DDL executado como `portal_ddl`; terminar com os GRANTs para o `svc_*`. Migrações só rodam com o volume do Postgres vazio (`docker compose down -v`).
- Os boilerplates do kit não consomem Kafka, guardam dados em memória e têm os problemas listados em `docs/04-analise-do-kit.md`. Não copie código deles sem aplicar as correções.

## Comandos

```bash
docker compose up -d --build          # ambiente completo (portal 8088, Postgres 15432, Redpanda 29092, Console 8091, serviços 8108/8118/8109/8119)
docker compose down -v                # derruba e apaga os dados (necessário após mudar migrações)
docker compose exec logistica-1 python -m comum.ferramentas.publicar_pedido_falso [--repetir 5]
docker compose exec logistica-1 python -m comum.ferramentas.gerar_token --perfil admin
docker compose exec logistica-1 python -m comum.ferramentas.cancelar_pedido_falso --pedido-id <id>
docker compose logs -f pedidos-falso  # papel do grupo de Pedidos (D23)
.venv/Scripts/python -m pytest        # testes unitários (criar a .venv com: pip install -e "comum[testes]")
.venv/Scripts/python -m pytest testes_integracao -v   # integração, com o ambiente no ar (acelera o relógio e derruba contêineres)
docker run --rm -i --network logistica-grupo5_default grafana/k6:0.54.0 run - < testes_carga/leitura.js   # carga
```

As senhas do `docker-compose.yml` são padrões de desenvolvimento, sobrescritas pelo `.env`. As credenciais do `.env.example` do kit são só de desenvolvimento; não copie senhas do kit para este repositório.
