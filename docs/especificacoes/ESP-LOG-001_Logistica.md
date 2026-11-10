# ESP-LOG-001 — Especificação de Requisitos: Logística e Frete (`logistica-service`)

## 0. Metadados

| Campo | Valor |
|---|---|
| Identificador | ESP-LOG-001 |
| Versão | 1.2 |
| Status | Em revisão (aguarda o gate G1 do grupo de Teste e Qualidade) |
| Serviço / Bounded context | `logistica-service`: solicitação de frete, escolha do frete, entrega e rastreio. Grupo 5 (Logística e Transporte) do Portal B2B Distribuído |
| Autores (PO / Dev / QA) | Grupo 5 — Logística e Transporte (PO e Dev). Revisão de QA: grupo de Teste e Qualidade |
| Data | 2026-11-10 |
| Documentos relacionados | ESP-TRP-001 (`transportadoras-service`); `docs/02-arquitetura-proposta.md`; `docs/03-eventos-e-integracoes.md`; `docs/06-pauta-de-decisoes.md` (D1 a D25); `docs/07-relatorio-tecnico.md`; JSON Schemas em `comum/comum/contratos/` |

## 1. Diretivas para a LLM geradora

1. Implemente **exatamente** o que está especificado. Não adicione endpoints, campos, tópicos, perfis ou regras que não estejam neste documento.
2. **Ordem de precedência** quando houver conflito aparente: Catálogo de erros (§10) e Contratos (§7) > Critérios de aceitação (§8) > Regras de negócio (§9) > Requisitos funcionais (§8) > texto descritivo.
3. Nomes de campos, tópicos, códigos de erro, rotas e valores de enumeração são **literais**: use-os byte a byte, com a mesma grafia e caixa.
4. Quando algo não estiver definido, escolha o comportamento mais simples que **não viole** nenhum item deste documento e registre a decisão em um comentário `# DECISÃO:` no código.
5. Entregue código completo e executável. Proibido: `TODO`, `pass` como implementação, pseudocódigo, trechos omitidos ("...").
6. Grave os arquivos completos na estrutura do §5 (pacote `logistica/` e, quando reaproveitar peças comuns, pacote `comum/`). Na resposta final, liste seus caminhos relativos.

## 2. Contexto

### 2.1 Objetivo do serviço

Para cada pedido do portal, abrir uma solicitação de frete, reunir as cotações das transportadoras, registrar a escolha do frete (pelo comprador ou pela regra do menor preço) e acompanhar a entrega até o fim, publicando os eventos que os outros serviços usam.

### 2.2 Posição na arquitetura

O grupo de Pedidos publica `pedido_criado` quando um pedido nasce e `pedido_atualizado` quando ele muda de status. Este serviço abre a solicitação e publica `solicitacao_frete_criada`. O `transportadoras-service` (ESP-TRP-001) responde com `cotacao_recebida`. O comprador escolhe pela API REST (via gateway), ou a regra automática escolhe; este serviço publica `frete_selecionado`. O `transportadoras-service` escala motorista e veículo e publica `rastreio_atualizado` durante a viagem. No fim, este serviço publica `entrega_concluida`; se não houver frete possível, `frete_indisponivel`. O administrador ajusta o relógio do módulo, e este serviço publica `relogio_ajustado` para o `transportadoras-service`.

```text
Pedidos ─────────[pedido_criado]──────────►┐
Pedidos ─────────[pedido_atualizado]──────►│
Transportadoras ─[cotacao_recebida]───────►│
Transportadoras ─[rastreio_atualizado]────►│
Telas ─► gateway ─REST /api/v1/logistica──►│ logistica-service
                                           ├──[solicitacao_frete_criada]──► Transportadoras
                                           ├──[frete_selecionado]─────────► Transportadoras, Pedidos
                                           ├──[frete_indisponivel]────────► Pedidos
                                           ├──[entrega_concluida]─────────► Pedidos
                                           ├──[relogio_ajustado]──────────► Transportadoras
                                           └──[logistica.dlt]─────────────► operação
```

## 3. Escopo

### 3.1 Dentro do escopo

- Abertura da solicitação de frete a partir de `pedido_criado`: coordenadas das cidades, distância, data de coleta e prazo de decisão.
- Registro das cotações recebidas por `cotacao_recebida`.
- Rotina de prazos: fim da rodada automática (10 s), escolha automática quando o prazo de decisão (12 h) vence e frete indisponível sem cotação.
- Escolha do frete pelo comprador (uma cotação) ou pela regra automática a pedido (botão), com `Idempotency-Key`.
- Comparação das cotações: selos, preço por tonelada-quilômetro e pontualidade de cada transportadora.
- Entrega: criação na escolha, acompanhamento por `rastreio_atualizado`, troca de transportadora quando a escolhida recusa a viagem, conclusão com `entrega_concluida` e contagem da pontualidade.
- Cancelamento do pedido por `pedido_atualizado`, inclusive quando o cancelamento chega antes do pedido.
- Relógio do módulo: consulta, ajuste pelo administrador e publicação de `relogio_ajustado`.
- Consultas de solicitações (inclusive pelo pedido), entregas, rastreio e entrega de um pedido.
- Ocorrências reportadas pelo comprador ou pelo fornecedor numa entrega (D22).
- Documentos demonstrativos da entrega em PDF, sem valor fiscal (D21).
- Notificações no portal para comprador e fornecedor, gravadas na mesma transação da mudança que as gera, e marcação de lida (D22).
- Saúde (`/health`, `/health/ready`) e métricas (`/metrics`).

### 3.2 Fora do escopo (não implementar)

- Envio de notificação por e-mail, SMS ou push; notificação para transportadora ou admin.
- Documento fiscal de verdade (CT-e, NF-e junto à SEFAZ). Edição ou exclusão de ocorrência.
- Telas (HTML, JavaScript, mapa).
- Login, emissão e renovação de token (grupo de Autenticação).
- Cadastro de transportadoras, motoristas e veículos; cálculo do preço da cotação; simulação da viagem (ESP-TRP-001).
- Cancelamento do frete pelo comprador, troca manual de transportadora, edição ou exclusão de cotação, rota por estrada, feriados.
- Leitura ou escrita no schema de outro serviço. Chamada HTTP a outro serviço para avançar o fluxo.
- Rota para zerar o estado. O ambiente de teste é recriado com `docker compose down -v` e `docker compose up -d --build`.

## 4. Glossário

| Termo | Definição precisa |
|---|---|
| Pedido | Pedido de compra do portal, identificado por `pedidoId`. Pertence ao grupo de Pedidos; este serviço só recebe os eventos. |
| Solicitação de frete | Pedido de transporte de um pedido, identificada por `id` (UUID4). No máximo uma por `pedidoId`. |
| Cotação | Proposta de uma transportadora para uma solicitação: `preco`, `prazo_dias` e `data_entrega_prevista`. No máximo uma por par (solicitação, transportadora). |
| Cotação válida | Cotação com `status` `"VALIDA"`. Só cotações válidas podem ser escolhidas. |
| Entrega | Execução do transporte da cotação escolhida, identificada por `id` (UUID4). Cada troca de transportadora cria uma entrega nova, com `tentativa` + 1. |
| Solicitação aberta | `status` ∈ {`"ABERTA"`, `"COTADA"`, `"SEM_COTACAO"`}. |
| Entrega ativa | `status` ∈ {`"AGUARDANDO_ALOCACAO"`, `"AGUARDANDO_COLETA"`, `"EM_TRANSITO"`}. |
| Entrega encerrada | `status` ∈ {`"ENTREGUE"`, `"CANCELADA"`, `"RECUSADA"`}. |
| Hora do módulo / agora | Valor do relógio do módulo (§5.1): `base_virtual + (hora real − base_real) × fator`. Sem ajuste gravado, é a hora real. Toda regra de negócio usa a hora do módulo. |
| Hora real | Relógio do computador, em UTC. Usado só na rodada automática (RN-10), em `atualizado_em` e no `timestamp` do envelope. |
| Instante | Data e hora em UTC, ISO-8601, com milissegundos e sufixo `Z`: `"2026-11-10T12:00:00.000Z"`. Na entrada, aceita qualquer ISO-8601 com fuso. |
| Data | `AAAA-MM-DD`: `"2026-11-11"`. |
| Valor monetário | Número JSON em reais, com no máximo 2 casas decimais (`6156.86`, `7113.3`). Cálculos com `Decimal`. |
| Dia útil | Segunda a sexta-feira. Feriados não contam. |
| Próximo dia útil de D | O primeiro dia útil depois de D (D não conta). Terça 2026-11-10 → quarta 2026-11-11; sexta 2026-11-13 → segunda 2026-11-16. |
| Distância | `arredondar(haversine(origem, destino) × 1,3; 1 casa)` em km. Raio da Terra 6371 km. O 1,3 representa a sinuosidade da estrada. |
| Preço por t·km | `preco ÷ (peso_kg ÷ 1000 × distancia_km)`, com 4 casas (arredondamento meio-para-o-par). `null` se o divisor for 0. |
| Pontualidade de uma transportadora | `entregas_no_prazo ÷ entregas`, contando as entregas concluídas neste serviço. Sem entregas, não há pontualidade. |
| Regra automática | Ordena as cotações válidas por: menor `preco`; menor `prazo_dias`; maior pontualidade (sem histórico conta 0); menor `transportadora_id` em ordem alfabética. A primeira vence. |
| Empresa do usuário | Claim `tenant_id` do token. |
| Perfil | `comprador`, `fornecedor`, `transportadora` ou `admin`, traduzido do token (§7.1). |
| Visível para o usuário | Comprador: `comprador_id` = empresa do usuário. Fornecedor: `fornecedor_id` = empresa do usuário. Admin: todas. |

## 5. Restrições técnicas

| Item | Valor obrigatório |
|---|---|
| Linguagem / versão | Python 3.12 |
| Framework | FastAPI com Pydantic v2 |
| Dependências permitidas | Biblioteca padrão, `fastapi` (com `starlette`), `uvicorn[standard]`, `pydantic`, `aiokafka`, `psycopg[binary,pool]` (versão 3, assíncrono, com `psycopg_pool`), `PyJWT[crypto]` (com `cryptography`), `jsonschema`, `prometheus-client` e o pacote `comum` do projeto. `fpdf2` só nos documentos em PDF (fora do escopo, §3.2). Nenhuma outra. |
| Persistência | PostgreSQL, schema `logistica`, usuário `svc_logistica`, pool de no máximo 5 conexões por instância (`DB_POOL_MAX`). Nenhum estado de negócio só em memória. |
| Instâncias | Duas cópias iguais (`logistica-1` na porta 8108 e `logistica-2` na 8118), atrás do gateway, com o mesmo banco. Qualquer rotina pode rodar nas duas ao mesmo tempo sem efeito duplicado. |
| Estrutura de arquivos | `services/logistica-service/logistica/`: `__init__.py` (constantes `SERVICO`, `SCHEMA`, `TOPICO_DLT`), `main.py` (montagem e rotinas), `api.py` (rotas), `servico.py` (regras com banco), `rastreio.py` (consumo do rastreio), `regras.py` (regras puras, sem banco nem Kafka). `notificacoes.py` e `documentos.py` existem e ficam fora desta versão (§3.2). DDL em `services/logistica-service/migracoes/NNN_*.sql`. |
| Ponto de entrada | `uvicorn logistica.main:app --host 0.0.0.0 --port 8108`. O `lifespan` abre o pool e inicia três rotinas: consumidor, publicador da outbox e prazos (a cada 1 s). |
| Configuração | `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_POOL_MAX` (5), `KAFKA_BOOTSTRAP_SERVERS`, `JWT_ALGORITHM` (`RS256`), `AUTH_JWKS_URL`, `JWT_SECRET_KEY` (só com `HS256`), `RODADA_COTACAO_SEGUNDOS` (10), `PRAZO_DECISAO_SEGUNDOS` (43200), `LOG_LEVEL` (`INFO`). |
| Formato de data/hora | Instante e Data (glossário). |
| Formato monetário | Valor monetário (glossário). |
| Logs | Uma linha JSON por registro no stdout, com `timestamp`, `level`, `service`, `correlationId` e `message`. Proibido `print()`. |

### 5.1 Portas (interfaces de infraestrutura)

```python
# Barramento: só por meio da outbox, dentro da transação da alteração.
async def gravar_evento(conn, schema: str, servico: str, topico: str, chave: str,
                        payload: dict, id_correlacao: str | None = None) -> dict: ...

# Consumo: um tratador por tópico; recebe a conexão já em transação e o envelope.
Tratador = Callable[[AsyncConnection, dict], Awaitable[None]]
class EventoInvalido(Exception): ...   # levantada pelo tratador: vai direto para a DLT

# Relógio do módulo.
class Relogio:
    async def agora(self, conn: AsyncConnection | None = None) -> datetime: ...   # sempre com fuso UTC

# Banco: pool psycopg 3 assíncrono.
class BancoDeDados:
    def transacao(self) -> AsyncContextManager[AsyncConnection]: ...   # commit no fim; rollback se houver exceção
```

Comportamento das portas:

- **Publicação.** Todo evento é gravado na tabela `logistica.outbox` na mesma transação da alteração de negócio. Uma rotina lê a outbox em ordem de gravação e publica no Kafka (Redpanda) com chave = `aggregateId`, em até 1 s depois do commit com o ambiente saudável. Só uma cópia publica por vez (trava `pg_try_advisory_xact_lock`). A entrega é "pelo menos uma vez": um evento pode sair duplicado; os consumidores são idempotentes.
- **Ordem de uma escrita.** Validar → alterar o estado → gravar o evento na outbox → commit. Se qualquer passo falhar, nada é gravado, nem o evento. Kafka fora do ar não impede a escrita: o evento espera na outbox.
- **Consumo.** Grupo `logistica-service`, tópicos `pedido_criado`, `cotacao_recebida`, `pedido_atualizado` e `rastreio_atualizado`. O offset só é confirmado depois de a mensagem ser processada ou ir para a DLT (RN-30).
- **Relógio.** Estado numa linha da tabela `logistica.relogio` (`base_real`, `base_virtual`, `fator`, `versao`). Só este serviço altera (API-12). Cada chamada de `agora` lê o banco (sem cache), para as duas cópias verem a mesma hora. Proibido `datetime.now()` em regra de negócio, exceto na rodada (RN-10).
- **Autenticação.** Chaves públicas no JWKS de `AUTH_JWKS_URL`, guardadas por 1 hora. Um `kid` desconhecido faz nova busca, no máximo uma a cada 5 s.

## 6. Modelo de domínio

### 6.1 Entidades

Os nomes abaixo são os da resposta da API (§7.2).

#### SolicitacaoFrete

| Atributo | Tipo | Obrigatório | Restrições / origem |
|---|---|---|---|
| id | string | Sim | UUID4 gerado pelo serviço. |
| pedido_id | string | Sim | `pedidoId` do evento; único. |
| produto_id, produto_nome | string | Sim | Do evento. |
| valor_carga | valor monetário | Sim | `valorTotal` do evento; ≥ 0. |
| comprador_id, fornecedor_id | string | Sim | Do evento. |
| tipo_carga | enum | Sim | `tipoTransporte` do evento: `"GRANEL"`, `"REFRIGERADO"`, `"CARGA_SECA"` ou `"PERIGOSO"`. |
| peso_kg | número | Sim | `pesoKg` do evento; > 0. |
| origem_cidade, origem_uf, destino_cidade, destino_uf | string | Sim | Nome e UF da tabela de cidades (Apêndice A), não o texto recebido. |
| origem_lat, origem_lon, destino_lat, destino_lon | número | Sim | Da tabela de cidades. |
| distancia_km | número | Sim | Distância (glossário), 1 casa. |
| data_coleta_prevista | data | Sim | Próximo dia útil da data UTC de `aberta_em` (RN-03). |
| data_entrega_desejada | data ou `null` | Não | `dataEntregaDesejada` do evento. |
| aberta_em | instante | Sim | Hora do módulo ao consumir o evento. |
| prazo_decisao_em | instante | Sim | `aberta_em` + 12 h (RN-04). |
| cotacao_escolhida_id | string ou `null` | Não | Cotação escolhida. |
| criterio | enum ou `null` | Não | `"ESCOLHA_COMPRADOR"` ou `"AUTOMATICO_MENOR_PRECO"`. |
| escolhida_por | string ou `null` | Não | `sub` de quem escolheu; `null` quando foi a rotina de prazos ou a troca de transportadora. |
| escolhida_em | instante ou `null` | Não | Hora do módulo na escolha. |
| status | enum | Sim | §6.2. Inicial `"ABERTA"`. |

Internos (não aparecem na API): `rodada_ate` (hora real da abertura + 10 s), `correlation_id` (do `pedido_criado`).

#### Cotacao

| Atributo | Tipo | Obrigatório | Restrições / origem |
|---|---|---|---|
| id | string | Sim | `cotacaoId` do evento; único no serviço. |
| transportadora_id | string | Sim | Do evento. |
| transportadora_nome | string ou `null` | Não | Do evento. |
| preco | valor monetário | Sim | > 0. |
| prazo_dias | inteiro | Sim | Dias úteis; ≥ 1. |
| data_entrega_prevista | data ou `null` | Não | Do evento. |
| valida_ate | instante ou `null` | Não | Do evento. Informativo: não bloqueia a escolha. |
| origem_cotacao | enum | Sim | `"SIMULADA"` (padrão quando ausente) ou `"DIGITADA"`. |
| observacoes | string ou `null` | Não | Até 500 caracteres. |
| status | enum | Sim | `"VALIDA"`, `"RECUSADA_TARDE"` (chegou com a solicitação fechada) ou `"VIAGEM_RECUSADA"` (a transportadora escolhida recusou a viagem). |
| recebida_em | instante | Sim | Hora do módulo ao consumir. |

#### Entrega

| Atributo | Tipo | Obrigatório | Restrições / origem |
|---|---|---|---|
| id | string | Sim | UUID4 gerado na escolha. |
| pedido_id, solicitacao_id, cotacao_id | string | Sim | Da escolha. |
| tentativa | inteiro | Sim | 1 na primeira escolha; +1 a cada troca de transportadora. Único por pedido. |
| status | enum | Sim | §6.2. Inicial `"AGUARDANDO_ALOCACAO"`. |
| transportadora_id | string | Sim | Da cotação. |
| transportadora_nome | string ou `null` | Não | Da cotação; atualizado por `VIAGEM_ALOCADA`. |
| transportadora_telefone | string ou `null` | Não | `VIAGEM_ALOCADA`. |
| motorista_nome, motorista_telefone, motorista_cnh_mascarada | string ou `null` | Não | `VIAGEM_ALOCADA`. A CNH chega mascarada (`"*******3465"`); o número completo nunca entra neste serviço. |
| veiculo_placa, veiculo_tipo | string ou `null` | Não | `VIAGEM_ALOCADA`. |
| coleta_prevista, coletada_em, previsao_chegada, entregue_em, posicao_em | instante ou `null` | Não | Eventos de rastreio. |
| prazo_prometido | data ou `null` | Não | `data_entrega_prevista` da cotação escolhida. |
| progresso | número | Sim | 0 a 1. Inicial 0. |
| posicao_lat, posicao_lon | número ou `null` | Não | Última posição recebida. |
| rota | lista de `[lat, lon]` ou `null` | Não | `VIAGEM_ALOCADA`. |
| com_ocorrencia | booleano | Sim | Inicial `false`; `true` depois de um rastreio `OCORRENCIA` ou de uma ocorrência reportada pela API-15. |
| no_prazo | booleano ou `null` | Não | `ENTREGA_REALIZADA`. |
| atraso_horas | número ou `null` | Não | `ENTREGA_REALIZADA`. |
| atualizado_em | instante | Sim | Hora real da última alteração (campo técnico). |

Interno: `ultima_sequencia` (inteiro, inicial 0): maior `sequencia` de rastreio já aplicada.

#### EventoRastreio

`sequencia`, `tipo`, `descricao`, `lat`, `lon`, `progresso`, `ocorrido_em`: cópia de cada `rastreio_atualizado` aplicado, por entrega. Chave (entrega, sequencia).

#### DesempenhoTransportadora

`transportadora_id`, `nome`, `entregas`, `entregas_no_prazo`, `atraso_total_horas`. Uma linha por transportadora com pelo menos uma entrega concluída (RN-25).

#### Ocorrencia

| Atributo | Tipo | Obrigatório | Restrições / origem |
|---|---|---|---|
| id | string | Sim | UUID4 gerado pelo serviço. |
| autor_papel | enum | Sim | `"comprador"` ou `"fornecedor"`: o perfil de quem reportou. |
| descricao | string | Sim | Sem os espaços das pontas; 5 a 500 caracteres depois de tirá-los (RN-33). |
| ocorrida_em | instante | Sim | Hora do módulo ao reportar. |

Internos (não aparecem na API): `entrega_id`, `pedido_id`, `autor_id` (`sub` de quem reportou).

