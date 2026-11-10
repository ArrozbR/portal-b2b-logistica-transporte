# 04. Análise do kit de infraestrutura

Leitura do kit ([portal-b2b-kit-infra](https://github.com/Printf-PedroCardoso/portal-b2b-kit-infra), commit `630515c`) focada nos nossos dois serviços. Nada foi executado ainda: tudo abaixo é **análise estática** (leitura do código). Antes de levar à Infraestrutura, vale confirmar os itens principais rodando o kit.

## 1. Problemas gerais já apontados por outro grupo

O grupo de Fornecimento e Produtos analisou o kit no [Relatório Técnico](https://github.com/davicalvarenga/Sistema-MicServ-SD/blob/main/docs/relatorio-tecnico.md), seção 3.4. Os itens abaixo afetam todos os serviços, inclusive os nossos:

| # | Problema | Efeito para nós |
|---|---|---|
| K1 | `01-init.sql` dá os GRANTs antes de criar as tabelas. Eles **testaram** e o `svc_*` recebe `permission denied` | `svc_logistica` e `svc_transportadoras` não acessam as próprias tabelas |
| K2 | O `docker-compose.yml` raiz não passa `DB_USER`/`DB_PASSWORD`, e `common/db.py` usa `portal_admin` por padrão | Confirmado em `app1-logistica` e `app1-transportadoras` |
| K3 | Nenhum `requirements.txt` instala `aiokafka`, e `common/events.py` engole a falha de import | Confirmado no nosso `requirements.txt`: os eventos nunca chegam ao Redpanda |
| K4 | O contexto de build é a pasta do serviço, mas o `main.py` importa `common` da pasta de cima | O contêiner tende a falhar ao iniciar |
| K5 | Eventos processados e chaves de idempotência ficam em memória | Perde a idempotência ao reiniciar e entre `app1` e `app2` |
| K6 | Um produtor Kafka novo por evento, e a falha de publicação vira só um aviso | Lento e perde eventos sem avisar |
| K8 | `require_roles` dá erro de tipo (500) quando o token não tem `perfil` | Tratar como 403 |
| K9 | Erro RFC 7807 sem `timestamp`, e o 422 de validação do FastAPI fora do padrão | Precisamos do tratador próprio |
| K10 | `/health/ready` não testa nada e `/metrics` devolve número fixo | Implementar de verdade |
| K11 | Guia, `CONTRACTS.md`, script de tópicos e código divergem em nomes, chaves e campos | Ver L11 abaixo |

## 2. Problemas específicos de logística e transportadoras

| # | Problema | Onde | Efeito | Encaminhamento |
|---|---|---|---|---|
| L1 | **Nenhum consumidor Kafka.** A solicitação é criada por `POST /api/v1/logistica/solicitacoes`, a cotação por `POST /api/v1/logistica/cotacoes` e as transportadoras respondem por `POST /api/v1/transportadoras/responder-solicitacao` | `main.py` dos dois serviços | O fluxo por eventos do guia não existe; alguém precisa chamar as rotas na mão | Implementar os consumidores de `pedido_criado`, `cotacao_recebida` e `solicitacao_frete_criada`. As rotas HTTP de criação saem ou viram ferramenta de teste |
| L2 | `selecionar_frete` com menos de 2 cotações e **sem corpo** faz `dto.cotacao_id` com `dto = None` | `logistica-service/main.py` | 500 em vez de 422 | Corrigir no nosso código |
| L3 | A seleção exige pelo menos 2 cotações (comentário "RF-12"), mas o guia só diz "aguarda até 10 s". Não está definido o que fazer com 1 cotação ou nenhuma | Boilerplate e guia | Comportamento indefinido quando só uma transportadora atende a carga (ex.: refrigerada) | Decidir na pauta (D4) |
| L4 | A janela de 10 s não está implementada; a seleção só acontece quando alguém chama a rota | `logistica-service/main.py` | Sem seleção automática | Rotina de fechamento de janela (D14) |
| L5 | Nem `registrar_cotacao` nem `selecionar_frete` olham o status da solicitação | `logistica-service/main.py` | Aceita cotação depois da seleção, e uma segunda chamada sem `Idempotency-Key` seleciona de novo e publica outro `frete_selecionado` | Atualização condicional de status (arquitetura, seção 9) |
| L6 | Empate em preço e prazo fica decidido pela ordem de chegada das cotações | `sorted(...)` em `selecionar_frete` | Resultado não determinístico, ruim para teste | Desempate final (arquitetura, seção 5.1) |
| L7 | Só 2 transportadoras em memória, com preço e prazo fixos, que não dependem de distância, peso ou tipo de carga, e sem filtro de compatibilidade | `transportadoras-service/main.py` | Toda solicitação recebe as mesmas duas cotações. Comparação sem sentido | Motor de cotação (arquitetura, seção 5.3) |
| L8 | Tabelas sem origem, destino, tipo de carga e peso; nada para entrega e rastreio; `cotacao` sem unicidade por (`solicitacao_id`, `transportadora_id`) | `database/01-init.sql` | Não dá para cotar nem rastrear; uma reentrega duplica cotação | Proposta de DDL (arquitetura, seção 7) |
| L9 | Rotas sem autenticação nem RBAC | Os dois `main.py` | Qualquer um seleciona frete ou cota em nome de qualquer transportadora | Exigir JWT; `transportadoraId` sai do token, não do corpo |
| L10 | Listagens sem paginação | `listar_solicitacoes`, `listar_transportadoras` | Contraria a seção 4.6 do guia, e o QA vai cobrar | Paginar |
| L11 | Divergências no catálogo: o guia diz que `pedido_atualizado` vai para "Front-end, Auditoria" e o `CONTRACTS.md` diz `logistica-service`; o guia usa a chave `solicitacao_id` e o `CONTRACTS.md` `solicitacaoFreteId`; o guia chama o campo de versão de `version` e o código `eventVersion` | Guia e `CONTRACTS.md` | Risco de cada grupo seguir um arquivo diferente | Seguir `CONTRACTS.md` e o código; pedir unificação |
| L12 | Só o `pedidos-service` consome `frete_selecionado`, e ninguém publica nada depois disso. O próprio `pedidos-service` não tem consumidor: só muda status por `PATCH` | `CONTRACTS.md`, `pedidos-service/main.py` | O pedido nunca chega a `FRETE_SELECIONADO` nem a `ENTREGUE` por evento | Tópicos novos e consumidores (eventos, seção 4) |
| L13 | O front de logística do kit é um formulário genérico ("ID da Solicitação", "Status"), e o gateway o serve em `/logistica/`, enquanto o guia fala em `/app/logistica` | `frontends/apps/logistica/index.html`, `gateway/common_routes.conf` | Não atende aos mockups do UX | Combinar com UX (D11) e confirmar o caminho com a Infra |
| L14 | Janela de 10 s não combina com cotação manual: o mockup do UX tem a transportadora preenchendo valor, prazo e validade, o que leva minutos | Guia (seção 8.1) e mockup `portal_b2b_06_fretes.png` | Cotação manual nunca entraria na janela | Janela configurável (D3, D4) |
| L15 | A auditoria da seleção registra o usuário como `"system"` | `selecionar_frete` | Perde quem escolheu quando a seleção é manual | Usar o `sub` do token quando houver |
| L16 | O kit valida o token com HS256 e chave compartilhada e lê `empresaId` e `perfil` (em minúsculas). O grupo de Autenticação definiu outro token: RS256, chaves públicas no `/.well-known/jwks.json` e claims `tenant_id` e `active_scope` (`BUYER`, `SUPPLIER`, `CARRIER`, `TENANT_ADMIN`). Fonte: issue #2 do repositório de Fornecimento e Produtos (09/11/2026), que já mudou para RS256 | `services/common/auth.py` do kit | Seguimos o kit, então um token real da Autenticação seria recusado com 401 | Proposta D25; depende de a Infra atualizar o kit |

## 3. Conclusão

Os boilerplates servem como ponto de partida para estrutura de pastas, middleware de `X-Correlation-Id`, tratamento RFC 7807 e envelope de eventos. O resto (consumo de eventos, persistência, janela de cotação, RBAC, paginação) precisa ser escrito. A proposta é copiar o boilerplate e a pasta `common` para este repositório, aplicar as correções acima e registrar cada uma no relatório técnico, como fez o grupo de Fornecimento e Produtos.

## 4. O que já foi corrigido no nosso código

Na etapa 1, o código foi escrito do zero no pacote `comum/` e nos dois serviços, seguindo o kit nas convenções (rotas, envelope, erros, portas, schemas) e corrigindo os problemas acima:

| Item | Como ficou | Onde |
|---|---|---|
| K1 | GRANTs depois do `CREATE TABLE`, mais `ALTER DEFAULT PRIVILEGES` | `services/*/migracoes/001_estrutura.sql` |
| K2 | Cada serviço conecta com o seu `svc_*` | `docker-compose.yml`, `comum/comum/db.py` |
| K3 | `aiokafka` é dependência; falha de conexão é tentada de novo, não engolida | `comum/pyproject.toml`, `comum/comum/kafka.py` |
| K4 | Código compartilhado é um pacote instalado na imagem; build a partir da raiz | `comum/`, `services/*/Dockerfile` |
| K5 | `processed_events` no banco, na mesma transação da alteração | `comum/comum/consumidor.py` |
| K6 | Um produtor por processo; publicação pela outbox | `comum/comum/kafka.py`, `comum/comum/outbox.py` |
| K8 | Token sem perfil devolve 403 | `comum/comum/auth.py` |
| K9 | `timestamp` no corpo e 422 de validação em RFC 7807 | `comum/comum/erros.py` |
| K10 | `/health/ready` testa banco e Redpanda; `/metrics` com métricas reais | `comum/comum/web.py` |
| L1 | Consumidores Kafka de `pedido_criado`, `cotacao_recebida` e `solicitacao_frete_criada` | `services/*/.../main.py` |
| L4 | Rotina de prazos a cada segundo nas duas cópias, com `FOR UPDATE SKIP LOCKED` | `logistica/servico.py` |
| L5 | Cotação e escolha conferem o status; escolha com gravação condicional | `logistica/servico.py` |
| L6 | Desempate final por pontualidade e `transportadoraId` | `logistica/regras.py` |
| L7 | Motor de cotação por distância, peso e tipo de carga, com filtro de compatibilidade | `transportadoras/cotacao.py` |
| L8 | Tabelas com origem, destino, carga, peso e unicidade das cotações | `services/*/migracoes/` |
| L9 | JWT obrigatório e perfis por rota | `comum/comum/auth.py`, `*/api.py` |
| L10 | Listagens paginadas, `size > 100` → 422 | `comum/comum/web.py` |

Na etapa 2:

| Item | Como ficou | Onde |
|---|---|---|
| L2 | Corpo da escolha validado (`cotacaoId` ou `modo`); corpo errado → 422, nunca 500 | `logistica/api.py` |
| L3 | Mínimo de 1 cotação; sem cotação, `SEM_COTACAO` e depois `frete_indisponivel` (D4) | `logistica/servico.py` |
| L14 | Cotações aceitas até a escolha do comprador (12 h), não só nos 10 s | `logistica/servico.py` |
| L15 | Quem escolheu fica em `escolhida_por` | `migracoes/002_*.sql`, `logistica/servico.py` |

Na etapa 3:

| Item | Como ficou | Onde |
|---|---|---|
| L13 | Telas próprias no layout do mockup do UX (lista de entregas e rastreamento com mapa), em vez do formulário genérico do kit; servidas pelo contêiner `portal`, que também reparte as chamadas entre as cópias | `frontend/`, `infra/portal/` |

Fica pendente: L12 (depende do grupo de Pedidos) e L16 (depende da Infra e da Autenticação, D25). O caminho do front no gateway do kit (`/logistica/` ou `/app/logistica`) ainda precisa ser confirmado com a Infraestrutura quando as telas forem para o kit.