#### Notificacao

| Atributo | Tipo | Obrigatório | Restrições / origem |
|---|---|---|---|
| id | string | Sim | UUID4 gerado pelo serviço. |
| tipo | enum | Sim | Um dos 10 tipos da RN-32. |
| titulo | string | Sim | Literal da RN-32 para o tipo. |
| mensagem | string | Sim | Texto em português com o `pedido_id`; pode mudar (só o `titulo` e o `tipo` são literais). Datas na mensagem no horário de Brasília (`dd/mm/aaaa hh:mm`), valores como `R$ 7.113,30`. |
| pedido_id, solicitacao_id | string | Sim | Do pedido que gerou a notificação. |
| lida | booleano | Sim | Inicial `false`; muda pela API-18. |
| criada_em | instante | Sim | Hora do módulo na mudança que gerou a notificação. |

Internos: `empresa_id` e `papel` (`"comprador"` ou `"fornecedor"`), o destinatário; `criado_em_real` (hora real, desempate da ordem).

#### Outros

| Tabela | Uso |
|---|---|
| `pedido_cancelado` | `pedido_id` de cancelamento que chegou antes do pedido (RN-06). |
| `idempotency_keys` | Chave de idempotência e resposta memorizada da escolha (RN-15). |
| `processed_events` | `eventId` já consumidos (RN-30). |
| `outbox` | Eventos a publicar (§5.1). |
| `relogio` | Estado do relógio (§5.1). |

### 6.2 Estados e transições

**Solicitação de frete**

| Estado atual | Evento / comando | Condição | Próximo estado |
|---|---|---|---|
| (inexistente) | `pedido_criado` válido | Sem solicitação para o `pedidoId` e pedido não cancelado antes (RN-05, RN-06) | ABERTA |
| ABERTA, SEM_COTACAO | `cotacao_recebida` válida | — | COTADA |
| ABERTA | Rotina de prazos | Hora real ≥ abertura + 10 s (RN-10) | SEM_COTACAO |
| COTADA | API-05 com `cotacaoId` | `agora ≤ prazo_decisao_em` | SELECIONADA (`ESCOLHA_COMPRADOR`) |
| COTADA | API-05 com `modo: AUTOMATICO` | — | SELECIONADA (`AUTOMATICO_MENOR_PRECO`) |
| COTADA | Rotina de prazos | `agora ≥ prazo_decisao_em` | SELECIONADA (`AUTOMATICO_MENOR_PRECO`) |
| SEM_COTACAO | Rotina de prazos | `agora ≥ prazo_decisao_em` | INDISPONIVEL |
| ABERTA, COTADA, SEM_COTACAO | `pedido_atualizado` CANCELADO | — | CANCELADA |
| SELECIONADA | `rastreio_atualizado` VIAGEM_RECUSADA | Há outra cotação válida | SELECIONADA (outra cotação, `AUTOMATICO_MENOR_PRECO`) |
| SELECIONADA | `rastreio_atualizado` VIAGEM_RECUSADA | Não há outra cotação válida | INDISPONIVEL |
| SELECIONADA, INDISPONIVEL, CANCELADA | `pedido_atualizado` CANCELADO | — | (não muda) |

INDISPONIVEL e CANCELADA são finais. SELECIONADA só muda por recusa da viagem.

**Entrega**

| Estado atual | Evento | Condição | Próximo estado |
|---|---|---|---|
| (inexistente) | Escolha do frete ou troca de transportadora | — | AGUARDANDO_ALOCACAO |
| Não encerrada | `VIAGEM_ALOCADA` | Sequência nova (RN-21) | AGUARDANDO_COLETA |
| Não encerrada | `VIAGEM_RECUSADA` | Sequência nova | RECUSADA |
| Não encerrada | `COLETA_REALIZADA` | Sequência nova | EM_TRANSITO |
| Não encerrada | `ENTREGA_REALIZADA` | Sequência nova | ENTREGUE |
| Ativa | `pedido_atualizado` CANCELADO | — | CANCELADA |
| Não encerrada | `POSICAO`, `PARADA`, `PREVISAO_ATUALIZADA`, `OCORRENCIA` | Sequência nova | (não muda) |

ENTREGUE, CANCELADA e RECUSADA são finais. Rastreio de entrega encerrada é ignorado.

**Cotação:** VALIDA → VIAGEM_RECUSADA (a transportadora recusou a viagem). RECUSADA_TARDE é final desde o recebimento.

## 7. Contratos de interface

### 7.1 Autenticação e contexto da requisição

Toda rota, exceto as públicas, exige `Authorization: Bearer <token>`. Rotas públicas: `/health`, `/health/ready`, `/metrics`, `/docs` e `/openapi.json`.

O token é o JWT RS256 do grupo de Autenticação (D25). O algoritmo vem da configuração `JWT_ALGORITHM`, nunca do cabeçalho do token. A chave pública vem do JWKS (`AUTH_JWKS_URL`), pelo `kid` do cabeçalho. Claims usados (os do Identity-Service, `TokenIssuer.cs`): `sub` (usuário), `iss`, `aud`, `exp`, `platform_role` (`NONE`, `SUPPORT_AGENT` ou `PLATFORM_ADMIN`), `view_mode` (`NONE`, `SINGLE` ou `MACRO_GROUP`), `tenant_id` (empresa), `active_scope` e `permissions`. `sub`, `exp`, `iss` e `aud` são obrigatórios; `iss` deve ser `JWT_ISSUER` (padrão `"identity-service"`) e `aud` deve ser `JWT_AUDIENCE` (padrão `"b2b-platform"`).

| Token | Perfil no módulo |
|---|---|
| `platform_role` `"PLATFORM_ADMIN"`, ou `permissions` contém `"logistica:admin"` (com qualquer `active_scope`, com ou sem empresa) | `admin` |
| Sem `tenant_id` ou sem `active_scope` (token do login, `view_mode` `"NONE"`, ou de grupo, `"MACRO_GROUP"`) | 403 `CONTEXTO_NAO_SELECIONADO` |
| `active_scope` `"BUYER"` | `comprador` |
| `active_scope` `"SUPPLIER"` | `fornecedor` |
| `active_scope` `"CARRIER"` | `transportadora` |
| `active_scope` `"TENANT_ADMIN"` sem ser administrador da plataforma | 403 `PERFIL_NAO_PERMITIDO` |
| Outro `active_scope` | 403 `PERFIL_AUSENTE` |

Verificação, nesta ordem (para no primeiro erro):

1. Sem cabeçalho `Authorization: Bearer` → 401 `NAO_AUTENTICADO`.
2. Cabeçalho do token ilegível ou sem `kid` → 401 `TOKEN_INVALIDO`.
3. JWKS inacessível → 503 `AUTENTICACAO_INDISPONIVEL`. `kid` fora do JWKS → 401 `TOKEN_INVALIDO`.
4. Assinatura inválida, algoritmo diferente do configurado, sem `sub`, `exp`, `iss` ou `aud`, ou `iss` ou `aud` diferentes dos configurados → 401 `TOKEN_INVALIDO`. Expirado (com assinatura válida) → 401 `TOKEN_EXPIRADO`.
5. Tradução do perfil, na ordem da tabela acima (o administrador da plataforma vem antes da falta de contexto).
6. Perfil fora dos permitidos da rota → 403 `PERFIL_NAO_PERMITIDO`.

Onde `JWT_ALGORITHM=HS256` (formato do kit da Infraestrutura), o token é conferido com `JWT_SECRET_KEY`, e os claims são `sub`, `empresaId` (ou `empresa_id`), `perfil` (um dos 4 perfis) e `exp`. O padrão é `RS256`.

O cabeçalho `X-Correlation-Id`, se presente, é o identificador da requisição; se ausente, o serviço gera um. Ele volta no cabeçalho da resposta, nos logs e nos eventos gravados pela requisição.

### 7.2 API REST

Prefixo das rotas de negócio: `/api/v1/logistica`. Respostas de sucesso em `application/json`. Os campos das entidades saem em `snake_case` (§6.1); as respostas compostas (escolha, comparação, rastreio, relógio) e os eventos usam `camelCase`. As duas grafias são literais.

Listagens paginadas: `?page=` (≥ 1, padrão 1) e `?size=` (1 a 100, padrão 10). Corpo: `{"items": [...], "page": 1, "size": 10, "total": 35}`.

| ID | Método | Rota | Perfis | Sucesso | Erros possíveis (na ordem de verificação) |
|---|---|---|---|---|---|
| API-01 | GET | `/health` | público | 200 | — |
| API-02 | GET | `/health/ready` | público | 200 | 503 (corpo próprio) |
| API-03 | GET | `/metrics` | público | 200 | — |
| API-04 | GET | `/api/v1/logistica/solicitacoes` | comprador, fornecedor, admin | 200 | 401/503 (§7.1) → 403 → 422 `DADOS_INVALIDOS` |
| API-05 | GET | `/api/v1/logistica/solicitacoes/{solicitacao_id}` | comprador, fornecedor, admin | 200 | 401/503 → 403 → 404 `SOLICITACAO_NAO_ENCONTRADA` |
| API-06 | POST | `/api/v1/logistica/solicitacoes/{solicitacao_id}/selecionar-frete` | comprador, admin | 200 | 422 (JSON ilegível) → 401/503 → 403 → 422 `DADOS_INVALIDOS` → 400 `IDEMPOTENCY_KEY_AUSENTE` → (replay: 200) → 404 `SOLICITACAO_NAO_ENCONTRADA` → 409 `FRETE_JA_ESCOLHIDO` / `SEM_COTACAO_PARA_ESCOLHER` / `SOLICITACAO_ENCERRADA` → 409 `PRAZO_DE_ESCOLHA_ENCERRADO` → 404 `COTACAO_NAO_ENCONTRADA` → 409 `FRETE_JA_ESCOLHIDO` |
| API-07 | GET | `/api/v1/logistica/solicitacoes/{solicitacao_id}/comparacao` | comprador, fornecedor, admin | 200 | 401/503 → 403 → 404 `SOLICITACAO_NAO_ENCONTRADA` |
| API-08 | GET | `/api/v1/logistica/entregas` | comprador, fornecedor, admin | 200 | 401/503 → 403 → 422 `DADOS_INVALIDOS` |
| API-09 | GET | `/api/v1/logistica/entregas/{entrega_id}` | comprador, fornecedor, admin | 200 | 401/503 → 403 → 404 `ENTREGA_NAO_ENCONTRADA` |
| API-10 | GET | `/api/v1/logistica/entregas/{entrega_id}/rastreio` | comprador, fornecedor, admin | 200 | 401/503 → 403 → 404 `ENTREGA_NAO_ENCONTRADA` |
| API-11 | GET | `/api/v1/logistica/pedidos/{pedido_id}/entrega` | comprador, fornecedor, admin | 200 | 401/503 → 403 → 404 `ENTREGA_NAO_ENCONTRADA` |
| API-12 | GET | `/api/v1/logistica/relogio` | qualquer perfil | 200 | 401/503 → 403 (só pelos casos 6 do §7.1) |
| API-13 | POST | `/api/v1/logistica/admin/relogio` | admin | 200 | 422 (JSON ilegível) → 401/503 → 403 → 422 `DADOS_INVALIDOS` |
| API-14 | GET | `/api/v1/logistica/entregas/{entrega_id}/ocorrencias` | comprador, fornecedor, admin | 200 | 401/503 → 403 → 404 `ENTREGA_NAO_ENCONTRADA` |
| API-15 | POST | `/api/v1/logistica/entregas/{entrega_id}/ocorrencias` | comprador, fornecedor | 201 | 422 (JSON ilegível) → 401/503 → 403 → 422 `DADOS_INVALIDOS` → 404 `ENTREGA_NAO_ENCONTRADA` → 409 `ENTREGA_ENCERRADA` |
| API-16 | GET | `/api/v1/logistica/entregas/{entrega_id}/documentos/{tipo}` | comprador, fornecedor, admin | 200 (`application/pdf`) | 401/503 → 403 → 422 `DADOS_INVALIDOS` → 404 `ENTREGA_NAO_ENCONTRADA` → 409 `DOCUMENTO_INDISPONIVEL` |
| API-17 | GET | `/api/v1/logistica/notificacoes` | comprador, fornecedor | 200 | 401/503 → 403 → 422 `DADOS_INVALIDOS` |
| API-18 | PATCH | `/api/v1/logistica/notificacoes/{notificacao_id}` | comprador, fornecedor | 200 | 422 (JSON ilegível) → 401/503 → 403 → 422 `DADOS_INVALIDOS` → 404 `NOTIFICACAO_NAO_ENCONTRADA` |

#### API-01 — Saúde

Resposta 200: `{"status": "UP", "service": "logistica-service", "timestamp": "2026-11-10T12:00:00.000Z"}`

#### API-02 — Prontidão

Testa o banco (`SELECT 1`) e o produtor Kafka, cada um com limite de 3 s.

Resposta 200:
```json
{"status": "READY", "service": "logistica-service", "checks": {"banco": "UP", "kafka": "UP"}, "timestamp": "2026-11-10T12:00:00.000Z"}
```
Resposta 503 (exemplo com o Redpanda fora): `{"status": "NOT_READY", "service": "logistica-service", "checks": {"banco": "UP", "kafka": "DOWN: KafkaConnectionError"}, "timestamp": "..."}`

#### API-03 — Métricas

Texto no formato Prometheus, com os contadores `http_requests_total{service,method,route,status}`, `eventos_consumidos_total{service,topic,resultado}` (`resultado` ∈ `processado`, `duplicado`, `dlt`), `eventos_publicados_total{service,topic}` e o histograma `http_request_duration_seconds`.

#### API-04 — Listar solicitações

Parâmetros: `status` (opcional, um dos 6 status da solicitação), `pedido_id` (opcional, 1 a 64 caracteres; igualdade exata, devolve no máximo 1 item, RN-05), `page`, `size`. Os filtros se somam (E). Só as visíveis para o usuário, ordenadas por `aberta_em` decrescente. Cada item tem os campos da API-05, sem `cotacoes`.

```json
{
  "items": [
    {
      "id": "5c0e7b9a-3d2f-4e8a-9b1c-7f6a2d4e8c10",
      "pedido_id": "PED-1001",
      "produto_id": "prod-soja",
      "produto_nome": "Soja em grão",
      "valor_carga": 192000.0,
      "comprador_id": "emp-comprador-1",
      "fornecedor_id": "emp-fornecedor-1",
      "tipo_carga": "GRANEL",
      "peso_kg": 24000.0,
      "origem_cidade": "Sorriso", "origem_uf": "MT", "origem_lat": -12.5453, "origem_lon": -55.7114,
      "destino_cidade": "Santos", "destino_uf": "SP", "destino_lat": -23.9608, "destino_lon": -46.3336,
      "distancia_km": 2091.1,
      "data_coleta_prevista": "2026-11-11",
      "data_entrega_desejada": "2026-11-30",
      "aberta_em": "2026-11-10T12:00:00.000Z",
      "prazo_decisao_em": "2026-11-11T00:00:00.000Z",
      "cotacao_escolhida_id": null,
      "criterio": null,
      "escolhida_por": null,
      "escolhida_em": null,
      "status": "COTADA"
    }
  ],
  "page": 1,
  "size": 10,
  "total": 1
}
```

#### API-05 — Detalhe da solicitação

Os campos da API-04 e mais `cotacoes`, ordenadas por `preco` e depois `prazo_dias`, crescentes. Inclui cotações de qualquer `status`.

```json
{
  "id": "5c0e7b9a-3d2f-4e8a-9b1c-7f6a2d4e8c10",
  "pedido_id": "PED-1001",
  "...": "(demais campos da API-04)",
  "status": "COTADA",
  "cotacoes": [
    {
      "id": "3996972a-f710-5b2d-bb56-e01716c4cf05",
      "transportadora_id": "transp-economica",
      "transportadora_nome": "Econômica Transportes",
      "preco": 6156.86,
      "prazo_dias": 8,
      "data_entrega_prevista": "2026-11-23",
      "valida_ate": "2026-11-11T00:00:00.000Z",
      "origem_cotacao": "SIMULADA",
      "observacoes": null,
      "status": "VALIDA",
      "recebida_em": "2026-11-10T12:00:00.400Z"
    },
    {
      "id": "1613289a-100e-598d-bc42-9b1f9f1d2293",
      "transportadora_id": "transp-graneleira",
      "transportadora_nome": "Graneleira Centro-Oeste",
      "preco": 7113.3,
      "prazo_dias": 5,
      "data_entrega_prevista": "2026-11-18",
      "valida_ate": "2026-11-11T00:00:00.000Z",
      "origem_cotacao": "SIMULADA",
      "observacoes": null,
      "status": "VALIDA",
      "recebida_em": "2026-11-10T12:00:00.410Z"
    },
    {
      "id": "c5d00486-d2af-5884-8ed9-0a0dafa8c84d",
      "transportadora_id": "transp-expressa",
      "transportadora_nome": "Expressa Cargas Rápidas",
      "preco": 9026.18,
      "prazo_dias": 4,
      "data_entrega_prevista": "2026-11-17",
      "valida_ate": "2026-11-11T00:00:00.000Z",
      "origem_cotacao": "SIMULADA",
      "observacoes": null,
      "status": "VALIDA",
      "recebida_em": "2026-11-10T12:00:00.420Z"
    }
  ]
}
```

#### API-06 — Escolher o frete

Cabeçalhos: `Authorization`, `Idempotency-Key` (obrigatório, até 100 caracteres; RN-15).

Requisição, uma das duas formas (exatamente um dos dois campos):
```json
{"cotacaoId": "1613289a-100e-598d-bc42-9b1f9f1d2293"}
```
```json
{"modo": "AUTOMATICO"}
```

Resposta 200: o payload do `frete_selecionado` (§7.4) mais `transportadoraNome`.
```json
{
  "pedidoId": "PED-1001",
  "solicitacaoFreteId": "5c0e7b9a-3d2f-4e8a-9b1c-7f6a2d4e8c10",
  "entregaId": "e7a41c22-6b0d-4f3e-8a5c-1d9b2e7f4a63",
  "tentativa": 1,
  "cotacaoId": "1613289a-100e-598d-bc42-9b1f9f1d2293",
  "transportadoraId": "transp-graneleira",
  "preco": 7113.3,
  "prazoDias": 5,
  "dataEntregaPrevista": "2026-11-18",
  "criterio": "ESCOLHA_COMPRADOR",
  "status": "FRETE_SELECIONADO",
  "transportadoraNome": "Graneleira Centro-Oeste"
}
```
No replay (RN-15), o corpo tem os mesmos campos e valores (a ordem das chaves pode mudar), e a resposta traz o cabeçalho `X-Idempotent-Replay: true`.

#### API-07 — Comparação das cotações

```json
{
  "solicitacao": { "id": "5c0e7b9a-3d2f-4e8a-9b1c-7f6a2d4e8c10", "...": "(campos da API-04)", "status": "COTADA" },
  "cotacoes": [
    {
      "id": "3996972a-f710-5b2d-bb56-e01716c4cf05",
      "transportadora_id": "transp-economica",
      "transportadora_nome": "Econômica Transportes",
      "preco": 6156.86,
      "prazo_dias": 8,
      "data_entrega_prevista": "2026-11-23",
      "valida_ate": "2026-11-11T00:00:00.000Z",
      "origem_cotacao": "SIMULADA",
      "observacoes": null,
      "status": "VALIDA",
      "recebida_em": "2026-11-10T12:00:00.400Z",
      "preco_t_km": 0.1227,
      "selos": ["MAIS_BARATA", "RECOMENDADA_PELA_REGRA"],
      "escolhida": false,
      "desempenho": {"entregas": 0, "pct_no_prazo": null, "atraso_medio_horas": null}
    }
  ],
  "podeEscolher": true,
  "entregaId": null,
  "horaDoModulo": "2026-11-10T12:01:00.000Z"
}
```
- `cotacoes`: todas as cotações, na ordem da API-05, cada uma com `preco_t_km`, `selos`, `escolhida` e `desempenho` (RN-26). O exemplo mostra só a primeira.
- `entregaId`: a entrega de maior `tentativa` com `status` ≠ `"RECUSADA"`; `null` se não houver.

#### API-08 — Listar entregas

Parâmetros: `status` (opcional, um dos 6 status da entrega), `incluir_recusadas` (booleano, padrão `false`), `page`, `size`. Só as visíveis para o usuário (pela solicitação), ordenadas pela criação, da mais nova para a mais antiga (RN-29).

```json
{
  "items": [
    {
      "id": "e7a41c22-6b0d-4f3e-8a5c-1d9b2e7f4a63",
      "pedido_id": "PED-1001",
      "tentativa": 1,
      "status": "AGUARDANDO_COLETA",
      "transportadora_id": "transp-graneleira",
      "transportadora_nome": "Graneleira Centro-Oeste",
      "progresso": 0.0,
      "previsao_chegada": "2026-11-18T17:00:00.000Z",
      "prazo_prometido": "2026-11-18",
      "entregue_em": null,
      "no_prazo": null,
      "atraso_horas": null,
      "com_ocorrencia": false,
      "veiculo_placa": "PAS6J78",
      "produto_nome": "Soja em grão",
      "peso_kg": 24000.0,
      "tipo_carga": "GRANEL",
      "origem_cidade": "Sorriso", "origem_uf": "MT",
      "destino_cidade": "Santos", "destino_uf": "SP",
      "atualizado_em": "2026-11-10T12:05:00.420Z"
    }
  ],
  "page": 1, "size": 10, "total": 1
}
```

#### API-09 — Detalhe da entrega

```json
{
  "id": "e7a41c22-6b0d-4f3e-8a5c-1d9b2e7f4a63",
  "pedido_id": "PED-1001",
  "tentativa": 1,
  "status": "AGUARDANDO_COLETA",
  "solicitacao_id": "5c0e7b9a-3d2f-4e8a-9b1c-7f6a2d4e8c10",
  "cotacao_id": "1613289a-100e-598d-bc42-9b1f9f1d2293",
  "transportadora_id": "transp-graneleira",
  "transportadora_nome": "Graneleira Centro-Oeste",
  "transportadora_telefone": "(65) 4000-1003",
  "motorista_nome": "Roberto Nunes",
  "motorista_telefone": "(66) 99544-3322",
  "motorista_cnh_mascarada": "*******3465",
  "veiculo_placa": "PAS6J78",
  "veiculo_tipo": "CARRETA_GRANELEIRA",
  "coleta_prevista": "2026-11-10T14:05:00.300Z",
  "coletada_em": null,
  "previsao_chegada": "2026-11-18T17:00:00.000Z",
  "prazo_prometido": "2026-11-18",
  "progresso": 0.0,
  "posicao_lat": -12.5453,
  "posicao_lon": -55.7114,
  "posicao_em": "2026-11-10T12:05:00.300Z",
  "com_ocorrencia": false,
  "entregue_em": null,
  "no_prazo": null,
  "atraso_horas": null,
  "rota": [[-12.5453, -55.7114], [-12.738783, -55.552454], [-23.9608, -46.3336]],
  "atualizado_em": "2026-11-10T12:05:00.420Z",
  "preco_frete": 7113.3,
  "prazo_dias": 5,
  "produto_nome": "Soja em grão",
  "peso_kg": 24000.0,
  "tipo_carga": "GRANEL",
  "valor_carga": 192000.0,
  "comprador_id": "emp-comprador-1",
  "fornecedor_id": "emp-fornecedor-1",
  "origem_cidade": "Sorriso", "origem_uf": "MT", "origem_lat": -12.5453, "origem_lon": -55.7114,
  "destino_cidade": "Santos", "destino_uf": "SP", "destino_lat": -23.9608, "destino_lon": -46.3336,
  "distancia_km": 2091.1
}
```
- A rota real tem 60 pontos; o exemplo mostra 3.
- Antes do `VIAGEM_ALOCADA`: campos de motorista, veículo, coleta, posição e `rota` são `null`, `progresso` é 0 e `status` é `"AGUARDANDO_ALOCACAO"`.
- `preco_frete` e `prazo_dias` vêm da cotação da entrega.

#### API-10 — Rastreio

```json
{
  "entregaId": "e7a41c22-6b0d-4f3e-8a5c-1d9b2e7f4a63",
  "pedidoId": "PED-1001",
  "status": "AGUARDANDO_COLETA",
  "progresso": 0.0,
  "posicao": {"lat": -12.5453, "lon": -55.7114},
  "posicaoEm": "2026-11-10T12:05:00.300Z",
  "previsaoChegada": "2026-11-18T17:00:00.000Z",
  "origem": {"cidade": "Sorriso", "uf": "MT", "lat": -12.5453, "lon": -55.7114},
  "destino": {"cidade": "Santos", "uf": "SP", "lat": -23.9608, "lon": -46.3336},
  "rota": [[-12.5453, -55.7114], [-12.738783, -55.552454], [-23.9608, -46.3336]],
  "eventos": [
    {"sequencia": 1, "tipo": "VIAGEM_ALOCADA", "descricao": "Motorista Roberto Nunes e veículo PAS6J78 escalados.",
     "lat": -12.5453, "lon": -55.7114, "progresso": 0.0, "ocorrido_em": "2026-11-10T12:05:00.300Z"}
  ],
  "ocorrencias": [],
  "horaDoModulo": "2026-11-10T12:06:00.000Z"
}
```
- `posicao`, `posicaoEm` e `previsaoChegada` são `null` antes da primeira posição; `rota` é `[]` antes do `VIAGEM_ALOCADA`.
- `eventos`: os rastreios aplicados, por `sequencia` crescente.
- `ocorrencias`: as mesmas ocorrências da API-14, na mesma ordem; `[]` quando não houver.

#### API-11 — Entrega de um pedido

A entrega de maior `tentativa` do pedido, visível para o usuário, qualquer que seja o status. Mesmo corpo da API-09.

#### API-12 — Consultar o relógio

```json
{"horaDoModulo": "2026-11-10T12:00:00.000Z", "horaReal": "2026-11-10T12:00:00.000Z", "fator": 1.0, "versao": 0}
```
Sem ajuste gravado: `fator` 1.0, `versao` 0 e `horaDoModulo` = `horaReal`.

#### API-13 — Ajustar o relógio

Requisição: `{"fator": 3600, "avancarHoras": 0}`. `fator`: número > 0 e ≤ 100000, com no máximo 2 casas decimais. `avancarHoras`: número de 0 a 1440, padrão 0.

Resposta 200 (o novo estado; `horaDoModulo` é a nova `base_virtual` e `horaReal` a nova `base_real`):
```json
{"horaDoModulo": "2026-11-10T12:10:00.000Z", "horaReal": "2026-11-10T12:10:00.000Z", "fator": 3600.0, "versao": 1}
```

#### API-14 — Ocorrências da entrega

Todas as ocorrências da entrega (RN-33), por `ocorrida_em` crescente. Não é paginada.

```json
{
  "items": [
    {"id": "4f0430e0-6382-4f0c-8183-9ea5a0c942ef", "autor_papel": "comprador",
     "descricao": "Lona da carreta rasgada na foto da coleta.", "ocorrida_em": "2026-11-10T12:30:00.000Z"}
  ]
}
```
Sem ocorrências: `{"items": []}`.

#### API-15 — Reportar ocorrência

Requisição: `{"descricao": "  Lona da carreta rasgada na foto da coleta.  "}`. `descricao`: texto obrigatório; os espaços das pontas são retirados e o restante deve ter de 5 a 500 caracteres (RN-33).

Resposta 201: a ocorrência gravada, como um item da API-14 (com `descricao` sem os espaços das pontas). Efeitos na mesma transação: `com_ocorrencia` da entrega vira `true` e a outra parte recebe a notificação `OCORRENCIA` (RN-32).

#### API-16 — Documento da entrega em PDF

`tipo` ∈ {`cte`, `romaneio`, `nota-fiscal`, `comprovante-coleta`}. Resposta 200 com `Content-Type: application/pdf` e `Content-Disposition: inline; filename="<tipo>-<pedido_id>.pdf"` (por exemplo, `cte-PED-1001.pdf`). Conteúdo na RN-34.

#### API-17 — Notificações do usuário

Parâmetros: `lida` (opcional, booleano: `true` só lidas, `false` só não lidas), `page`, `size`. Só as notificações da empresa e do perfil do usuário (RN-32), por `criada_em` decrescente; empate pela ordem de gravação, a mais nova primeiro. `naoLidas` conta todas as não lidas do usuário, com ou sem filtro.

```json
{
  "items": [
    {
      "id": "02adbb1c-c545-43c5-8b71-4083d01e2cae",
      "tipo": "MOTORISTA_ESCALADO",
      "titulo": "Motorista escalado",
      "mensagem": "Roberto Nunes, com o veículo PAS6J78, fará a entrega do pedido PED-1001. Coleta prevista para 10/11/2026 11:05.",
      "pedido_id": "PED-1001",
      "solicitacao_id": "5c0e7b9a-3d2f-4e8a-9b1c-7f6a2d4e8c10",
      "lida": false,
      "criada_em": "2026-11-10T12:05:00.300Z"
    },
    {
      "id": "21efc7fe-8db0-4e7d-b6c5-4889d1908d61",
      "tipo": "FRETE_ESCOLHIDO",
      "titulo": "Frete escolhido",
      "mensagem": "O frete do pedido PED-1001 foi escolhido pelo comprador: Graneleira Centro-Oeste, R$ 7.113,30, 5 dias úteis.",
      "pedido_id": "PED-1001",
      "solicitacao_id": "5c0e7b9a-3d2f-4e8a-9b1c-7f6a2d4e8c10",
      "lida": false,
      "criada_em": "2026-11-10T12:05:00.000Z"
    }
  ],
  "page": 1, "size": 10, "total": 2, "naoLidas": 2
}
```
(Exemplo: U-FORN depois de E-1 com o `VIAGEM_ALOCADA`.)

#### API-18 — Marcar notificação

Requisição: `{"lida": true}` ou `{"lida": false}`. `lida` é booleano e opcional (padrão `true`; o corpo `{}` marca como lida). Resposta 200: a notificação, como um item da API-17, com o novo `lida`. Marcar de novo com o mesmo valor também responde 200. Notificação de outra empresa ou de outro perfil → 404 `NOTIFICACAO_NAO_ENCONTRADA`.

### 7.3 Eventos consumidos

Envelope de toda mensagem consumida: objeto JSON com `eventId`, `eventType`, `timestamp`, `source`, `aggregateId` e `payload` (objeto) obrigatórios; `eventVersion` e `correlationId` opcionais. O tratador é escolhido pelo **tópico**; `eventType` não é conferido. O `payload` é validado pelo JSON Schema do tópico (`comum/comum/contratos/<tópico>.schema.json`, draft 2020-12; campos extras são aceitos; `format` de data não é conferido pelo schema).

| Tópico | Produtor | Chave | Ação | Em caso de mensagem inválida |
|---|---|---|---|---|
| `pedido_criado` | Pedidos | `pedidoId` | RF-01 | DLT `logistica.dlt` (RN-30) |
| `cotacao_recebida` | `transportadoras-service` | `solicitacaoFreteId` | RF-02 | DLT |
| `pedido_atualizado` | Pedidos | `pedidoId` | RF-10 | DLT |
| `rastreio_atualizado` | `transportadoras-service` | `pedidoId` | RF-11, RF-12 | DLT |

Campos do `payload`:

| Tópico | Obrigatórios | Opcionais |
|---|---|---|
| `pedido_criado` | `pedidoId`, `compradorId`, `fornecedorId`, `produtoId`, `produtoNome` (strings não vazias); `quantidade` (> 0); `unidade` (`KG`, `TON`, `UN`, `CX`, `L`); `pesoKg` (> 0); `tipoTransporte` (`GRANEL`, `REFRIGERADO`, `CARGA_SECA`, `PERIGOSO`); `valorTotal` (≥ 0); `origem` e `destino` (`{"cidade": string não vazia, "uf": "^[A-Z]{2}$"}`) | `negociacaoId`, `fornecimentoId` (não usado), `dataEntregaDesejada` (data), `status` |
| `cotacao_recebida` | `cotacaoId`, `solicitacaoFreteId`, `transportadoraId` (strings não vazias); `preco` (> 0); `prazoDias` (inteiro ≥ 1) | `transportadoraNome`, `dataEntregaPrevista`, `validaAte`, `origemCotacao` (`SIMULADA`, `DIGITADA`), `observacoes` (até 500 caracteres ou `null`) |
| `pedido_atualizado` | `pedidoId`; e `novoStatus` ou `status` (string não vazia) | `statusAnterior` |
| `rastreio_atualizado` | `pedidoId`, `entregaId`, `transportadoraId`, `sequencia` (inteiro ≥ 1), `tipo`, `descricao`, `ocorridoEm` | Conforme o `tipo` (tabela abaixo) |

Campos de `rastreio_atualizado` obrigatórios por `tipo`:

| `tipo` | Obrigatórios além dos comuns |
|---|---|
| `VIAGEM_ALOCADA` | `motorista` (`nome`; opcionais `telefone`, `cnhMascarada`), `veiculo` (`placa`, `tipo`), `rota` (lista de `[lat, lon]`), `coletaPrevista`, `previsaoChegada`, `posicao` (`{"lat", "lon"}`). Opcional `transportadora` (`nome`, `telefone`) |
| `VIAGEM_RECUSADA` | `motivo` (`SEM_MOTORISTA`, `SEM_VEICULO`) |
| `COLETA_REALIZADA` | — (opcionais `posicao`, `previsaoChegada`) |
| `POSICAO`, `PARADA`, `PREVISAO_ATUALIZADA` | `posicao`, `progresso` (0 a 1), `previsaoChegada`. Opcionais: `local` e `duracaoPrevistaMin` (PARADA); `previsaoAnterior` (PREVISAO_ATUALIZADA) |
| `OCORRENCIA` | — |
| `ENTREGA_REALIZADA` | `noPrazo` (booleano), `atrasoHoras` (≥ 0), `posicao` |

Exemplo de mensagem recebida (`pedido_criado`, pedido P-1 do §8.0):
```json
{
  "eventId": "0b6a1c1e-8d0f-4a37-9f5e-1f2b3c4d5e6f",
  "eventType": "pedido_criado",
  "eventVersion": "1.0",
  "timestamp": "2026-11-10T11:59:59.800Z",
  "source": "pedidos-service",
  "correlationId": "3e46ad25-60ba-46b7-abe1-250ad2717009",
  "aggregateId": "PED-1001",
  "payload": {
    "pedidoId": "PED-1001",
    "negociacaoId": "NEG-501",
    "compradorId": "emp-comprador-1",
    "fornecedorId": "emp-fornecedor-1",
    "produtoId": "prod-soja",
    "fornecimentoId": "FORN-77",
    "produtoNome": "Soja em grão",
    "quantidade": 24000,
    "unidade": "KG",
    "pesoKg": 24000,
    "tipoTransporte": "GRANEL",
    "valorTotal": 192000.0,
    "origem": {"cidade": "Sorriso", "uf": "MT"},
    "destino": {"cidade": "Santos", "uf": "SP"},
    "dataEntregaDesejada": "2026-11-30",
    "status": "CRIADO"
  }
}
```

Os exemplos de `cotacao_recebida` e `rastreio_atualizado` estão na ESP-TRP-001 (§7.4), que é a fonte da verdade desses tópicos.

### 7.4 Eventos publicados

Envelope comum:

| Campo | Valor |
|---|---|
| `eventId` | UUID4 novo, único por evento |
| `eventType` | Igual ao nome do tópico |
| `eventVersion` | `"1.0"` (string) |
| `timestamp` | Hora **real** da gravação na outbox (instante) |
| `source` | `"logistica-service"` |
| `correlationId` | O do evento ou da requisição que originou a gravação; se não houver, UUID4 novo |
| `aggregateId` | A chave de partição da tabela abaixo |
| `payload` | Objeto do tópico, validado pelo JSON Schema antes da gravação |

| Tópico | Quando | Chave de partição (`aggregateId`) | Payload |
|---|---|---|---|
| `solicitacao_frete_criada` | Solicitação aberta (RF-01) | `solicitacaoFreteId` | `solicitacaoFreteId`, `pedidoId`, `produtoId`, `produtoNome`, `compradorId`, `fornecedorId`, `tipoCarga`, `pesoKg`, `origem` e `destino` (`cidade`, `uf`, `lat`, `lon`), `distanciaKm`, `dataColetaPrevista`, `prazoDecisaoEm`, `status` (`"ABERTA"`) |
| `frete_selecionado` | Escolha (RF-06, RF-07, RF-08) ou troca de transportadora (RF-12) | `pedidoId` | `pedidoId`, `solicitacaoFreteId`, `entregaId`, `tentativa`, `cotacaoId`, `transportadoraId`, `preco`, `prazoDias`, `dataEntregaPrevista` (data ou `null`), `criterio`, `status` (`"FRETE_SELECIONADO"`) |
| `frete_indisponivel` | Sem cotação no prazo (RF-04) ou sem transportadora com frota (RF-12) | `pedidoId` | `pedidoId`, `solicitacaoFreteId`, `motivo` (`"SEM_COTACAO"` ou `"SEM_TRANSPORTADORA_DISPONIVEL"`), `detalhe`, `ocorridoEm` (hora do módulo) |
| `entrega_concluida` | Rastreio `ENTREGA_REALIZADA` aplicado (RF-11) | `pedidoId` | `pedidoId`, `entregaId`, `transportadoraId`, `entregueEm` (`ocorridoEm` do rastreio), `prazoPrometido` (data ou `null`), `noPrazo`, `atrasoHoras` |
| `relogio_ajustado` | Ajuste do relógio (RF-14) | `"relogio"` | `versao`, `baseReal`, `baseVirtual`, `fator`, `ajustadoPor` (`sub` do admin) |
| `logistica.dlt` | Mensagem consumida que não pôde ser processada (RN-30) | `aggregateId` da mensagem original; `"desconhecido"` se ela não era JSON ou tinha o envelope incompleto | `originalEvent` (o envelope recebido; o texto bruto se a mensagem não era JSON ou tinha o envelope incompleto), `error` (texto), `stackTrace` (texto), `failedAtAttempt` (inteiro), `originalTopic` |

Exemplo `solicitacao_frete_criada` (P-1):
```json
{
  "eventId": "9d60e831-b932-4645-b724-a2dd682c8482",
  "eventType": "solicitacao_frete_criada",
  "eventVersion": "1.0",
  "timestamp": "2026-11-10T12:00:00.050Z",
  "source": "logistica-service",
  "correlationId": "3e46ad25-60ba-46b7-abe1-250ad2717009",
  "aggregateId": "5c0e7b9a-3d2f-4e8a-9b1c-7f6a2d4e8c10",
  "payload": {
    "solicitacaoFreteId": "5c0e7b9a-3d2f-4e8a-9b1c-7f6a2d4e8c10",
    "pedidoId": "PED-1001",
    "produtoId": "prod-soja",
    "produtoNome": "Soja em grão",
    "compradorId": "emp-comprador-1",
    "fornecedorId": "emp-fornecedor-1",
    "tipoCarga": "GRANEL",
    "pesoKg": 24000.0,
    "origem": {"cidade": "Sorriso", "uf": "MT", "lat": -12.5453, "lon": -55.7114},
    "destino": {"cidade": "Santos", "uf": "SP", "lat": -23.9608, "lon": -46.3336},
    "distanciaKm": 2091.1,
    "dataColetaPrevista": "2026-11-11",
    "prazoDecisaoEm": "2026-11-11T00:00:00.000Z",
    "status": "ABERTA"
  }
}
```

Exemplo `frete_selecionado`: o corpo da resposta da API-06 sem `transportadoraNome`, com `aggregateId` `"PED-1001"`.

Exemplo `frete_indisponivel`:
```json
{"pedidoId": "PED-1002", "solicitacaoFreteId": "9d3e5a71-2b4c-4f8d-a6e0-4c7b1f2d8e35", "motivo": "SEM_COTACAO",
 "detalhe": "Nenhuma transportadora cotou dentro do prazo de decisão", "ocorridoEm": "2026-11-11T00:00:00.512Z"}
```
O `detalhe` é `"Nenhuma transportadora cotou dentro do prazo de decisão"` para `SEM_COTACAO` e `"Nenhuma transportadora que cotou tem frota livre"` para `SEM_TRANSPORTADORA_DISPONIVEL`.

Exemplo `entrega_concluida`:
```json
{"pedidoId": "PED-1002", "entregaId": "b52c9e10-7a3d-4f61-9e2b-6c8d0a4f1e93", "transportadoraId": "transp-teste-a",
 "entregueEm": "2026-11-20T21:36:00.000Z", "prazoPrometido": "2026-11-19", "noPrazo": false, "atrasoHoras": 15.6}
```

Exemplo `relogio_ajustado`:
```json
{"versao": 1, "baseReal": "2026-11-10T12:10:00.000Z", "baseVirtual": "2026-11-10T12:10:00.000Z", "fator": 3600.0, "ajustadoPor": "usr-admin"}
```

Exemplo `logistica.dlt` (cidade fora da tabela):
```json
{
  "eventType": "logistica.dlt",
  "source": "logistica-service",
  "aggregateId": "PED-1009",
  "payload": {
    "originalEvent": {"eventId": "...", "eventType": "pedido_criado", "aggregateId": "PED-1009", "payload": {"...": "..."}},
    "error": "Cidade de origem desconhecida: {'cidade': 'Atlântida', 'uf': 'MT'}",
    "stackTrace": "Traceback (most recent call last): ...",
    "failedAtAttempt": 1,
    "originalTopic": "pedido_criado"
  }
}
```

## 8. Requisitos funcionais

### 8.0 Cenário base dos critérios de aceitação

Todos os CAs partem deste cenário e dizem só o que muda. Os CAs são verificados como caixa-preta no ambiente do `docker-compose.yml`: requisições pelo gateway (`http://localhost:8088`), eventos publicados e lidos no Kafka (`localhost:29092`) e, só para conferir, consultas ao banco (Q-01).

**S0 — ambiente.** Recém-criado (`docker compose down -v` e `docker compose up -d --build`), com os seeds 900 a 902 do `transportadoras-service`: transportadoras simuladas `transp-expressa`, `transp-economica`, `transp-graneleira`, `transp-frio` e `transp-perigosos`, e a transportadora não simulada `transp-rodovia`. Sem nenhuma entrega concluída (desempenho vazio). Relógio sem ajuste (fator 1).

**T0 — hora de referência.** O pedido P-1 é consumido com a hora do módulo em `2026-11-10T12:00:00.000Z` (terça-feira). O relógio só anda para a frente (Q-02): num ambiente com outra hora, confira as mesmas relações a partir do `aberta_em` devolvido.

**Usuários** (tokens RS256 do §7.1):

| Nome | `sub` | `tenant_id` | `active_scope` | `permissions` | Perfil |
|---|---|---|---|---|---|
| U-COMP | `usr-comprador-1` | `emp-comprador-1` | `BUYER` | `[]` | comprador |
| U-COMP2 | `usr-comprador-2` | `emp-comprador-2` | `BUYER` | `[]` | comprador |
| U-FORN | `usr-fornecedor-1` | `emp-fornecedor-1` | `SUPPLIER` | `[]` | fornecedor |
| U-TRANSP | `usr-transp-rodovia` | `emp-transp-rodovia` | `CARRIER` | `[]` | transportadora |
| U-ADM | `usr-admin` | `emp-portal` | `TENANT_ADMIN` | `[]` | admin (`platform_role` `PLATFORM_ADMIN`) |
| U-TADM | `usr-gestor-1` | `emp-comprador-1` | `TENANT_ADMIN` | `[]` | (sem acesso) |

Todos os tokens têm `iss` `"identity-service"`, `aud` `"b2b-platform"` e `view_mode` `"SINGLE"`; `platform_role` é `"NONE"`, exceto em U-ADM.

**Pedidos de referência** (publicados em `pedido_criado`, envelope como no §7.3):

| Nome | `pedidoId` | Carga | Rota | Resultado esperado |
|---|---|---|---|---|
| P-1 | `PED-1001` | `GRANEL`, 24000 kg, "Soja em grão", `valorTotal` 192000.0, `dataEntregaDesejada` `"2026-11-30"` | Sorriso/MT → Santos/SP | S-1 com 3 cotações automáticas |
| P-2 | `PED-1002` | `REFRIGERADO`, 30000 kg, "Carne congelada", `valorTotal` 450000.0 | Sorriso/MT → Santos/SP | S-2 sem cotação automática: a única transportadora refrigerada não tem veículo para 30 t |

Os demais campos de P-2 são iguais aos de P-1. Pedidos extras usam o mesmo formato, com `pedidoId` `PED-1003` em diante.

**S-1** (solicitação de P-1): `distancia_km` 2091.1, `data_coleta_prevista` `"2026-11-11"`, `prazo_decisao_em` `"2026-11-11T00:00:00.000Z"`. Cotações publicadas pelo `transportadoras-service`:

| Nome | `transportadora_id` | `preco` | `prazo_dias` | `data_entrega_prevista` | `preco_t_km` |
|---|---|---|---|---|---|
| C-ECO | `transp-economica` | 6156.86 | 8 | `2026-11-23` | 0.1227 |
| C-GRA | `transp-graneleira` | 7113.3 | 5 | `2026-11-18` | 0.1417 |
| C-EXP | `transp-expressa` | 9026.18 | 4 | `2026-11-17` | 0.1799 |

**Cotações de teste** (publicadas pelo QA em `cotacao_recebida`, com `cotacaoId` UUID novo, `transportadoraNome` `"Teste A"`, `"Teste B"` ou `"Teste C"` e `origemCotacao` `"DIGITADA"`). As transportadoras `transp-teste-*` não existem no `transportadoras-service`, então nenhuma viagem é simulada para elas: o QA publica o rastreio.

| Nome | `transportadora_id` | `preco` | `prazoDias` | `dataEntregaPrevista` |
|---|---|---|---|---|
| Q-A | `transp-teste-a` | 5000.00 | 6 | `2026-11-19` |
| Q-B | `transp-teste-b` | 5000.00 | 5 | `2026-11-18` |
| Q-C | `transp-teste-c` | 4800.00 | 9 | `2026-11-24` |

**E-1**: entrega criada quando U-COMP escolhe C-GRA em S-1. **E-2**: entrega criada quando U-COMP escolhe Q-A em S-2 (depois de Q-A, Q-B e Q-C publicadas para S-2).

O desempenho das transportadoras acumula e só zera com `docker compose down -v`. Por isso, num ambiente reaproveitado, cada CA que depende do desempenho (CA-35, CA-40, CA-48) usa transportadoras de teste com ids novos (por exemplo, `transp-teste-a-35`), no lugar de `transp-teste-a` e `transp-teste-b`.

### RF-01 — Abrir a solicitação de frete

- **Prioridade:** Must
- **Enunciado (EARS):** Quando uma mensagem válida de `pedido_criado` for recebida para um `pedidoId` sem solicitação e sem cancelamento registrado, o serviço deve criar a solicitação com status `ABERTA` e publicar `solicitacao_frete_criada`.
- **Regras aplicáveis:** RN-01 a RN-06, RN-30
- **Interface:** tópico `pedido_criado`, tópico `solicitacao_frete_criada`, `logistica.dlt`

```gherkin
# CA-01
Cenário: Pedido válido abre a solicitação
  Dado o cenário S0 e a hora do módulo T0
  Quando P-1 é publicado em pedido_criado
  Então em até 5 s GET /api/v1/logistica/solicitacoes/{id de S-1} por U-COMP retorna 200 com pedido_id "PED-1001", tipo_carga "GRANEL", peso_kg 24000.0, valor_carga 192000.0, origem_cidade "Sorriso", origem_lat -12.5453, origem_lon -55.7114, destino_cidade "Santos", destino_lat -23.9608, destino_lon -46.3336, distancia_km 2091.1, data_coleta_prevista "2026-11-11", aberta_em "2026-11-10T12:00:00.000Z", prazo_decisao_em "2026-11-11T00:00:00.000Z", data_entrega_desejada "2026-11-30" e cotacao_escolhida_id null
  E o status é "ABERTA" ou "COTADA" (as cotações automáticas chegam em menos de 1 s)
  E há exatamente uma mensagem em "solicitacao_frete_criada" com chave igual ao id de S-1, source "logistica-service", eventVersion "1.0", correlationId igual ao do pedido_criado e payload igual ao exemplo do §7.4

# CA-02
Cenário: A mesma mensagem duas vezes tem efeito uma vez só
  Quando o mesmo envelope de P-1 (mesmo eventId) é publicado 2 vezes
  Então existe 1 solicitação com pedido_id "PED-1001"
  E há exatamente 1 mensagem em "solicitacao_frete_criada" para ela e nenhuma em "logistica.dlt"

# CA-03
Cenário: Outro evento para o mesmo pedido é ignorado
  Dado S-1 aberta
  Quando um pedido_criado com outro eventId, pedidoId "PED-1001" e pesoKg 99999 é publicado
  Então S-1 continua com peso_kg 24000.0, não há segunda solicitação, nem segunda mensagem em "solicitacao_frete_criada", nem mensagem em "logistica.dlt"

# CA-04
Cenário: Cidade fora da tabela vai para a DLT
  Quando P-1 é publicado com pedidoId "PED-1009" e origem {"cidade": "Atlântida", "uf": "MT"}
  Então nenhuma solicitação com pedido_id "PED-1009" existe
  E em até 5 s há uma mensagem em "logistica.dlt" com chave "PED-1009" e payload com originalTopic "pedido_criado", failedAtAttempt 1, error "Cidade de origem desconhecida: {'cidade': 'Atlântida', 'uf': 'MT'}" e originalEvent igual ao envelope publicado
  Quando a origem é válida e o destino é {"cidade": "Gotham", "uf": "SP"}
  Então o error começa com "Cidade de destino desconhecida:"

# CA-05
Cenário: Payload fora do contrato vai para a DLT
  Quando P-1 é publicado com pedidoId "PED-1010" e qualquer uma destas mudanças: pesoKg 0; tipoTransporte "VIVO"; origem {"cidade": "Sorriso", "uf": "mt"}; sem o campo destino; pedidoId 1010 (número)
  Então nenhuma solicitação é criada para o pedido
  E há uma mensagem em "logistica.dlt" com failedAtAttempt 1 e error começando com "Payload de pedido_criado fora do contrato:"

# CA-06
Cenário: Nome da cidade sem acento e em maiúsculas
  Quando P-1 é publicado com pedidoId "PED-1011", origem {"cidade": "SORRISO", "uf": "MT"} e destino {"cidade": "  sao   paulo ", "uf": "SP"}
  Então a solicitação tem origem_cidade "Sorriso" e destino_cidade "São Paulo"

# CA-07
Cenário: Data de coleta no próximo dia útil (data UTC)
  Quando P-1 é consumido com a hora do módulo "2026-11-13T12:00:00.000Z" (sexta-feira)
  Então data_coleta_prevista é "2026-11-16" e prazo_decisao_em é "2026-11-14T00:00:00.000Z"
  Quando P-1 é consumido com a hora do módulo "2026-11-11T01:30:00.000Z" (terça 22:30 em Brasília, quarta em UTC)
  Então data_coleta_prevista é "2026-11-12"

# CA-08
Cenário: Cancelamento que chega antes do pedido
  Dado que pedido_atualizado {"pedidoId": "PED-1003", "status": "CANCELADO"} foi consumido
  Quando P-1 é publicado com pedidoId "PED-1003"
  Então nenhuma solicitação com pedido_id "PED-1003" existe
  E não há mensagem para "PED-1003" em "solicitacao_frete_criada" nem em "logistica.dlt"
```

### RF-02 — Registrar a cotação

- **Prioridade:** Must
- **Enunciado (EARS):** Quando uma mensagem válida de `cotacao_recebida` for recebida para uma solicitação existente, o serviço deve guardar a cotação e, se for a primeira válida, mudar a solicitação para `COTADA`.
- **Regras aplicáveis:** RN-07, RN-08, RN-09
- **Interface:** tópico `cotacao_recebida`, API-05

```gherkin
# CA-09
Cenário: Cotações automáticas deixam a solicitação COTADA
  Dado S-1 aberta
  Quando as 3 cotações de S-1 são consumidas
  Então GET da API-05 retorna status "COTADA" e cotacoes na ordem C-ECO, C-GRA, C-EXP, com os valores da tabela do §8.0, status "VALIDA", origem_cotacao "SIMULADA" e valida_ate "2026-11-11T00:00:00.000Z"

# CA-10
Cenário: Segunda cotação da mesma transportadora é ignorada
  Dado S-1 com C-ECO
  Quando uma cotacao_recebida com outro eventId e outro cotacaoId, solicitacaoFreteId de S-1, transportadoraId "transp-economica" e preco 1.00 é publicada
  Então S-1 continua com uma cotação de "transp-economica", com preco 6156.86
  E não há mensagem em "logistica.dlt"

# CA-11
Cenário: Cotação de solicitação desconhecida vai para a DLT
  Quando uma cotacao_recebida com solicitacaoFreteId "nao-existe" é publicada
  Então há uma mensagem em "logistica.dlt" com failedAtAttempt 1 e error "Solicitação desconhecida: nao-existe"

# CA-12
Cenário: Cotação que chega depois da escolha é guardada como tardia
  Dado S-1 SELECIONADA (CA-21)
  Quando Q-A é publicada para S-1
  Então a API-05 mostra a cotação de "transp-teste-a" com status "RECUSADA_TARDE"
  E S-1 continua SELECIONADA com cotacao_escolhida_id de C-GRA

# CA-13
Cenário: Cotação durante SEM_COTACAO reabre a escolha
  Dado S-2 com status "SEM_COTACAO" (CA-14)
  Quando Q-A é publicada para S-2
  Então a cotação de "transp-teste-a" tem status "VALIDA" e S-2 passa a "COTADA"
```

### RF-03 — Encerrar a rodada automática sem cotação

- **Prioridade:** Must
- **Enunciado (EARS):** Enquanto uma solicitação estiver `ABERTA` sem cotação, quando passarem 10 s de hora real desde a abertura, o serviço deve mudar o status para `SEM_COTACAO`.
- **Regras aplicáveis:** RN-10
- **Interface:** rotina de prazos, API-05

```gherkin
# CA-14
Cenário: Rodada de 10 s sem resposta
  Quando P-2 é publicado
  Então 5 s depois do consumo S-2 tem status "ABERTA"
  E entre 10 s e 12 s depois do consumo S-2 tem status "SEM_COTACAO"
  E nenhuma mensagem para "PED-1002" é publicada em "frete_selecionado" nem em "frete_indisponivel"
```

### RF-04 — Declarar o frete indisponível sem cotação

- **Prioridade:** Must
- **Enunciado (EARS):** Quando a hora do módulo alcançar o `prazo_decisao_em` de uma solicitação `SEM_COTACAO`, o serviço deve mudá-la para `INDISPONIVEL` e publicar `frete_indisponivel` com motivo `SEM_COTACAO`.
- **Regras aplicáveis:** RN-11
- **Interface:** rotina de prazos, tópico `frete_indisponivel`

```gherkin
# CA-15
Cenário: Prazo de 12 h vence sem cotação
  Dado S-2 com status "SEM_COTACAO"
  Quando U-ADM envia POST /api/v1/logistica/admin/relogio {"fator": 1, "avancarHoras": 12}
  Então em até 3 s S-2 tem status "INDISPONIVEL"
  E há exatamente uma mensagem em "frete_indisponivel" com chave "PED-1002" e payload pedidoId "PED-1002", solicitacaoFreteId igual ao id de S-2, motivo "SEM_COTACAO", detalhe "Nenhuma transportadora cotou dentro do prazo de decisão" e ocorridoEm ≥ prazo_decisao_em de S-2
  Quando U-COMP envia a API-06 para S-2 com {"modo": "AUTOMATICO"}
  Então a resposta é 409 com codigo "SOLICITACAO_ENCERRADA"
```

### RF-05 — Consultar solicitações

- **Prioridade:** Must
- **Enunciado (EARS):** Quando um usuário autenticado com perfil comprador, fornecedor ou admin consultar a API-04 ou a API-05, o serviço deve devolver só as solicitações visíveis para ele.
- **Regras aplicáveis:** RN-19, RN-28
- **Interface:** API-04, API-05

```gherkin
# CA-16
Cenário: Cada perfil vê as suas solicitações
  Dado S-1 e S-2 abertas
  Quando U-COMP, U-FORN e U-ADM consultam GET /api/v1/logistica/solicitacoes
  Então as três respostas são 200 e contêm S-1 e S-2, com total 2, page 1 e size 10, S-2 antes de S-1
  Quando U-COMP2 consulta
  Então a resposta é 200 com items [] e total 0

# CA-17
Cenário: Detalhe visível e não visível
  Quando U-COMP consulta a API-05 de S-1
  Então a resposta é 200 com todos os campos do exemplo da API-05
  Quando U-COMP2 consulta a API-05 de S-1, ou U-COMP consulta a API-05 de "nao-existe"
  Então a resposta é 404 com codigo "SOLICITACAO_NAO_ENCONTRADA"

# CA-18
Cenário: Filtros e paginação
  Quando U-COMP consulta com status=SEM_COTACAO
  Então items contém só S-2
  Quando U-COMP consulta com size=1
  Então items tem 1 item, size 1 e total 2
  Quando U-COMP consulta com qualquer um de: size=101, size=0, page=0, status=XYZ
  Então a resposta é 422 com codigo "DADOS_INVALIDOS" e erros[0].campo igual a "query.size", "query.size", "query.page" ou "query.status", respectivamente

# CA-19
Cenário: Autenticação e perfil
  Quando a API-04 é chamada sem Authorization
  Então a resposta é 401 com codigo "NAO_AUTENTICADO"
  Quando é chamada com "Authorization: Bearer abc.def.ghi"
  Então a resposta é 401 com codigo "TOKEN_INVALIDO"
  Quando U-TRANSP chama a API-04
  Então a resposta é 403 com codigo "PERFIL_NAO_PERMITIDO"
  Quando U-TADM chama a API-04
  Então a resposta é 403 com codigo "PERFIL_NAO_PERMITIDO"
  Quando a API-04 é chamada com size=101 e sem Authorization
  Então a resposta é 401 com codigo "NAO_AUTENTICADO" (autenticação antes da validação)

# CA-20
Cenário: Casos do token (verificados também por teste unitário)
  Quando o token RS256 tem assinatura válida e exp no passado
  Então a resposta é 401 com codigo "TOKEN_EXPIRADO"
  Quando o token não tem tenant_id
  Então a resposta é 401 com codigo "TOKEN_INVALIDO"
  Quando o token tem active_scope "GUEST" e permissions []
  Então a resposta é 403 com codigo "PERFIL_AUSENTE"
  Quando o token tem um kid que não está no JWKS e o JWKS responde
  Então a resposta é 401 com codigo "TOKEN_INVALIDO"
  Quando o JWKS está inacessível e o kid do token não está em cache
  Então a resposta é 503 com codigo "AUTENTICACAO_INDISPONIVEL"
  Quando o token foi assinado com HS256 e JWT_ALGORITHM é RS256
  Então a resposta é 401 com codigo "TOKEN_INVALIDO"
  Quando o token tem aud "outro-sistema", ou não tem aud, ou tem iss "servico-falso"
  Então a resposta é 401 com codigo "TOKEN_INVALIDO"
  Quando o token é o do login (view_mode "NONE", sem tenant_id nem active_scope) ou de grupo (view_mode "MACRO_GROUP", sem tenant_id)
  Então a resposta é 403 com codigo "CONTEXTO_NAO_SELECIONADO"
  Quando o token tem platform_role "PLATFORM_ADMIN" e view_mode "NONE"
  Então o usuário é admin (a API-12 e a API-13 respondem 200)
  Quando o token tem platform_role "SUPPORT_AGENT" e active_scope "TENANT_ADMIN"
  Então a resposta é 403 com codigo "PERFIL_NAO_PERMITIDO"

# CA-73
Cenário: Solicitação pelo pedido
  Dado S-1 e S-2
  Quando U-COMP consulta a API-04 com pedido_id=PED-1001
  Então a resposta é 200 com total 1 e o único item com id igual ao de S-1
  Quando U-COMP consulta com pedido_id=PED-1001&status=SELECIONADA (S-1 ainda COTADA)
  Então items é [] e total é 0
  Quando U-COMP2 consulta com pedido_id=PED-1001, ou U-COMP consulta com pedido_id=PED-9999
  Então items é [] e total é 0
  Quando U-COMP consulta com pedido_id= (vazio) ou com 65 caracteres
  Então a resposta é 422 com codigo "DADOS_INVALIDOS" e erros[0].campo "query.pedido_id"
```

### RF-06 — Escolha do frete pelo comprador

- **Prioridade:** Must
- **Enunciado (EARS):** Quando o comprador dono da solicitação (ou um admin) enviar a API-06 com `cotacaoId` de uma cotação válida, com a solicitação `COTADA` e `agora ≤ prazo_decisao_em`, o serviço deve registrar a escolha, criar a entrega, publicar `frete_selecionado` e responder 200.
- **Regras aplicáveis:** RN-12, RN-14 a RN-17, RN-31
- **Interface:** API-06, tópico `frete_selecionado`

```gherkin
# CA-21
Cenário: O comprador escolhe uma cotação que não é a mais barata
  Dado S-1 COTADA com C-ECO, C-GRA e C-EXP
  Quando U-COMP envia a API-06 para S-1 com {"cotacaoId": <id de C-GRA>} e Idempotency-Key "k-1001"
  Então a resposta é 200 com pedidoId "PED-1001", solicitacaoFreteId de S-1, entregaId UUID, tentativa 1, cotacaoId de C-GRA, transportadoraId "transp-graneleira", preco 7113.3, prazoDias 5, dataEntregaPrevista "2026-11-18", criterio "ESCOLHA_COMPRADOR", status "FRETE_SELECIONADO" e transportadoraNome "Graneleira Centro-Oeste"
  E a API-05 de S-1 retorna status "SELECIONADA", cotacao_escolhida_id de C-GRA, criterio "ESCOLHA_COMPRADOR", escolhida_por "usr-comprador-1" e escolhida_em igual à hora do módulo da escolha
  E a API-09 da entrega retorna status "AGUARDANDO_ALOCACAO", tentativa 1, cotacao_id de C-GRA, transportadora_id "transp-graneleira" e prazo_prometido "2026-11-18"

# CA-22
Cenário: A escolha publica frete_selecionado
  Quando a escolha do CA-21 é feita
  Então há exatamente uma mensagem em "frete_selecionado" com chave "PED-1001", correlationId igual ao do pedido_criado de P-1 e payload igual ao corpo da resposta sem transportadoraNome

# CA-23
Cenário: Reenvio com a mesma chave
  Dado a escolha do CA-21 feita com Idempotency-Key "k-1001"
  Quando U-COMP reenvia a API-06 para S-1 com Idempotency-Key "k-1001" e corpo {"cotacaoId": <id de C-EXP>}
  Então a resposta é 200, com cabeçalho X-Idempotent-Replay "true" e corpo com os mesmos campos e valores da primeira resposta (C-GRA)
  E continua havendo exatamente uma mensagem em "frete_selecionado" para "PED-1001" e uma entrega para S-1

# CA-24
Cenário: A chave é por usuário
  Dado a escolha do CA-21 feita com Idempotency-Key "k-1001"
  Quando U-ADM envia a API-06 para S-1 com Idempotency-Key "k-1001" e {"modo": "AUTOMATICO"}
  Então a resposta é 409 com codigo "FRETE_JA_ESCOLHIDO"

# CA-25
Cenário: Segunda escolha
  Dado S-1 SELECIONADA
  Quando U-COMP envia a API-06 com Idempotency-Key "k-1002" e {"cotacaoId": <id de C-ECO>}
  Então a resposta é 409 com codigo "FRETE_JA_ESCOLHIDO"
  E S-1 continua com cotacao_escolhida_id de C-GRA

# CA-26
Cenário: Idempotency-Key ausente ou inválido
  Quando U-COMP envia a API-06 para S-1 COTADA com {"modo": "AUTOMATICO"} e sem Idempotency-Key, ou com Idempotency-Key "   "
  Então a resposta é 400 com codigo "IDEMPOTENCY_KEY_AUSENTE"
  Quando envia com Idempotency-Key de 101 caracteres
  Então a resposta é 422 com codigo "DADOS_INVALIDOS" e erros[0].campo "header.Idempotency-Key"

# CA-27
Cenário: Corpo inválido
  Quando U-COMP envia a API-06 com Idempotency-Key novo e qualquer corpo entre: {}; {"cotacaoId": "x", "modo": "AUTOMATICO"}; {"modo": "MANUAL"}; []; texto "{xx" com Content-Type application/json
  Então a resposta é 422 com codigo "DADOS_INVALIDOS"

# CA-28
Cenário: Quem pode escolher
  Quando U-COMP2 envia a API-06 para S-1, ou U-COMP envia para "nao-existe"
  Então a resposta é 404 com codigo "SOLICITACAO_NAO_ENCONTRADA"
  Quando U-FORN, U-TRANSP ou U-TADM envia a API-06 para S-1
  Então a resposta é 403 com codigo "PERFIL_NAO_PERMITIDO"
  Quando a API-06 é enviada sem Authorization e com corpo válido
  Então a resposta é 401 com codigo "NAO_AUTENTICADO"

# CA-29
Cenário: Cotação que não é válida desta solicitação
  Dado S-1 COTADA
  Quando U-COMP envia {"cotacaoId": "nao-existe"} ou o cotacaoId de uma cotação de S-2
  Então a resposta é 404 com codigo "COTACAO_NAO_ENCONTRADA"

# CA-30
Cenário: Status que não permite escolha
  Quando U-COMP envia a API-06 para S-2 com status "ABERTA" ou "SEM_COTACAO"
  Então a resposta é 409 com codigo "SEM_COTACAO_PARA_ESCOLHER"
  Quando envia para uma solicitação "CANCELADA" (CA-41) ou "INDISPONIVEL" (CA-15)
  Então a resposta é 409 com codigo "SOLICITACAO_ENCERRADA"

# CA-31
Cenário: Prazo de escolha vencido
  Dado S-1 COTADA
  Quando U-ADM avança o relógio 12 h e U-COMP, logo em seguida, envia {"cotacaoId": <id de C-GRA>}
  Então a resposta é 409 com codigo "PRAZO_DE_ESCOLHA_ENCERRADO", ou "FRETE_JA_ESCOLHIDO" se a rotina de prazos já aplicou a regra automática (Q-07)
  E em até 3 s S-1 está SELECIONADA com cotacao_escolhida_id de C-ECO e criterio "AUTOMATICO_MENOR_PRECO"

# CA-32
Cenário: Precedência de erros
  Quando o corpo é o texto "{xx" e não há Authorization
  Então a resposta é 422 "DADOS_INVALIDOS" (o JSON ilegível vem antes da autenticação)
  Quando U-FORN envia corpo {}
  Então a resposta é 403 "PERFIL_NAO_PERMITIDO" (perfil antes do corpo)
  Quando U-COMP envia corpo {} sem Idempotency-Key
  Então a resposta é 422 "DADOS_INVALIDOS" (corpo antes da chave)
  Quando U-COMP envia corpo válido sem Idempotency-Key para "nao-existe"
  Então a resposta é 400 "IDEMPOTENCY_KEY_AUSENTE" (chave antes da solicitação)
  Quando U-COMP envia {"cotacaoId": "nao-existe"} para S-1 já SELECIONADA
  Então a resposta é 409 "FRETE_JA_ESCOLHIDO" (status antes da cotação)

# CA-33
Cenário: Erro não altera nada e não memoriza a chave
  Dado S-1 COTADA
  Quando U-COMP envia {"cotacaoId": "nao-existe"} com Idempotency-Key "k-1003" e recebe 404
  Então S-1 continua COTADA, sem entrega e sem mensagem em "frete_selecionado"
  Quando U-COMP envia {"cotacaoId": <id de C-GRA>} com a mesma Idempotency-Key "k-1003"
  Então a resposta é 200 sem o cabeçalho X-Idempotent-Replay
```

### RF-07 — Escolha automática a pedido

- **Prioridade:** Must
- **Enunciado (EARS):** Quando o comprador dono (ou um admin) enviar a API-06 com `{"modo": "AUTOMATICO"}` para uma solicitação `COTADA`, o serviço deve escolher a cotação pela regra automática, com critério `AUTOMATICO_MENOR_PRECO`, mesmo depois do prazo.
- **Regras aplicáveis:** RN-13 a RN-17
- **Interface:** API-06, tópico `frete_selecionado`

```gherkin
# CA-34
Cenário: Botão automático escolhe a mais barata
  Dado S-1 COTADA
  Quando U-COMP envia {"modo": "AUTOMATICO"} com Idempotency-Key "k-1004"
  Então a resposta é 200 com cotacaoId de C-ECO, transportadoraId "transp-economica", preco 6156.86, prazoDias 8, dataEntregaPrevista "2026-11-23" e criterio "AUTOMATICO_MENOR_PRECO"
  E a API-05 de S-1 retorna escolhida_por "usr-comprador-1"

# CA-35
Cenário: Desempates da regra automática
  Dado uma solicitação de um pedido igual a P-2 (sem cotação automática) com Q-A e Q-B
  Quando U-COMP envia {"modo": "AUTOMATICO"}
  Então a escolhida é Q-B (mesmo preço 5000.00, prazo 5 < 6)
  Dado outra solicitação igual com Q-A e Q-B, mas Q-B com prazoDias 6
  Então a escolhida é Q-A (mesmo preço e prazo, sem histórico: "transp-teste-a" vem antes na ordem alfabética)
  Dado outra solicitação igual com Q-A, Q-B e Q-C
  Então a escolhida é Q-C (menor preço, 4800.00, mesmo com o maior prazo)
  Dado que "transp-teste-b" tem 1 entrega concluída no prazo (rastreio ENTREGA_REALIZADA com noPrazo true) e "transp-teste-a" nenhuma
  E outra solicitação igual com Q-A e Q-B, ambas com preço 5000.00 e prazoDias 6
  Então a escolhida é Q-B (maior pontualidade)

# CA-36
Cenário: Admin escolhe em qualquer solicitação
  Dado S-1 COTADA
  Quando U-ADM envia {"modo": "AUTOMATICO"} com Idempotency-Key "k-1005"
  Então a resposta é 200 com cotacaoId de C-ECO e a API-05 retorna escolhida_por "usr-admin"
```

### RF-08 — Escolha automática no fim do prazo

- **Prioridade:** Must
- **Enunciado (EARS):** Quando a hora do módulo alcançar o `prazo_decisao_em` de uma solicitação `COTADA`, o serviço deve escolher a cotação pela regra automática, sem usuário, e publicar `frete_selecionado`.
- **Regras aplicáveis:** RN-13, RN-18
- **Interface:** rotina de prazos, tópico `frete_selecionado`

```gherkin
# CA-37
Cenário: Comprador não escolheu em 12 h
  Dado S-1 COTADA
  Quando U-ADM avança o relógio 12 h
  Então em até 3 s S-1 está SELECIONADA com cotacao_escolhida_id de C-ECO, criterio "AUTOMATICO_MENOR_PRECO" e escolhida_por null
  E há exatamente uma mensagem em "frete_selecionado" com chave "PED-1001" e criterio "AUTOMATICO_MENOR_PRECO", mesmo com as duas cópias do serviço rodando
```

### RF-09 — Comparar as cotações

- **Prioridade:** Must
- **Enunciado (EARS):** Quando um usuário que vê a solicitação consultar a API-07, o serviço deve devolver as cotações lado a lado, com preço por t·km, selos, desempenho da transportadora e se ele ainda pode escolher.
- **Regras aplicáveis:** RN-19, RN-26
- **Interface:** API-07

```gherkin
# CA-38
Cenário: Comparação antes da escolha
  Dado S-1 COTADA no cenário S0
  Quando U-COMP consulta a API-07 de S-1
  Então a resposta é 200 com cotacoes na ordem C-ECO, C-GRA, C-EXP
  E preco_t_km 0.1227, 0.1417 e 0.1799
  E selos ["MAIS_BARATA", "RECOMENDADA_PELA_REGRA"], [] e ["MAIS_RAPIDA"]
  E escolhida false nas três, desempenho {"entregas": 0, "pct_no_prazo": null, "atraso_medio_horas": null} nas três
  E podeEscolher true, entregaId null e horaDoModulo igual à hora do módulo
  Quando U-FORN consulta
  Então podeEscolher é false

# CA-39
Cenário: Comparação depois da escolha
  Dado a escolha do CA-21
  Quando U-COMP consulta a API-07 de S-1
  Então escolhida é true só em C-GRA, podeEscolher é false e entregaId é o id de E-1

# CA-40
Cenário: Empates, pontualidade e erros
  Dado uma solicitação de um pedido igual a P-2 com Q-A e Q-B, ambas com preço 5000.00 e prazoDias 5
  Quando U-COMP consulta a API-07
  Então as duas têm "MAIS_BARATA" e "MAIS_RAPIDA", e só Q-A tem "RECOMENDADA_PELA_REGRA"
  Dado que "transp-teste-a" tem 2 entregas concluídas, uma no prazo e outra com atrasoHoras 6.0, e "transp-teste-b" nenhuma
  Então Q-A tem desempenho {"entregas": 2, "pct_no_prazo": 0.5, "atraso_medio_horas": 3.0} e o selo "MAIS_PONTUAL"
  Quando U-COMP2 consulta a API-07 de S-1
  Então a resposta é 404 com codigo "SOLICITACAO_NAO_ENCONTRADA"
  Quando U-TRANSP consulta
  Então a resposta é 403 com codigo "PERFIL_NAO_PERMITIDO"
```

### RF-10 — Cancelamento do pedido

- **Prioridade:** Must
- **Enunciado (EARS):** Quando uma mensagem válida de `pedido_atualizado` com status `CANCELADO` for recebida, o serviço deve encerrar a solicitação aberta e as entregas ativas do pedido; se o pedido ainda não tiver solicitação, deve registrar o cancelamento.
- **Regras aplicáveis:** RN-06, RN-20
- **Interface:** tópico `pedido_atualizado`

```gherkin
# CA-41
Cenário: Cancelamento antes da escolha
  Dado S-1 COTADA
  Quando pedido_atualizado {"pedidoId": "PED-1001", "statusAnterior": "CRIADO", "novoStatus": "CANCELADO"} é publicado
  Então S-1 tem status "CANCELADA"
  E depois de U-ADM avançar o relógio 12 h, não há mensagem para "PED-1001" em "frete_selecionado" nem em "frete_indisponivel"

# CA-42
Cenário: Cancelamento depois da escolha
  Dado E-1 com status "AGUARDANDO_COLETA"
  Quando pedido_atualizado {"pedidoId": "PED-1001", "status": "cancelado"} é publicado
  Então E-1 tem status "CANCELADA" e S-1 continua "SELECIONADA"
  E um rastreio_atualizado posterior para E-1 com sequência nova é ignorado (E-1 continua "CANCELADA")

# CA-43
Cenário: Outras mudanças de status e mensagens inválidas
  Dado S-1 COTADA
  Quando pedido_atualizado {"pedidoId": "PED-1001", "novoStatus": "EM_SEPARACAO"} é publicado
  Então S-1 continua "COTADA" e não há mensagem em "logistica.dlt"
  Quando pedido_atualizado {"pedidoId": "PED-1001"} (sem status) ou {"novoStatus": "CANCELADO"} (sem pedidoId) é publicado
  Então há uma mensagem em "logistica.dlt" com failedAtAttempt 1 e S-1 continua "COTADA"
```

### RF-11 — Acompanhar a entrega

- **Prioridade:** Must
- **Enunciado (EARS):** Quando uma mensagem válida de `rastreio_atualizado` com `sequencia` maior que a última aplicada for recebida para uma entrega não encerrada, o serviço deve registrar o evento e atualizar a entrega conforme o `tipo`; ao aplicar `ENTREGA_REALIZADA`, deve publicar `entrega_concluida` e somar a entrega ao desempenho da transportadora.
- **Regras aplicáveis:** RN-21, RN-22, RN-25
- **Interface:** tópico `rastreio_atualizado`, tópico `entrega_concluida`, API-09, API-10

Os rastreios abaixo são publicados pelo QA para E-2, com `pedidoId` `"PED-1002"`, `entregaId` de E-2 e `transportadoraId` `"transp-teste-a"`.

```gherkin
# CA-44
Cenário: Viagem alocada
  Dado E-2 com status "AGUARDANDO_ALOCACAO"
  Quando é publicado o rastreio sequencia 1, tipo "VIAGEM_ALOCADA", descricao "Motorista Ana Teste e veículo TST1A23 escalados.", motorista {"nome": "Ana Teste", "telefone": "(41) 90000-0001", "cnhMascarada": "*******0001"}, veiculo {"placa": "TST1A23", "tipo": "CARRETA_FRIGORIFICA"}, transportadora {"nome": "Teste A", "telefone": "(41) 4000-0000"}, rota [[-12.5453, -55.7114], [-23.9608, -46.3336]], posicao {"lat": -12.5453, "lon": -55.7114}, coletaPrevista "2026-11-11T09:00:00.000Z", previsaoChegada "2026-11-19T17:00:00.000Z" e ocorridoEm "2026-11-10T13:00:00.000Z"
  Então a API-09 de E-2 retorna status "AGUARDANDO_COLETA", motorista_nome "Ana Teste", motorista_cnh_mascarada "*******0001", veiculo_placa "TST1A23", transportadora_nome "Teste A", transportadora_telefone "(41) 4000-0000", coleta_prevista "2026-11-11T09:00:00.000Z", previsao_chegada "2026-11-19T17:00:00.000Z", progresso 0.0, posicao_lat -12.5453 e rota com 2 pontos
  E a API-10 retorna eventos com 1 item: sequencia 1, tipo "VIAGEM_ALOCADA"

# CA-45
Cenário: Coleta e posição
  Quando é publicado o rastreio sequencia 2, tipo "COLETA_REALIZADA", ocorridoEm "2026-11-11T09:10:00.000Z"
  Então E-2 tem status "EM_TRANSITO" e coletada_em "2026-11-11T09:10:00.000Z"
  Quando é publicado o rastreio sequencia 3, tipo "POSICAO", posicao {"lat": -18.25, "lon": -51.02}, progresso 0.5, previsaoChegada "2026-11-19T17:00:00.000Z", ocorridoEm "2026-11-15T12:00:00.000Z"
  Então a API-10 retorna progresso 0.5, posicao {"lat": -18.25, "lon": -51.02}, posicaoEm "2026-11-15T12:00:00.000Z" e status "EM_TRANSITO"

# CA-46
Cenário: Rastreio repetido ou atrasado é ignorado
  Dado E-2 com o rastreio sequencia 3 aplicado (progresso 0.5)
  Quando é publicado, com outro eventId, o rastreio sequencia 3, tipo "POSICAO", progresso 0.9
  Então E-2 continua com progresso 0.5
  Quando é publicado o rastreio sequencia 2, tipo "POSICAO", progresso 0.1
  Então E-2 continua com progresso 0.5 e a API-10 continua com 3 eventos
  E nenhuma dessas mensagens vai para "logistica.dlt"

# CA-47
Cenário: Parada, previsão nova e ocorrência
  Quando é publicado o rastreio sequencia 4, tipo "PARADA", posicao {"lat": -19.0, "lon": -50.4}, progresso 0.55, previsaoChegada "2026-11-19T17:00:00.000Z", local "na rodovia", duracaoPrevistaMin 480
  Então E-2 tem progresso 0.55 e status "EM_TRANSITO"
  Quando é publicado o rastreio sequencia 5, tipo "PREVISAO_ATUALIZADA", posicao {"lat": -20.0, "lon": -49.9}, progresso 0.62, previsaoChegada "2026-11-20T21:36:00.000Z", previsaoAnterior "2026-11-19T17:00:00.000Z"
  Então E-2 tem previsao_chegada "2026-11-20T21:36:00.000Z"
  Quando é publicado o rastreio sequencia 6, tipo "OCORRENCIA", descricao "Pneu furado; troca em andamento."
  Então E-2 tem com_ocorrencia true e status "EM_TRANSITO"

# CA-48
Cenário: Entrega realizada
  Quando é publicado o rastreio sequencia 7, tipo "ENTREGA_REALIZADA", posicao {"lat": -23.9608, "lon": -46.3336}, noPrazo false, atrasoHoras 15.6, ocorridoEm "2026-11-20T21:36:00.000Z"
  Então E-2 tem status "ENTREGUE", entregue_em "2026-11-20T21:36:00.000Z", no_prazo false, atraso_horas 15.6 e progresso 1.0
  E há exatamente uma mensagem em "entrega_concluida" com chave "PED-1002" e payload igual ao exemplo do §7.4 (com entregaId de E-2 e prazoPrometido "2026-11-19")
  E, numa nova solicitação com cotação de "transp-teste-a", a API-07 mostra desempenho {"entregas": 1, "pct_no_prazo": 0.0, "atraso_medio_horas": 15.6}

# CA-49
Cenário: Rastreio de entrega encerrada é ignorado
  Dado E-2 ENTREGUE
  Quando é publicado o rastreio sequencia 8, tipo "POSICAO", progresso 0.3
  Então E-2 continua "ENTREGUE" com progresso 1.0, sem nova mensagem em "entrega_concluida" e sem mensagem em "logistica.dlt"

# CA-50
Cenário: Rastreio inválido vai para a DLT
  Quando é publicado um rastreio com entregaId "nao-existe"
  Então há uma mensagem em "logistica.dlt" com failedAtAttempt 1 e error "Entrega desconhecida: nao-existe"
  Quando é publicado um rastreio com tipo "TELEPORTE", ou tipo "VIAGEM_ALOCADA" sem motorista, ou tipo "VIAGEM_ALOCADA" sem posicao
  Então há uma mensagem em "logistica.dlt" com failedAtAttempt 1 e error começando com "Payload de rastreio_atualizado fora do contrato:"
```

### RF-12 — Trocar de transportadora quando a viagem é recusada

- **Prioridade:** Must
- **Enunciado (EARS):** Quando um `rastreio_atualizado` do tipo `VIAGEM_RECUSADA` for aplicado, o serviço deve encerrar a entrega como `RECUSADA` e passar o frete para a próxima cotação válida pela regra automática; se não houver, deve declarar o frete indisponível.
- **Regras aplicáveis:** RN-23, RN-24
- **Interface:** tópico `rastreio_atualizado`, tópicos `frete_selecionado` e `frete_indisponivel`, API-08, API-11

```gherkin
# CA-51
Cenário: Recusa passa para a próxima cotação
  Dado uma solicitação S-3 de um pedido "PED-1004" igual a P-2, com Q-A e Q-B (Q-B com preço 5100.00), e U-COMP escolheu Q-A, criando a entrega E-3 (tentativa 1)
  Quando é publicado para E-3 o rastreio sequencia 1, tipo "VIAGEM_RECUSADA", motivo "SEM_MOTORISTA", transportadoraId "transp-teste-a"
  Então E-3 tem status "RECUSADA" e a cotação Q-A tem status "VIAGEM_RECUSADA"
  E S-3 continua "SELECIONADA", com cotacao_escolhida_id de Q-B, criterio "AUTOMATICO_MENOR_PRECO" e escolhida_por "usr-comprador-1" (o campo não muda na troca)
  E existe a entrega E-3b com tentativa 2, status "AGUARDANDO_ALOCACAO" e transportadora_id "transp-teste-b"
  E há uma segunda mensagem em "frete_selecionado" com chave "PED-1004", entregaId de E-3b, tentativa 2, transportadoraId "transp-teste-b" e criterio "AUTOMATICO_MENOR_PRECO"
  E a API-08 de U-COMP mostra E-3b e não mostra E-3; com incluir_recusadas=true mostra as duas; a API-11 de "PED-1004" retorna E-3b

# CA-52
Cenário: Sem cotação restante
  Dado o resultado do CA-51
  Quando é publicado para E-3b o rastreio sequencia 1, tipo "VIAGEM_RECUSADA", motivo "SEM_VEICULO", transportadoraId "transp-teste-b"
  Então E-3b tem status "RECUSADA" e S-3 tem status "INDISPONIVEL"
  E há exatamente uma mensagem em "frete_indisponivel" com chave "PED-1004", motivo "SEM_TRANSPORTADORA_DISPONIVEL" e detalhe "Nenhuma transportadora que cotou tem frota livre"
  E não há terceira mensagem em "frete_selecionado" para "PED-1004"

# CA-53
Cenário: Recusa repetida não troca duas vezes
  Dado a recusa de E-3 aplicada (CA-51)
  Quando o mesmo rastreio de recusa de E-3 é publicado de novo com outro eventId
  Então continua havendo exatamente 2 mensagens em "frete_selecionado" para "PED-1004" e uma entrega com tentativa 2
```

### RF-13 — Consultar entregas e rastreio

- **Prioridade:** Must
- **Enunciado (EARS):** Quando um usuário com perfil comprador, fornecedor ou admin consultar a API-08, a API-09, a API-10 ou a API-11, o serviço deve devolver só as entregas visíveis para ele.
- **Regras aplicáveis:** RN-19, RN-28, RN-29
- **Interface:** API-08 a API-11

```gherkin
# CA-54
Cenário: Lista de entregas
  Dado E-1 com status "AGUARDANDO_COLETA"
  Quando U-COMP ou U-FORN consulta a API-08
  Então a resposta é 200 com um item igual ao exemplo da API-08
  Quando U-COMP2 consulta
  Então items é [] e total é 0
  Quando U-COMP consulta com status=ENTREGUE
  Então items é []
  Quando U-COMP consulta com size=101 ou status=PERDIDA
  Então a resposta é 422 com codigo "DADOS_INVALIDOS"

# CA-55
Cenário: Detalhe, rastreio e entrega do pedido
  Dado E-2 antes de qualquer rastreio (a transportadora de teste não aloca sozinha)
  Quando U-COMP consulta a API-10 de E-2
  Então status é "AGUARDANDO_ALOCACAO", posicao é null, previsaoChegada é null, rota é [] e eventos é []
  E a API-09 de E-2 tem motorista_nome null, veiculo_placa null, rota null e progresso 0.0
  Dado E-1 depois do VIAGEM_ALOCADA
  Quando U-COMP consulta a API-09, a API-10 de E-1 e a API-11 de "PED-1001"
  Então as respostas são 200 com os campos dos exemplos da API-09, da API-10 e da API-09, respectivamente
  Quando U-COMP2 consulta a API-09 ou a API-10 de E-1, ou U-COMP consulta a API-11 de "PED-9999"
  Então a resposta é 404 com codigo "ENTREGA_NAO_ENCONTRADA"
  Quando U-TRANSP consulta a API-09 de E-1
  Então a resposta é 403 com codigo "PERFIL_NAO_PERMITIDO"
```

### RF-14 — Relógio do módulo

- **Prioridade:** Must
- **Enunciado (EARS):** Quando qualquer usuário autenticado consultar a API-12, o serviço deve devolver a hora do módulo. Quando um admin enviar a API-13 válida, o serviço deve gravar o novo estado do relógio sem salto para trás e publicar `relogio_ajustado`.
- **Regras aplicáveis:** RN-27
- **Interface:** API-12, API-13, tópico `relogio_ajustado`

```gherkin
# CA-56
Cenário: Consultar o relógio
  Dado o cenário S0
  Quando U-TRANSP consulta a API-12
  Então a resposta é 200 com fator 1.0, versao 0 e horaDoModulo igual a horaReal (diferença < 1 s)
  Quando a API-12 é chamada sem Authorization
  Então a resposta é 401 com codigo "NAO_AUTENTICADO"

# CA-57
Cenário: Acelerar o relógio
  Dado a hora do módulo H antes do ajuste
  Quando U-ADM envia a API-13 com {"fator": 3600}
  Então a resposta é 200 com fator 3600.0, versao 1 e horaDoModulo entre H e H + 1 s de hora real
  E há uma mensagem em "relogio_ajustado" com chave "relogio" e payload versao 1, fator 3600.0, baseVirtual igual a horaDoModulo, baseReal igual a horaReal e ajustadoPor "usr-admin"
  E 2 s de hora real depois, a API-12 mostra horaDoModulo cerca de 2 h depois de H (2 s × 3600)

# CA-58
Cenário: Adiantar o relógio
  Dado a hora do módulo H e fator 1
  Quando U-ADM envia {"fator": 1, "avancarHoras": 12}
  Então a resposta é 200 com horaDoModulo entre H + 12 h e H + 12 h + 1 s, e versao igual à anterior + 1

# CA-59
Cenário: Ajuste inválido
  Quando U-ADM envia qualquer corpo entre: {"fator": 0}; {"fator": -1}; {"fator": 100000.01}; {"fator": 0.001}; {"fator": 1.234}; {"fator": 1, "avancarHoras": -1}; {"fator": 1, "avancarHoras": 1441}; {}
  Então a resposta é 422 com codigo "DADOS_INVALIDOS", a versao do relógio não muda e nenhuma mensagem é publicada em "relogio_ajustado"
  Quando U-ADM envia {"fator": 0.07} ou {"fator": 100000}
  Então a resposta é 200
  Quando U-COMP ou U-TADM envia {"fator": 2}
  Então a resposta é 403 com codigo "PERFIL_NAO_PERMITIDO"
```

### RF-15 — Saúde e métricas

- **Prioridade:** Must
- **Enunciado (EARS):** Quando `/health`, `/health/ready` ou `/metrics` for chamado, o serviço deve responder sem exigir autenticação; `/health/ready` deve responder 503 se o banco ou o Kafka não responder em 3 s.
- **Interface:** API-01, API-02, API-03

```gherkin
# CA-60
Cenário: Saúde, prontidão e métricas
  Quando GET /health é chamado em cada cópia (portas 8108 e 8118), sem cabeçalhos
  Então a resposta é 200 com status "UP" e service "logistica-service"
  Quando GET /health/ready é chamado com banco e Redpanda no ar
  Então a resposta é 200 com status "READY" e checks {"banco": "UP", "kafka": "UP"}
  Quando o contêiner do Redpanda é parado e GET /health/ready é chamado
  Então a resposta é 503 com status "NOT_READY" e checks.kafka começando com "DOWN"
  Quando GET /metrics é chamado depois de uma chamada à API-04
  Então a resposta é 200, em texto, com uma linha http_requests_total com service="logistica-service" e route="/api/v1/logistica/solicitacoes"
```

### RF-16 — Consumo idempotente, retentativas e DLT

- **Prioridade:** Must
- **Enunciado (EARS):** Se uma mensagem consumida não for JSON, não tiver o envelope completo ou tiver payload fora do contrato, então o serviço deve publicá-la em `logistica.dlt` sem retentativa. Se o processamento falhar por outro motivo, então o serviço deve tentar de novo depois de 1 s, 2 s e 4 s e, se continuar falhando, publicá-la em `logistica.dlt`.
- **Regras aplicáveis:** RN-30
- **Interface:** todos os tópicos consumidos, `logistica.dlt`

```gherkin
# CA-61
Cenário: Mensagem que não é JSON ou com envelope incompleto
  Quando o texto "isto não é json" é publicado em "pedido_criado"
  Então há uma mensagem em "logistica.dlt" com chave "desconhecido", originalEvent "isto não é json", failedAtAttempt 1 e originalTopic "pedido_criado"
  Quando o envelope de P-1 sem o campo eventId é publicado
  Então há uma mensagem em "logistica.dlt" com chave "desconhecido", error "Envelope sem os campos: eventId", failedAtAttempt 1 e originalEvent igual ao texto publicado
  E o consumidor continua: um P-1 válido publicado em seguida abre a solicitação

# CA-62
Cenário: Falha que não é do contrato tem 3 retentativas
  Quando P-1 é publicado com pedidoId "PED-1012" e dataEntregaDesejada "31/11/2026" (o schema não confere o formato; o banco recusa)
  Então nenhuma solicitação é criada para "PED-1012"
  E entre 7 s e 15 s depois há uma mensagem em "logistica.dlt" com failedAtAttempt 4
```

### RF-17 — Notificações no portal

- **Prioridade:** Should
- **Enunciado (EARS):** Quando uma mudança da RN-32 for gravada, o serviço deve gravar, na mesma transação, uma notificação para cada destinatário da RN-32. Quando um comprador ou fornecedor consultar a API-17 ou enviar a API-18, o serviço deve devolver ou alterar só as notificações da sua empresa e do seu perfil.
- **Regras aplicáveis:** RN-28, RN-32
- **Interface:** API-17, API-18

```gherkin
# CA-74
Cenário: Notificações do fluxo com escolha pelo comprador
  Dado S-1 COTADA
  Então a API-17 de U-COMP tem 1 item: tipo "COTACOES_DISPONIVEIS", titulo "Cotações de frete disponíveis", pedido_id "PED-1001", solicitacao_id igual ao id de S-1, lida false e criada_em igual ao recebida_em da primeira cotação de S-1; e naoLidas 1
  E a mensagem contém "PED-1001" e "10/11/2026 21:00" (prazo_decisao_em no horário de Brasília)
  E a API-17 de U-FORN tem total 0
  Quando U-COMP escolhe C-GRA (CA-21) e o VIAGEM_ALOCADA de E-1 é aplicado
  Então a API-17 de U-FORN tem 2 itens, nesta ordem: "MOTORISTA_ESCALADO" e "FRETE_ESCOLHIDO", e naoLidas 2
  E a mensagem do FRETE_ESCOLHIDO contém "pelo comprador", "Graneleira Centro-Oeste", "R$ 7.113,30" e "5 dias úteis"
  E a API-17 de U-COMP tem 2 itens: "MOTORISTA_ESCALADO" e "COTACOES_DISPONIVEIS" (quem escolheu não recebe "FRETE_ESCOLHIDO")
  E U-COMP2 tem total 0

# CA-75
Cenário: Notificações da regra automática e da falta de cotação
  Dado o cenário do CA-37 (a rotina de prazos escolheu C-ECO)
  Então U-COMP e U-FORN têm, cada um, 1 notificação "FRETE_ESCOLHIDO" de "PED-1001", com "pela regra automática (menor preço)" na mensagem
  Dado o cenário do CA-14 (S-2 SEM_COTACAO)
  Então U-COMP e U-FORN têm, cada um, 1 notificação "SEM_COTACAO" de "PED-1002" com titulo "Nenhuma transportadora cotou ainda"
  Quando o prazo vence (CA-15)
  Então cada um tem também 1 notificação "FRETE_INDISPONIVEL" de "PED-1002" com titulo "Frete indisponível"
  E nenhuma notificação é gravada por pedido_atualizado CANCELADO (CA-41)

# CA-76
Cenário: Lista de notificações
  Dado U-FORN com as 2 notificações do CA-74, ambas não lidas
  Quando U-FORN marca a "MOTORISTA_ESCALADO" como lida (API-18) e consulta a API-17 com lida=false
  Então items tem só a "FRETE_ESCOLHIDO", total 1 e naoLidas 1
  Quando consulta com lida=true
  Então items tem só a "MOTORISTA_ESCALADO", total 1 e naoLidas 1
  Quando consulta com size=1
  Então items tem só a "MOTORISTA_ESCALADO", total 2 e naoLidas 1
  Quando consulta com size=101 ou lida=talvez
  Então a resposta é 422 com codigo "DADOS_INVALIDOS"
  Quando U-ADM ou U-TRANSP consulta a API-17
  Então a resposta é 403 com codigo "PERFIL_NAO_PERMITIDO"

# CA-77
Cenário: Marcar como lida ou não lida
  Dado a notificação N = "FRETE_ESCOLHIDO" de U-FORN no CA-74
  Quando U-FORN envia a API-18 de N com {"lida": true}
  Então a resposta é 200 com o id de N, tipo "FRETE_ESCOLHIDO" e lida true
  Quando envia de novo {"lida": true}, ou envia {}
  Então a resposta é 200 com lida true
  Quando envia {"lida": false}
  Então a resposta é 200 com lida false e a API-17 volta a contar N em naoLidas
  Quando U-COMP envia a API-18 de N, ou U-FORN envia a API-18 de "nao-existe"
  Então a resposta é 404 com codigo "NOTIFICACAO_NAO_ENCONTRADA"
  Quando U-FORN envia {"lida": "talvez"}
  Então a resposta é 422 com codigo "DADOS_INVALIDOS" e erros[0].campo "body.lida"
  Quando U-ADM envia a API-18 de N
  Então a resposta é 403 com codigo "PERFIL_NAO_PERMITIDO"
```

### RF-18 — Ocorrências reportadas pelo usuário

- **Prioridade:** Should
- **Enunciado (EARS):** Quando um comprador ou fornecedor enviar a API-15 válida para uma entrega visível e não cancelada nem recusada, o serviço deve gravar a ocorrência com a hora do módulo, marcar `com_ocorrencia` na entrega e notificar a outra parte, na mesma transação. Quando um usuário consultar a API-14, o serviço deve devolver as ocorrências da entrega visível.
- **Regras aplicáveis:** RN-19, RN-32, RN-33
- **Interface:** API-14, API-15, API-10

```gherkin
# CA-78
Cenário: Comprador reporta uma ocorrência
  Dado E-1 com status "AGUARDANDO_COLETA" e com_ocorrencia false
  Quando U-COMP envia a API-15 de E-1 com {"descricao": "  Lona da carreta rasgada na foto da coleta.  "}
  Então a resposta é 201 com autor_papel "comprador", descricao "Lona da carreta rasgada na foto da coleta." (sem os espaços das pontas), id UUID e ocorrida_em igual à hora do módulo
  E a API-09 de E-1 tem com_ocorrencia true e o mesmo status
  E a API-14 de E-1, por U-FORN ou U-ADM, tem 1 item igual à resposta, e a API-10 tem o mesmo item em ocorrencias
  E U-FORN tem 1 notificação "OCORRENCIA" com titulo "Ocorrência na entrega" e mensagem contendo "O comprador" e "Lona da carreta rasgada"
  E U-COMP não recebe notificação "OCORRENCIA"
  Quando U-FORN envia a API-15 de E-1 com {"descricao": "Carga conferida, sem avaria."}
  Então a resposta é 201 com autor_papel "fornecedor", a API-14 tem 2 itens por ocorrida_em crescente e U-COMP recebe 1 notificação "OCORRENCIA" com "O fornecedor" na mensagem

# CA-79
Cenário: Ocorrência recusada
  Quando U-COMP envia a API-15 de E-1 com descricao "     " (5 espaços), "  abc  ", "abcd" ou 501 caracteres, ou sem descricao
  Então a resposta é 422 com codigo "DADOS_INVALIDOS" e erros[0].campo "body.descricao", e a API-14 não muda
  Quando U-ADM ou U-TRANSP envia a API-15 de E-1
  Então a resposta é 403 com codigo "PERFIL_NAO_PERMITIDO"
  Quando U-COMP2 envia a API-15 ou consulta a API-14 de E-1, ou U-COMP usa a entrega "nao-existe"
  Então a resposta é 404 com codigo "ENTREGA_NAO_ENCONTRADA"
  Dado E-1 CANCELADA (pedido_atualizado CANCELADO de "PED-1001", CA-42)
  Quando U-FORN envia a API-15 de E-1 com {"descricao": "Depois do cancelamento"}
  Então a resposta é 409 com codigo "ENTREGA_ENCERRADA" e nenhuma notificação é gravada
  E a API-14 de E-1 continua respondendo 200 com as ocorrências anteriores
```

### RF-19 — Documentos demonstrativos em PDF

- **Prioridade:** Could
- **Enunciado (EARS):** Quando um usuário com perfil comprador, fornecedor ou admin pedir a API-16 de uma entrega visível, o serviço deve gerar o PDF do `tipo` com os dados atuais da entrega e a marca "DOCUMENTO DEMONSTRATIVO - SEM VALOR FISCAL". Se o `tipo` for `comprovante-coleta` e a carga ainda não tiver sido coletada, então o serviço deve responder 409 `DOCUMENTO_INDISPONIVEL`.
- **Regras aplicáveis:** RN-19, RN-34
- **Interface:** API-16

```gherkin
# CA-80
Cenário: Documentos da entrega
  Dado E-1 depois do VIAGEM_ALOCADA (Roberto Nunes, PAS6J78) e antes da coleta
  Quando U-COMP pede a API-16 de E-1 com tipo cte, romaneio ou nota-fiscal
  Então a resposta é 200 com Content-Type "application/pdf", Content-Disposition 'inline; filename="<tipo>-PED-1001.pdf"' e corpo começando com "%PDF-"
  E o texto do PDF contém "DOCUMENTO DEMONSTRATIVO - SEM VALOR FISCAL", "PED-1001" e "Nº " seguido do número da RN-34 (cte 154995, romaneio 154205, nota-fiscal 448765)
  E o texto do cte contém "Graneleira Centro-Oeste", "PAS6J78" e "Roberto Nunes"
  Quando U-COMP pede o mesmo tipo de novo
  Então o número é o mesmo
  Dado E-1 depois do COLETA_REALIZADA
  Quando U-FORN ou U-ADM pede a API-16 de E-1 com tipo comprovante-coleta
  Então a resposta é 200 e o texto contém "Nº 600897"

# CA-81
Cenário: Documento recusado
  Dado E-1 antes do COLETA_REALIZADA
  Quando U-COMP pede a API-16 de E-1 com tipo comprovante-coleta
  Então a resposta é 409 com codigo "DOCUMENTO_INDISPONIVEL"
  Quando U-COMP pede com tipo boleto
  Então a resposta é 422 com codigo "DADOS_INVALIDOS" e erros[0].campo "path.tipo"
  Quando U-COMP2 pede a API-16 de E-1, ou U-COMP pede a da entrega "nao-existe"
  Então a resposta é 404 com codigo "ENTREGA_NAO_ENCONTRADA"
  Quando U-TRANSP pede a API-16 de E-1
  Então a resposta é 403 com codigo "PERFIL_NAO_PERMITIDO"
```

## 9. Regras de negócio

| ID | Regra | Exemplo concreto |
|---|---|---|
| RN-01 | Origem e destino são procurados na tabela de 35 cidades (Apêndice A) pelo nome, sem diferenciar maiúsculas, acentos e espaços repetidos, e pela UF (exata, maiúscula, garantida pelo contrato). A solicitação grava o nome e a UF da tabela. Origem fora da tabela → DLT com `error` `"Cidade de origem desconhecida: <origem recebida>"`; depois, o mesmo para o destino. | `"  sao   paulo "`/`SP` → São Paulo. `Atlântida`/`MT` → DLT. |
| RN-02 | `distancia_km` = `arredondar(haversine × 1,3; 1 casa)`, com as coordenadas da tabela. | Sorriso/MT → Santos/SP: 2091.1. Rio Verde/GO → Paranaguá/PR: 1163.0. |
| RN-03 | `data_coleta_prevista` = próximo dia útil da data **UTC** de `aberta_em`. | `2026-11-10T12:00Z` → `2026-11-11`; `2026-11-13T12:00Z` → `2026-11-16`. |
| RN-04 | `prazo_decisao_em` = `aberta_em` + `PRAZO_DECISAO_SEGUNDOS` (43200 s = 12 h). | `2026-11-10T12:00:00.000Z` → `2026-11-11T00:00:00.000Z`. |
| RN-05 | Há no máximo uma solicitação por `pedidoId`. Um segundo `pedido_criado` para o mesmo pedido, com outro `eventId`, é ignorado: não altera, não publica, não vai à DLT. | CA-03. |
| RN-06 | `pedido_atualizado` CANCELADO de um pedido sem solicitação registra o cancelamento. Um `pedido_criado` posterior desse pedido não abre solicitação, não publica e não vai à DLT. | CA-08. |
| RN-07 | Há no máximo uma cotação por (solicitação, transportadora). Uma segunda é ignorada e a primeira fica como está. | CA-10. |
| RN-08 | A cotação recebida com a solicitação aberta tem `status` `"VALIDA"`; com a solicitação em qualquer outro status, `"RECUSADA_TARDE"`. Cotação tardia é guardada, aparece na API-05 e na API-07, e não pode ser escolhida. Solicitação inexistente → DLT `"Solicitação desconhecida: <id>"`. | CA-12. |
| RN-09 | A primeira cotação válida muda a solicitação de `ABERTA` ou `SEM_COTACAO` para `COTADA`. | CA-09, CA-13. |
| RN-10 | Rodada automática: uma solicitação `ABERTA` sem cotação passa a `SEM_COTACAO` quando a hora **real** alcança abertura + `RODADA_COTACAO_SEGUNDOS` (10 s). A rotina roda a cada 1 s. A rodada usa hora real porque é a espera técnica das respostas automáticas: no relógio acelerado, ela terminaria antes de as cotações chegarem. | CA-14. |
| RN-11 | Quando `agora ≥ prazo_decisao_em` e a solicitação está `SEM_COTACAO`, ela passa a `INDISPONIVEL` e o serviço publica `frete_indisponivel` com motivo `SEM_COTACAO`. | CA-15. |
| RN-12 | O comprador pode escolher **qualquer** cotação válida, não só a mais barata, enquanto `agora ≤ prazo_decisao_em` (inclusive). Com `agora > prazo_decisao_em` → 409 `PRAZO_DE_ESCOLHA_ENCERRADO`. | CA-21 escolhe C-GRA, que não é a mais barata. |
| RN-13 | Regra automática (glossário), usada no botão (`modo: AUTOMATICO`), no fim do prazo e na troca de transportadora: menor `preco` → menor `prazo_dias` → maior pontualidade (sem histórico = 0) → menor `transportadora_id`. Considera só cotações `VALIDA`. | Q-A 5000/6 × Q-B 5000/5 → Q-B. |
| RN-14 | A escolha só grava se o status ainda for `COTADA` (gravação condicional). Erros de status, verificados antes do prazo e da cotação: `SELECIONADA` → 409 `FRETE_JA_ESCOLHIDO`; `ABERTA` ou `SEM_COTACAO` → 409 `SEM_COTACAO_PARA_ESCOLHER`; `CANCELADA` ou `INDISPONIVEL` → 409 `SOLICITACAO_ENCERRADA`. Se outra escolha gravar entre a leitura e a gravação → 409 `FRETE_JA_ESCOLHIDO`. | Duas escolhas simultâneas: uma 200, a outra 409. |
| RN-15 | Idempotência da API-06: o cabeçalho `Idempotency-Key` é obrigatório (ausente, vazio ou só espaços → 400 `IDEMPOTENCY_KEY_AUSENTE`; mais de 100 caracteres → 422). A chave memorizada é o par (`sub` do usuário, `Idempotency-Key`). Só respostas 200 são memorizadas, na mesma transação da escolha. Depois da validação do corpo e da presença da chave, um par memorizado devolve 200 com o corpo memorizado e `X-Idempotent-Replay: true`, sem conferir solicitação, status, prazo ou cotação, sem nova escolha e sem novo evento. O mesmo valor de chave enviado por outro usuário não é replay. | CA-23, CA-24. |
| RN-16 | Escolhem: o comprador cuja empresa é o `comprador_id` da solicitação, ou um admin. Outro comprador recebe 404 `SOLICITACAO_NAO_ENCONTRADA` (a existência não é revelada). Fornecedor e transportadora → 403. | CA-28. |
| RN-17 | A escolha grava, na mesma transação: status `SELECIONADA`, `cotacao_escolhida_id`, `criterio`, `escolhida_por`, `escolhida_em` (hora do módulo); uma entrega com `tentativa` 1, status `AGUARDANDO_ALOCACAO` e `prazo_prometido` = `data_entrega_prevista` da cotação; e o `frete_selecionado` na outbox. | CA-21, CA-22. |
| RN-18 | Quando `agora ≥ prazo_decisao_em` e a solicitação está `COTADA`, a rotina de prazos aplica a regra automática com `criterio` `AUTOMATICO_MENOR_PRECO` e `escolhida_por` `null`. Com duas cópias, cada solicitação é tratada por uma só (`FOR UPDATE SKIP LOCKED`). | CA-37. |
| RN-19 | Visibilidade (glossário). O que não é visível responde 404, como se não existisse. As listas só contam o que é visível. | U-COMP2 não vê S-1. |
| RN-20 | Cancelamento: só age se `novoStatus` (ou, na falta, `status`) for `CANCELADO`, sem diferenciar maiúsculas. Solicitação aberta → `CANCELADA`. Entregas ativas do pedido → `CANCELADA`. Solicitação `SELECIONADA` continua `SELECIONADA`. Outros status do pedido são ignorados, sem DLT. | CA-41 a CA-43. |
| RN-21 | Rastreio: entrega desconhecida → DLT `"Entrega desconhecida: <id>"`. `sequencia` ≤ última aplicada → ignorado. Entrega encerrada → ignorado. O evento ignorado não é gravado e não vai à DLT. A comparação de sequência vem antes da de status. | CA-46, CA-49. |
| RN-22 | Efeito de cada `tipo` de rastreio aplicado: `VIAGEM_ALOCADA` → status `AGUARDANDO_COLETA`, grava motorista, veículo, `rota`, `coleta_prevista`, `previsao_chegada`, posição e `posicao_em` = `ocorridoEm`, `progresso` 0, e o nome e o telefone da transportadora se vierem; `COLETA_REALIZADA` → `EM_TRANSITO`, `coletada_em` = `ocorridoEm`, posição se vier; `POSICAO`, `PARADA` e `PREVISAO_ATUALIZADA` → posição, `posicao_em`, `progresso` e `previsao_chegada`; `OCORRENCIA` → `com_ocorrencia` = true; `ENTREGA_REALIZADA` → `ENTREGUE`, `entregue_em` = `ocorridoEm`, `no_prazo`, `atraso_horas`, `progresso` 1 e posição; `VIAGEM_RECUSADA` → RN-23. Todo rastreio aplicado é gravado em `eventos` (API-10). | CA-44 a CA-48. |
| RN-23 | Recusa da viagem: a entrega vira `RECUSADA` e a cotação dela `VIAGEM_RECUSADA`. Entre as cotações `VALIDA` restantes, a regra automática escolhe a nova; a solicitação continua `SELECIONADA`, com a nova `cotacao_escolhida_id` e `criterio` `AUTOMATICO_MENOR_PRECO` (`escolhida_por` e `escolhida_em` não mudam). Cria-se uma entrega com `tentativa` + 1 e publica-se um novo `frete_selecionado`. A troca é condicional à cotação recusada ainda ser a escolhida: uma recusa repetida não troca de novo. | CA-51, CA-53. |
| RN-24 | Se não restar cotação `VALIDA`, a solicitação passa a `INDISPONIVEL` e o serviço publica `frete_indisponivel` com motivo `SEM_TRANSPORTADORA_DISPONIVEL`. | CA-52. |
| RN-25 | Ao aplicar `ENTREGA_REALIZADA`, o desempenho da transportadora soma 1 em `entregas`, 1 em `entregas_no_prazo` se `noPrazo` for true, e `atrasoHoras` em `atraso_total_horas`; e o serviço publica `entrega_concluida`. | CA-48. |
| RN-26 | Comparação (API-07): `preco_t_km` (glossário); selos calculados só entre cotações `VALIDA`, e empates ganham o selo juntos: `MAIS_BARATA` (menor preço), `MAIS_RAPIDA` (menor prazo), `MAIS_PONTUAL` (maior pontualidade, só se alguma tiver histórico), `RECOMENDADA_PELA_REGRA` (a que a regra automática escolheria, uma só); cotação não válida tem `selos` `[]`. `desempenho`: `entregas` (0 sem histórico), `pct_no_prazo` (4 casas ou `null`), `atraso_medio_horas` (`atraso_total_horas ÷ entregas`, 1 casa, ou `null`). `escolhida`: id = `cotacao_escolhida_id`. `podeEscolher`: status `COTADA` **e** `agora ≤ prazo_decisao_em` **e** perfil comprador ou admin. | CA-38 a CA-40. |
| RN-27 | Relógio: `agora = base_virtual + (hora real − base_real) × fator`. O ajuste calcula a hora do módulo atual, soma `avancarHoras` e grava como nova `base_virtual`, com `base_real` = hora real, o novo `fator` e `versao` + 1. Nunca volta para trás. Dois ajustes simultâneos são serializados por trava no banco. | Fator 1 → 3600 às 12:10: `baseVirtual` 12:10, e 1 s real depois o módulo marca 13:10. |
| RN-28 | Paginação: `page` ≥ 1 (padrão 1), `size` de 1 a 100 (padrão 10); fora disso → 422. Solicitações por `aberta_em` decrescente; entregas por criação decrescente. `total` conta os itens visíveis com os filtros aplicados. | `size=101` → 422. |
| RN-29 | A API-08 omite entregas `RECUSADA`, a menos que `incluir_recusadas=true`; com `status` informado, vale só o filtro de status. A API-11 devolve a entrega de maior `tentativa` do pedido, de qualquer status. | CA-51. |
| RN-30 | Consumo: o `eventId` é gravado em `processed_events` na mesma transação do efeito; um `eventId` já gravado é ignorado. JSON ilegível, envelope incompleto, payload fora do contrato ou referência inexistente (`EventoInvalido`) → DLT direto (`failedAtAttempt` 1). Outra falha → novas tentativas depois de 1 s, 2 s e 4 s; depois → DLT (`failedAtAttempt` 4). Mensagem com `eventId` que foi para a DLT por payload inválido fica marcada: uma cópia dela é ignorada. O offset só avança depois de processar ou de gravar na DLT; se o banco estiver fora, o consumidor espera e não perde a mensagem. | CA-61, CA-62. |
| RN-31 | Requisição com erro (qualquer 4xx) não altera estado, não grava evento e não memoriza a `Idempotency-Key`. | CA-33. |
| RN-32 | Notificações: gravadas na mesma transação da mudança, com `criada_em` = hora do módulo dessa mudança e `lida` false. Destinatário = (empresa, perfil): `comprador_id` com perfil comprador e `fornecedor_id` com perfil fornecedor. Transportadora e admin não recebem. Tipos, `titulo` (literal) e quem recebe: `COTACOES_DISPONIVEIS` "Cotações de frete disponíveis" (primeira cotação válida muda a solicitação para `COTADA`, RN-09) → comprador. `SEM_COTACAO` "Nenhuma transportadora cotou ainda" (RN-10) → os dois. `FRETE_ESCOLHIDO` "Frete escolhido" (RN-17 e RN-18) → fornecedor; também o comprador quando `escolhida_por` é `null` (rotina de prazos). `FRETE_INDISPONIVEL` "Frete indisponível" (RN-11, RN-24) → os dois. `TRANSPORTADORA_TROCADA` "Transportadora trocada" (RN-23) → os dois. `MOTORISTA_ESCALADO` "Motorista escalado" (`VIAGEM_ALOCADA`) → os dois. `COLETA_REALIZADA` "Carga coletada" → os dois. `PREVISAO_ATUALIZADA` "Previsão de chegada alterada" → comprador. `ENTREGA_REALIZADA` "Entrega realizada" → os dois. `OCORRENCIA` "Ocorrência na entrega" (API-15) → a outra parte (quem reportou não recebe). Cancelamento (RN-20), rastreio `POSICAO`, `PARADA` e `OCORRENCIA`, e ajuste do relógio não geram notificação. Uma mudança que não acontece (mensagem ignorada, gravação condicional que perde) não gera notificação. | CA-74 a CA-77. |
| RN-33 | Ocorrência (API-15): só comprador ou fornecedor, numa entrega visível (RN-19) com status diferente de `CANCELADA` e `RECUSADA` (entrega `ENTREGUE` aceita: avaria descoberta na chegada). `descricao`: os espaços das pontas são retirados antes de contar; de 5 a 500 caracteres depois disso. Grava `autor_papel` = perfil e `ocorrida_em` = hora do módulo; marca `com_ocorrencia` true; notifica a outra parte (RN-32). A API-14 e o campo `ocorrencias` da API-10 listam todas, por `ocorrida_em` crescente, para qualquer status da entrega. | "  abc  " → 422; entrega `CANCELADA` → 409. CA-78, CA-79. |
| RN-34 | Documentos (API-16): PDF gerado na hora com os dados atuais da entrega (API-09), em qualquer status, inclusive `CANCELADA` e `ENTREGUE`. Todo documento tem, no cabeçalho, "Portal B2B - <título>", "Nº <número>" e "Emitido em <hora do módulo, horário de Brasília> (hora do módulo)", e a marca d'água "DOCUMENTO DEMONSTRATIVO - SEM VALOR FISCAL". Títulos: `cte` "CT-e - Conhecimento de Transporte Eletrônico"; `romaneio` "Romaneio de carga"; `nota-fiscal` "Nota fiscal de venda"; `comprovante-coleta` "Comprovante de coleta". Número = `int(sha1("<tipo>:<id da entrega>") em hexadecimal, 8 primeiros dígitos) mod 1000000`, com 6 dígitos (zeros à esquerda): o mesmo documento tem sempre o mesmo número. Campos ainda vazios aparecem como "a definir" (placa, motorista) ou "-". `comprovante-coleta` só existe com `coletada_em` preenchido; antes → 409 `DOCUMENTO_INDISPONIVEL`. | E-1: cte 154995, romaneio 154205, nota-fiscal 448765, comprovante-coleta 600897. CA-80, CA-81. |

## 10. Catálogo de erros

Formato único (RFC 7807), com `Content-Type: application/problem+json`:
```json
{
  "type": "https://portal-b2b.corp/erros/frete-ja-escolhido",
  "title": "Frete já escolhido",
  "status": 409,
  "detail": "A solicitação 5c0e7b9a-3d2f-4e8a-9b1c-7f6a2d4e8c10 já teve o frete escolhido.",
  "instance": "/api/v1/logistica/solicitacoes/5c0e7b9a-3d2f-4e8a-9b1c-7f6a2d4e8c10/selecionar-frete",
  "correlationId": "66caa64de354f62e526052141516a135",
  "timestamp": "2026-11-10T12:06:00.000Z",
  "codigo": "FRETE_JA_ESCOLHIDO"
}
```
- `type` = `"https://portal-b2b.corp/erros/"` + `codigo` em minúsculas com `_` trocado por `-`.
- `codigo` é o identificador estável para os testes; `title` e `detail` são texto em português e podem mudar.
- `DADOS_INVALIDOS` traz também `erros`: lista de `{"campo": "<origem>.<nome>", "mensagem": "<texto>"}`, com origem `body`, `query`, `header` ou `path`. A validação automática do framework é convertida para este formato.

| Código | HTTP | Quando ocorre |
|---|---|---|
| `NAO_AUTENTICADO` | 401 | Sem `Authorization: Bearer` (§7.1, passo 1). |
| `TOKEN_INVALIDO` | 401 | Token ilegível, sem `kid`, `kid` desconhecido, assinatura ou algoritmo inválido, sem `sub` ou `exp`, `iss` ou `aud` ausentes ou diferentes dos configurados (§7.1). |
| `TOKEN_EXPIRADO` | 401 | `exp` no passado, com assinatura válida. |
| `AUTENTICACAO_INDISPONIVEL` | 503 | JWKS inacessível. |
| `PERFIL_NAO_PERMITIDO` | 403 | Perfil fora dos permitidos da rota, ou `TENANT_ADMIN` sem ser administrador da plataforma. |
| `CONTEXTO_NAO_SELECIONADO` | 403 | Token sem empresa ou sem escopo ativo (`view_mode` `NONE` ou `MACRO_GROUP`), de quem não é administrador da plataforma. |
| `PERFIL_AUSENTE` | 403 | `active_scope` desconhecido (ou, no formato HS256, `perfil` fora dos 4). |
| `DADOS_INVALIDOS` | 422 | JSON ilegível; corpo, parâmetro ou cabeçalho fora das restrições. |
| `IDEMPOTENCY_KEY_AUSENTE` | 400 | API-06 sem `Idempotency-Key` útil (RN-15). |
| `SOLICITACAO_NAO_ENCONTRADA` | 404 | Solicitação inexistente ou não visível (RN-16, RN-19). |
| `COTACAO_NAO_ENCONTRADA` | 404 | `cotacaoId` não é cotação `VALIDA` da solicitação. |
| `ENTREGA_NAO_ENCONTRADA` | 404 | Entrega inexistente ou não visível; pedido sem entrega visível. |
| `FRETE_JA_ESCOLHIDO` | 409 | Solicitação `SELECIONADA`, ou outra escolha gravou primeiro (RN-14). |
| `SEM_COTACAO_PARA_ESCOLHER` | 409 | Solicitação `ABERTA` ou `SEM_COTACAO`. |
| `SOLICITACAO_ENCERRADA` | 409 | Solicitação `CANCELADA` ou `INDISPONIVEL`. |
| `PRAZO_DE_ESCOLHA_ENCERRADO` | 409 | Escolha por `cotacaoId` com `agora > prazo_decisao_em` (RN-12). |
| `ENTREGA_ENCERRADA` | 409 | API-15 numa entrega `CANCELADA` ou `RECUSADA` (RN-33). |
| `DOCUMENTO_INDISPONIVEL` | 409 | API-16 `comprovante-coleta` antes da coleta (RN-34). |
| `NOTIFICACAO_NAO_ENCONTRADA` | 404 | API-18 de notificação inexistente, de outra empresa ou de outro perfil. |

Respostas fora do catálogo, também em RFC 7807: rota inexistente → 404 com `codigo` `NAO_ENCONTRADO`; método não permitido → 405 com `codigo` `METODO_NAO_PERMITIDO`; falha não prevista → 500 com `codigo` `ERRO_INTERNO` e o `correlationId` para o suporte. `/docs` e `/openapi.json` ficam habilitados. A resposta 503 de `/health/ready` tem o corpo da API-02, não RFC 7807. Essas respostas não entram na conformidade.

**Ordem de verificação** (quando mais de um erro se aplica, vale o primeiro):

1. Corpo que não é JSON legível (rotas com corpo) → 422 `DADOS_INVALIDOS`.
2. Autenticação, na ordem do §7.1 → 401 ou 503.
3. Perfil da rota → 403.
4. Parâmetros, cabeçalhos e corpo → 422 `DADOS_INVALIDOS`.
5. `Idempotency-Key` (só API-06) → 400.
6. Replay de idempotência (só API-06) → 200 memorizado.
7. Recurso visível → 404.
8. Status da solicitação (só API-06) → 409. Status da entrega (só API-15) → 409 `ENTREGA_ENCERRADA`. Coleta feita (só API-16 `comprovante-coleta`) → 409 `DOCUMENTO_INDISPONIVEL`.
9. Prazo da escolha (só API-06 com `cotacaoId`) → 409.
10. Cotação (só API-06 com `cotacaoId`) → 404.
11. Gravação condicional (só API-06) → 409.

## 11. Requisitos não funcionais

| ID | Característica (ISO/IEC 25010) | Requisito | Métrica e limiar | Verificação |
|---|---|---|---|---|
| RNF-01 | Eficiência de desempenho | Tempo de resposta das leituras pelo gateway, com as duas cópias | 200 usuários virtuais por 30 s, sem pausa, em API-08 (`size=20`), API-10 e API-07: p95 < 500 ms em cada rota e menos de 1% de erros | `testes_carga/leitura.js` (k6) — CA-63 |
| RNF-02 | Confiabilidade — integridade | Escolha única com duas cópias e a rotina de prazos disputando | 6 escolhas simultâneas da mesma solicitação, alternando as duas cópias e os dois tipos de corpo, junto com um ajuste do relógio para fator 100000: no máximo 1 resposta 200, as demais 409, exatamente 1 `frete_selecionado` (na outbox e no tópico) e 1 entrega | `testes_integracao/test_cenarios_distribuidos.py` — CA-64 |
| RNF-03 | Confiabilidade — tolerância a falhas | Uma cópia de cada serviço cai no meio da viagem | Com `logistica-1` e `transportadoras-1` paradas e a entrega `EM_TRANSITO`, a entrega chega a `ENTREGUE` só com as cópias 2: rastreios com sequência 1 a N sem buraco, `entrega_concluida` gravado uma vez na outbox | `testes_integracao/test_cenarios_distribuidos.py` — CA-65 |
| RNF-04 | Confiabilidade — recuperabilidade | Kafka fora do ar não perde evento | Com o Redpanda parado, a API-06 responde 200; o `frete_selecionado` fica na outbox e é publicado uma vez em até 30 s depois de o Redpanda voltar | Teste manual — CA-66 |
| RNF-05 | Compatibilidade — interoperabilidade | Formato único de erro | 100% das respostas 4xx e 5xx da API (exceto `/health/ready`) em `application/problem+json`, com `type`, `title`, `status`, `detail`, `instance`, `correlationId`, `timestamp` e `codigo` não vazios | CA-67 |
| RNF-06 | Manutenibilidade — analisabilidade | Correlação de ponta a ponta | 100% das respostas devolvem o `X-Correlation-Id` recebido; 100% dos eventos derivados de um pedido têm o `correlationId` do `pedido_criado` | CA-68 |
| RNF-07 | Confiabilidade — ordenação | Chave de partição estável | 100% das mensagens publicadas com chave igual ao `aggregateId` do §7.4 | CA-69 |
| RNF-08 | Eficiência — uso de recursos | Pool limitado | No máximo 5 conexões abertas por cópia (`pg_stat_activity` com `usename = 'svc_logistica'` ≤ 10 com as duas cópias) durante o teste de carga | Inspeção — CA-70 |
| RNF-09 | Manutenibilidade | Logs estruturados | 100% das linhas do stdout do serviço são JSON com `timestamp`, `level`, `service` e `message`; nenhum `print(` no código do serviço (os scripts de linha de comando de `comum/comum/ferramentas/` podem imprimir) | Inspeção — CA-71 |
| RNF-10 | Portabilidade | Só as dependências permitidas (§5) | Nenhum `import` fora da biblioteca padrão, das dependências do §5, de `comum` e de `logistica` | Inspeção — CA-72 |
| RNF-11 | Eficiência de desempenho e confiabilidade | Gravações com muitos pedidos ao mesmo tempo, pelo gateway | 10 pedidos novos por segundo durante 60 s, cada um com cotação, escolha da mais barata (API-06), espera da alocação e cancelamento: API-06 com p95 < 500 ms; do pedido às cotações com p95 < 20 s; 0 solicitação duplicada (API-04 com `pedido_id` devolve no máximo 1); menos de 1% de erros HTTP | `testes_carga/escrita.js` (k6) — CA-82 |

```gherkin
# CA-63
Cenário: Carga de leitura
  Dado ao menos uma entrega no ambiente
  Quando o script testes_carga/leitura.js roda com 200 VUs por 30 s
  Então os limiares p(95)<500 das rotas entregas, rastreio e comparacao e http_req_failed rate<0.01 passam

# CA-64
Cenário: Escolhas simultâneas nas duas cópias
  Dado S-1 COTADA
  Quando 6 requisições da API-06 de U-COMP, com Idempotency-Key diferentes, alternando as portas 8108 e 8118 e os corpos {"modo": "AUTOMATICO"} e {"cotacaoId": ...}, e um POST da API-13 com {"fator": 100000} são enviados ao mesmo tempo
  Então cada escolha responde 200 ou 409, com no máximo uma 200 (nenhuma, se a rotina de prazos ganhou a corrida)
  E S-1 fica SELECIONADA, com exatamente 1 frete_selecionado na outbox e no tópico, e 1 entrega

# CA-65
Cenário: Cópia caindo no meio da viagem
  Dado o frete de P-1 escolhido pelo botão automático, o relógio com fator 3600 e a entrega EM_TRANSITO
  Quando os contêineres logistica-1 e transportadoras-1 são parados e o relógio vai a fator 20000
  Então a entrega chega a "ENTREGUE" em até 240 s
  E as sequências dos rastreios gravados vão de 1 a N, sem buraco, começando por VIAGEM_ALOCADA e COLETA_REALIZADA e terminando em ENTREGA_REALIZADA
  E entrega_concluida foi gravado exatamente uma vez na outbox (no tópico, ao menos uma vez)

# CA-66
Cenário: Redpanda fora do ar
  Dado S-1 COTADA e o contêiner redpanda parado
  Quando U-COMP faz a escolha do CA-21
  Então a resposta é 200
  Quando o redpanda volta
  Então em até 30 s há exatamente 1 mensagem em "frete_selecionado" para "PED-1001"

# CA-67
Cenário: Formato de erro
  Para cada resposta 4xx produzida pelos CAs de erro deste documento
  Então o Content-Type é application/problem+json e o corpo tem type, title, status (igual ao HTTP), detail, instance, correlationId, timestamp e codigo

# CA-68
Cenário: Correlação
  Quando a API-04 é chamada com X-Correlation-Id "qa-123"
  Então a resposta traz X-Correlation-Id "qa-123"
  Quando P-1 é consumido e o frete é escolhido
  Então solicitacao_frete_criada e frete_selecionado têm o correlationId do pedido_criado de P-1

# CA-69
Cenário: Chave de partição
  Depois do fluxo completo de P-1 (escolha, viagem e entrega) e de um ajuste de relógio
  Então solicitacao_frete_criada tem chave igual ao id de S-1; frete_selecionado e entrega_concluida têm chave "PED-1001"; relogio_ajustado tem chave "relogio"; e o aggregateId de cada envelope é igual à chave

# CA-70
Cenário: Conexões
  Durante o CA-63
  Então pg_stat_activity mostra no máximo 10 conexões do usuário svc_logistica

# CA-71
Cenário: Logs
  Ao ler o stdout de logistica-1 durante o CA-01
  Então cada linha é um objeto JSON com timestamp, level, service "logistica-service" e message
  E nenhum arquivo .py de services/logistica-service/logistica ou de comum/comum (fora de comum/comum/ferramentas) chama print()

# CA-72
Cenário: Dependências
  Ao inspecionar os imports dos arquivos .py de services/logistica-service/logistica e de comum/comum
  Então só há módulos da biblioteca padrão, das dependências do §5, de comum ou de logistica

# CA-82
Cenário: Carga de escrita
  Dado o relógio em fator 1 e nenhum pedido "ped-k6-" em aberto
  Quando o script testes_carga/escrita.js roda com TAXA=10 e DURACAO=60s
  Então os limiares p(95)<500 de escolher e criar_pedido, p(95)<20000 de pedido_ate_cotacoes, count==0 de solicitacoes_duplicadas e http_req_failed rate<0.01 passam
  E, ao fim, nenhum pedido "ped-k6-" tem solicitação aberta, entrega ativa ou viagem AGENDADA ou EM_TRANSITO
```

O pedido de teste é criado pelo `pedidos-falso` (`POST /api/v1/pedidos-falso/pedidos`, só admin), que publica `pedido_criado` no Kafka como o grupo de Pedidos faria (D23). Essa rota é uma ferramenta de desenvolvimento, não deste serviço, e fica fora da conformidade. Com a frota do seed (7 caminhões de granel), parte das escolhas fica sem caminhão livre; isso não é erro (RN-23 e RN-24) e aparece nos contadores `sem_frota` e `sem_cotacao`. Resultado em 10/11/2026, ambiente recém-criado: 601 pedidos, API-06 com p95 de 9,7 ms, do pedido às cotações com p95 de 511 ms, 0 duplicada, 0% de erros.

## 12. Matriz de rastreabilidade

| Requisito | Regras | Interfaces | Critérios de aceitação |
|---|---|---|---|
| RF-01 | RN-01 a RN-06, RN-30 | `pedido_criado`, `solicitacao_frete_criada`, `logistica.dlt` | CA-01 a CA-08 |
| RF-02 | RN-07 a RN-09 | `cotacao_recebida`, API-05 | CA-09 a CA-13 |
| RF-03 | RN-10 | Rotina de prazos | CA-14. Sem CA de erro: a rotina não recebe entrada do usuário |
| RF-04 | RN-11 | Rotina de prazos, `frete_indisponivel` | CA-15 |
| RF-05 | RN-19, RN-28 | API-04, API-05 | CA-16 a CA-20, CA-73 |
| RF-06 | RN-12, RN-14 a RN-17, RN-31 | API-06, `frete_selecionado` | CA-21 a CA-33 |
| RF-07 | RN-13 a RN-17 | API-06 | CA-34 a CA-36. Erros compartilhados com RF-06 (CA-26 a CA-32) |
| RF-08 | RN-13, RN-18 | Rotina de prazos, `frete_selecionado` | CA-37. Sem CA de erro: a rotina não recebe entrada; o conflito com o comprador está em CA-31 |
| RF-09 | RN-19, RN-26 | API-07 | CA-38 a CA-40 |
| RF-10 | RN-06, RN-20 | `pedido_atualizado` | CA-08, CA-41 a CA-43 |
| RF-11 | RN-21, RN-22, RN-25 | `rastreio_atualizado`, `entrega_concluida`, API-09, API-10 | CA-44 a CA-50 |
| RF-12 | RN-23, RN-24 | `rastreio_atualizado`, `frete_selecionado`, `frete_indisponivel`, API-08, API-11 | CA-51 a CA-53 |
| RF-13 | RN-19, RN-28, RN-29 | API-08 a API-11 | CA-54, CA-55 |
| RF-14 | RN-27 | API-12, API-13, `relogio_ajustado` | CA-56 a CA-59 |
| RF-15 | — | API-01 a API-03 | CA-60. Sem CA de erro: rotas públicas sem entrada |
| RF-16 | RN-30 | Todos os tópicos consumidos, `logistica.dlt` | CA-61, CA-62 (e CA-02, CA-04, CA-05, CA-11, CA-43, CA-50) |
| RF-17 | RN-28, RN-32 | API-17, API-18 (e as mudanças da RN-32) | CA-74 a CA-77 |
| RF-18 | RN-19, RN-32, RN-33 | API-14, API-15, API-10 | CA-78, CA-79 |
| RF-19 | RN-19, RN-34 | API-16 | CA-80, CA-81 |
| RNF-01 a RNF-10 | — | Todas | CA-63 a CA-72 |
| RNF-11 | — | API-04, API-06, API-11 | CA-82 |

Os CAs do token (CA-20) são cobertos pelos testes unitários de `comum/tests/test_auth.py`, porque o QA não tem a chave privada da Autenticação para gerar tokens expirados ou com escopo inválido. Os atributos internos (`rodada_ate`, `correlation_id`, `ultima_sequencia`) não aparecem na API; são verificados pelo comportamento (CA-14, CA-22, CA-46).

## 13. Premissas, decisões e questões em aberto

| ID | Tipo | Descrição | Decisão |
|---|---|---|---|
| Q-01 | Premissa | O serviço já está implementado (versão 0.1.0). Esta especificação descreve o comportamento implementado. | O QA verifica os CAs como caixa-preta no ambiente do `docker-compose.yml`, como os testes de `testes_integracao/`. Não há injeção de dublês: o barramento e o banco são os reais, e o relógio é controlado pela API-13. |
| Q-02 | Decisão (D18) | O relógio só acelera e adianta; não pode ser posto num instante exato nem voltar. | Os CAs com data usam T0 como referência. Num ambiente com outra hora, o QA confere as mesmas relações (RN-03, RN-04) a partir do `aberta_em` devolvido. |
| Q-03 | Decisão (D5) | Quem escolhe o frete. | O comprador, em até 12 h, ou o botão automático; depois, a regra do kit. **Depende do professor (P2).** Se mudar, mudam RF-06, RF-07 e RN-12. |
| Q-04 | Decisão (D12) | Tópicos `rastreio_atualizado`, `entrega_concluida`, `frete_indisponivel` e `relogio_ajustado` não existem no kit. | Usados como descritos. **Dependem da Infraestrutura (P3).** |
| Q-05 | Decisão (D25) | Token e perfil de administrador. | RS256 do Identity-Service, com `iss` e `aud` conferidos; admin = `platform_role` `PLATFORM_ADMIN` (o administrador global do Identity-Service) ou a permissão `logistica:admin`; `TENANT_ADMIN` sozinho não acessa. Confirmado no código e no seed do Identity-Service (10/11/2026). |
| Q-06 | Decisão | Escopo desta versão. | A v1.0 cobria o núcleo do fluxo do frete. Desde a v1.2, cobre também notificações (RF-17), ocorrências (RF-18) e documentos em PDF (RF-19): todas as rotas do serviço estão especificadas. |
| Q-07 | Decisão | `PRAZO_DE_ESCOLHA_ENCERRADO` só aparece no intervalo entre o vencimento e a próxima volta da rotina de prazos (até 1 s); depois, a resposta é `FRETE_JA_ESCOLHIDO`. | O CA-31 aceita os dois códigos e confere o resultado final. |
| Q-08 | Decisão | Corpo com JSON ilegível. | 422 `DADOS_INVALIDOS` antes da autenticação: o framework lê o corpo antes de resolver as dependências. |
| Q-09 | Decisão | Recurso de outra empresa. | 404, não 403, para não revelar que existe (RN-16, RN-19). |
| Q-10 | Decisão | Formato de datas nos eventos. | O JSON Schema não confere `format`. Data ilegível chega ao banco, que recusa; a mensagem vai para a DLT depois das 3 retentativas (CA-62). |
| Q-11 | Premissa (D2) | Campos do `pedido_criado`. | Os do §7.3, propostos ao grupo de Pedidos (`docs/contratos/proposta-grupo-pedidos.md`). **Dependem da resposta do grupo de Pedidos.** |
| Q-12 | Decisão | Hora real × hora do módulo. | Hora real só na rodada (RN-10), em `atualizado_em` e no `timestamp` do envelope. Todo o resto usa a hora do módulo. |

Q-03, Q-04, Q-05 e Q-11 têm decisão tomada e implementada; o que falta é a confirmação de outro grupo ou do professor. Se a confirmação vier diferente, esta especificação ganha uma nova versão.

### 13.1 Casos de borda obrigatórios

| Caso de borda | Decisão |
|---|---|
| String vazia ou só com espaços em campos obrigatórios | No evento, string vazia é inválida pelo contrato (`minLength` 1) e vai à DLT; string só com espaços passa no contrato (o nome de cidade só com espaços não é encontrado e vai à DLT pela RN-01). Na API-06, `Idempotency-Key` só com espaços equivale a ausente (400). Na API-15, `descricao` só com espaços tem tamanho 0 depois de tirar as pontas → 422. |
| Cabeçalho opcional presente porém vazio | `X-Correlation-Id` vazio equivale a ausente (o serviço gera um). |
| Mensagem duplicada **e** inválida | Envelope ilegível ou incompleto: cada cópia vai à DLT. Payload inválido com envelope completo: a primeira vai à DLT e marca o `eventId`; as cópias são ignoradas. |
| Campo de chave/ID com tipo inesperado | No evento, `pedidoId` ou `solicitacaoFreteId` numérico é inválido pelo contrato → DLT. Na rota, o id é sempre texto; id inexistente → 404. |
| `cotacaoId` repetido em outra solicitação | O banco recusa (`id` único); a mensagem vai à DLT depois das 3 retentativas. O `transportadoras-service` gera ids únicos por (solicitação, transportadora). |
| Data/hora sem fuso horário | Nos eventos, o banco interpreta como UTC. A API desta especificação não recebe data/hora. |
| Falha da porta de publicação / banco | Kafka fora: o evento espera na outbox (RNF-04). Banco fora: a API responde 500 `ERRO_INTERNO` depois de até 30 s; o consumidor espera e não confirma o offset. |
| Rotas e métodos fora do contrato | 404 `NAO_ENCONTRADO` e 405 `METODO_NAO_PERMITIDO`, em RFC 7807 (§10). |
| Rastreio com `sequencia` igual à última, mas conteúdo diferente | Ignorado (RN-21). |
| Entrega atrasada por menos de 3 minutos | `noPrazo` false e `atrasoHoras` 0.0 (arredondamento a 1 casa). O serviço copia os dois valores do rastreio. |
| `eventType` diferente do tópico | Ignorado: vale o tópico. |

## 14. Checklist de prontidão (Definition of Ready) — preenchido pelo QA

- [ ] Nenhum `{{ }}` restante; comentários de orientação removidos.
- [ ] Todo RF tem enunciado EARS, prioridade e CAs de sucesso e erro quando aplicáveis; exceções justificadas na matriz.
- [ ] Todo CA usa valores concretos e resultado observável.
- [ ] Todo código de erro citado em CA existe no §10 e vice-versa.
- [ ] Ordem de verificação de erros definida para cada endpoint.
- [ ] Campos de entidade, projeções de resposta e campos derivados estão mapeados; exemplos JSON respeitam os contratos.
- [ ] Todo tópico citado tem produtor/consumidor, chave e exemplo.
- [ ] Toda dependência externa está modelada como porta (§5.1).
- [ ] Todo RNF tem métrica, limiar e forma de verificação.
- [ ] Matriz de rastreabilidade completa (nenhum RF sem CA, nenhum CA órfão).
- [ ] Não há palavras vagas sem quantificação ("rápido", "adequado", "etc.", "deve tratar erros").
- [ ] Seção 13 sem questões abertas e tabela 13.1 (casos de borda) toda decidida.
- [ ] Comentários `# DECISÃO:` da última geração (se houver) analisados e incorporados como regra.

## 15. Histórico de versões

| Versão | Data | Autor | Mudança |
|---|---|---|---|
| 1.2 | 2026-11-10 | Grupo 5 | Todas as rotas do serviço especificadas: ocorrências (API-14, API-15, RF-18, RN-33), documentos em PDF (API-16, RF-19, RN-34) e notificações (API-17, API-18, RF-17, RN-32), com 3 códigos de erro novos (§10). Filtro `pedido_id` na API-04 (CA-73) e teste de carga de escrita (RNF-11, CA-82). Exemplos tirados de respostas reais do ambiente. Ao escrever, um defeito foi corrigido: uma ocorrência só com espaços (`"     "`) passava no mínimo de 5 caracteres e era gravada vazia; agora os espaços das pontas saem antes de contar (CA-79). CA-01 a CA-72 sem mudança. |
| 1.1 | 2026-11-10 | Grupo 5 | Token conforme o código do Identity-Service: `iss` e `aud` conferidos (antes, todo token real seria recusado, porque o PyJWT recusa `aud` não esperado), admin pelo `platform_role` `PLATFORM_ADMIN` e 403 `CONTEXTO_NAO_SELECIONADO` para token sem empresa ou escopo (§7.1, §10, CA-20, Q-05). |
| 1.0 | 2026-11-10 | Grupo 5 | Criação, a partir do serviço implementado (etapas 1 a 5) e de respostas reais capturadas no ambiente. Ao escrever as duas especificações, quatro defeitos foram corrigidos no código (explicação 07). Os que afetam este documento: `VIAGEM_ALOCADA` sem `posicao` passava no contrato (agora vai direto à DLT, CA-50) e fator do relógio com mais de 2 casas respondia 500 ou era gravado diferente do publicado (agora 422, CA-59). Os outros dois estão na ESP-TRP-001. |

## Apêndice A — Tabela de cidades

Coordenadas aproximadas do centro da cidade, usadas só na simulação (D15).

| Cidade | UF | lat | lon |
|---|---|---|---|
| Sorriso | MT | -12.5453 | -55.7114 |
| Sinop | MT | -11.8642 | -55.5093 |
| Lucas do Rio Verde | MT | -13.0588 | -55.9042 |
| Rondonópolis | MT | -16.4673 | -54.6372 |
| Cuiabá | MT | -15.6014 | -56.0979 |
| Primavera do Leste | MT | -15.5600 | -54.2811 |
| Sapezal | MT | -13.5428 | -58.8146 |
| Campo Novo do Parecis | MT | -13.6587 | -57.8907 |
| Rio Verde | GO | -17.7923 | -50.9192 |
| Goiânia | GO | -16.6869 | -49.2648 |
| Jataí | GO | -17.8784 | -51.7204 |
| Campo Grande | MS | -20.4697 | -54.6201 |
| Dourados | MS | -22.2231 | -54.8120 |
| Maracaju | MS | -21.6105 | -55.1678 |
| Uberlândia | MG | -18.9128 | -48.2755 |
| Uberaba | MG | -19.7472 | -47.9381 |
| Belo Horizonte | MG | -19.9167 | -43.9345 |
| Paranaguá | PR | -25.5205 | -48.5095 |
| Cascavel | PR | -24.9578 | -53.4596 |
| Londrina | PR | -23.3045 | -51.1696 |
| Curitiba | PR | -25.4284 | -49.2733 |
| Ponta Grossa | PR | -25.0950 | -50.1619 |
| Santos | SP | -23.9608 | -46.3336 |
| São Paulo | SP | -23.5505 | -46.6333 |
| Campinas | SP | -22.9099 | -47.0626 |
| Ribeirão Preto | SP | -21.1704 | -47.8103 |
| Luís Eduardo Magalhães | BA | -12.0960 | -45.7866 |
| Salvador | BA | -12.9777 | -38.5016 |
| Balsas | MA | -7.5325 | -46.0356 |
| São Luís | MA | -2.5307 | -44.3068 |
| Recife | PE | -8.0476 | -34.8770 |
| Porto Alegre | RS | -30.0346 | -51.2177 |
| Rio Grande | RS | -32.0350 | -52.0986 |
| Itajaí | SC | -26.9078 | -48.6619 |
| Rio de Janeiro | RJ | -22.9068 | -43.1729 |
