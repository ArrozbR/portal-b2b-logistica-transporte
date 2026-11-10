# ESP-TRP-001 — Especificação de Requisitos: Transportadoras (`transportadoras-service`)

## 0. Metadados

| Campo | Valor |
|---|---|
| Identificador | ESP-TRP-001 |
| Versão | 1.0 |
| Status | Em revisão (aguarda o gate G1 do grupo de Teste e Qualidade) |
| Serviço / Bounded context | `transportadoras-service`: transportadoras homologadas, frota, cotação, escala e viagem simulada. Grupo 5 (Logística e Transporte) do Portal B2B Distribuído |
| Autores (PO / Dev / QA) | Grupo 5 — Logística e Transporte (PO e Dev). Revisão de QA: grupo de Teste e Qualidade |
| Data | 2026-11-10 |
| Documentos relacionados | ESP-LOG-001 (`logistica-service`); `docs/02-arquitetura-proposta.md`; `docs/03-eventos-e-integracoes.md`; `docs/06-pauta-de-decisoes.md` (D1 a D25); `docs/07-relatorio-tecnico.md`; JSON Schemas em `comum/comum/contratos/` |

## 1. Diretivas para a LLM geradora

1. Implemente **exatamente** o que está especificado. Não adicione endpoints, campos, tópicos, perfis ou regras que não estejam neste documento.
2. **Ordem de precedência** quando houver conflito aparente: Catálogo de erros (§10) e Contratos (§7) > Critérios de aceitação (§8) > Regras de negócio (§9) > Requisitos funcionais (§8) > texto descritivo.
3. Nomes de campos, tópicos, códigos de erro, rotas e valores de enumeração são **literais**: use-os byte a byte, com a mesma grafia e caixa.
4. Quando algo não estiver definido, escolha o comportamento mais simples que **não viole** nenhum item deste documento e registre a decisão em um comentário `# DECISÃO:` no código.
5. Entregue código completo e executável. Proibido: `TODO`, `pass` como implementação, pseudocódigo, trechos omitidos ("...").
6. Grave os arquivos completos na estrutura do §5 (pacote `transportadoras/` e, quando reaproveitar peças comuns, pacote `comum/`). Na resposta final, liste seus caminhos relativos.

## 2. Contexto

### 2.1 Objetivo do serviço

Manter as transportadoras homologadas e a frota delas (motoristas e veículos), cotar as solicitações de frete, escalar motorista e veículo quando a transportadora é escolhida e simular a viagem, publicando o rastreio que a logística mostra no mapa.

### 2.2 Posição na arquitetura

O `logistica-service` (ESP-LOG-001) publica `solicitacao_frete_criada`. Cada transportadora simulada compatível, com frota livre, responde com `cotacao_recebida`. Transportadoras não simuladas cotam pela API REST (cotação digitada). Quando a logística publica `frete_selecionado`, este serviço sorteia motorista e veículo livres da transportadora escolhida e publica `rastreio_atualizado` (`VIAGEM_ALOCADA` ou `VIAGEM_RECUSADA`). Durante a viagem, publica os rastreios de coleta, posição, parada, atraso e entrega. `pedido_atualizado` com `CANCELADO`, do grupo de Pedidos, cancela a viagem e libera a frota. `relogio_ajustado`, da logística, mantém o relógio do módulo igual nos dois serviços.

```text
Logística ───────[solicitacao_frete_criada]──►┐
Logística ───────[frete_selecionado]─────────►│
Logística ───────[relogio_ajustado]──────────►│
Pedidos ─────────[pedido_atualizado]─────────►│
Telas ─► gateway ─REST /api/v1/transportadoras►│ transportadoras-service
                                               ├──[cotacao_recebida]─────► Logística
                                               ├──[rastreio_atualizado]──► Logística
                                               └──[transportadoras.dlt]──► operação
```

## 3. Escopo

### 3.1 Dentro do escopo

- Consulta das transportadoras homologadas, da transportadora da empresa do usuário e do ranking de desempenho.
- Cotação automática das transportadoras simuladas, com o motor de cotação (D7), só para quem tem frota livre compatível (D20).
- Lista de cargas para a transportadora e cotação digitada (D3).
- Cadastro, alteração e desativação de motoristas e veículos (D19).
- Escala: sorteio reproduzível de motorista e veículo compatíveis, reserva sem disputa entre as cópias e recusa quando falta frota (D19, D20).
- Simulação da viagem: coleta, posição a cada passo, parada para descanso, atraso revelado no caminho e entrega (D8 a D10).
- Cancelamento da viagem e liberação da frota.
- Cópia do relógio do módulo a partir de `relogio_ajustado` (D18).
- Saúde (`/health`, `/health/ready`) e métricas (`/metrics`).

### 3.2 Fora do escopo (não implementar)

- Cadastro, edição, homologação e desativação de transportadoras e das regras de cotação (vêm só dos seeds; Apêndice A).
- Reativação ou remoção física de motorista e veículo (a desativação é definitiva nesta versão).
- Escolha do frete, comparação e notificações (ESP-LOG-001).
- GPS real, rota por estrada, feriados, tráfego.
- Telas (HTML, JavaScript, mapa); login e emissão de token (grupo de Autenticação).
- Leitura ou escrita no schema de outro serviço. Chamada HTTP a outro serviço para avançar o fluxo.
- Rota para zerar o estado. O ambiente de teste é recriado com `docker compose down -v` e `docker compose up -d --build`.

## 4. Glossário

| Termo | Definição precisa |
|---|---|
| Transportadora | Empresa homologada, identificada por `id` (ex.: `"transp-economica"`), ligada a uma empresa do portal por `empresa_id`. |
| Transportadora simulada | `simulada` = true: cota sozinha. Não simulada (`transp-rodovia`): só cota pela API (cotação digitada). As duas têm viagem simulada. |
| Atende a carga | `tipo_carga` ∈ `tipos_carga` da transportadora **e** (`ufs_atendidas` é `null` **ou** a UF de origem e a de destino estão em `ufs_atendidas`). |
| Categoria da CNH | Ordem A < B < C < D < E. O motorista pode dirigir o veículo se a categoria dele for maior ou igual à `categoria_cnh_exigida` do veículo. |
| Motorista livre | `ativo` = true, sem viagem em andamento e `cnh_validade` ≥ data UTC da hora do módulo. |
| Veículo livre compatível | `ativo` = true, sem viagem em andamento, `tipo_carga` ∈ `tipos_carga` do veículo e `capacidade_kg` ≥ `peso_kg` da carga. |
| Frota livre compatível | Existe um veículo livre compatível e um motorista livre da mesma transportadora que pode dirigi-lo. |
| Preço da cotação | `max(preco_minimo; (tarifa_km × distancia_km + tarifa_ton × peso_kg ÷ 1000) × fator_tipo_carga)`, arredondado ao centavo, meio para cima. `fator_tipo_carga` ausente para o tipo = 1. Cálculo com `Decimal`. |
| Prazo da cotação | `prazo_base_dias + teto(distancia_km ÷ km_por_dia)`, em dias úteis. |
| Data de entrega prevista | Data de coleta + prazo, contando só dias úteis. |
| Dias úteis entre C e E | Quantidade de dias úteis depois de C até E, inclusive. `2026-11-11` (quarta) → `2026-11-17` (terça) = 4. |
| `cotacaoId` | `UUID5(6f1d2c3e-4b5a-4c7d-9e8f-0a1b2c3d4e5f, "<solicitacaoFreteId>:<transportadoraId>")`, igual para a cotação automática e a digitada. |
| Hora do módulo / agora | Cópia local do relógio da logística (§5.1). Sem estado gravado, é a hora real. |
| Horário de Brasília | UTC−3, sem horário de verão. |
| Instante, Data, Valor monetário, Dia útil, Distância | Como na ESP-LOG-001 (§4). |
| Semente | O `entregaId` do `frete_selecionado`. Todo sorteio da viagem usa `random.Random(semente)`, então a mesma entrega gera sempre o mesmo resultado. |
| Plano da viagem | Coleta = hora do módulo da escala + 2 h. Chegada planejada = o maior entre 14:00 (Brasília) da data prometida e coleta + `distancia_km ÷ (km_por_dia ÷ 24)` horas; sem data prometida, só o segundo. |
| Atraso sorteado | Com a semente: se `random()` < `prob_atraso` da transportadora, o atraso é `arredondar(uniform(4; 36); 1)` horas; senão, 0. |
| Progresso | Fração do caminho (0 a 1), em linha reta do último marco (coleta, ou o ponto em que o atraso apareceu) até a chegada prevista: `marco_progresso + (1 − marco_progresso) × (agora − marco_tempo) ÷ (chegada − marco_tempo)`, 4 casas. Nunca diminui. |
| Limite do prazo | 00:00 (Brasília) do dia seguinte à data prometida. Entregue até o limite, inclusive: no prazo. Depois: `atrasoHoras` = `arredondar((entregue − limite) em horas; 1)`. |
| Local | Cidade mais próxima da tabela (ESP-LOG-001, Apêndice A) a até 150 km: `"<Cidade> - <UF>"`; mais longe: `"na rodovia"`. |
| CNH mascarada | `"*"` repetido (dígitos − 4) vezes + os 4 últimos dígitos: `"06678901243"` → `"*******1243"`. |
| Passo da viagem | Avanço de uma viagem, feito pela rotina de viagens quando a hora **real** alcança o `proximo_passo_em` dela; o próximo passo é marcado para `RASTREIO_INTERVALO_SEGUNDOS` (30 s) reais depois. |
| Dono da frota | Usuário com perfil `transportadora` cuja empresa é o `empresa_id` da transportadora, ou um `admin`. |

## 5. Restrições técnicas

| Item | Valor obrigatório |
|---|---|
| Linguagem / versão | Python 3.12 |
| Framework | FastAPI com Pydantic v2 |
| Dependências permitidas | As da ESP-LOG-001 (§5), sem `fpdf2`. Nenhuma outra. |
| Persistência | PostgreSQL, schema `transportadoras`, usuário `svc_transportadoras`, pool de no máximo 5 conexões por instância. Nenhum estado de negócio só em memória. |
| Instâncias | Duas cópias iguais (`transportadoras-1` na porta 8109 e `transportadoras-2` na 8119), com o mesmo banco. |
| Estrutura de arquivos | `services/transportadoras-service/transportadoras/`: `__init__.py` (`SERVICO`, `SCHEMA`, `TOPICO_DLT`), `main.py`, `api.py`, `servico.py`, `cotacao.py` (motor de cotação, puro), `simulacao.py` (plano e passo da viagem, puros). DDL e seeds em `services/transportadoras-service/migracoes/NNN_*.sql`. |
| Ponto de entrada | `uvicorn transportadoras.main:app --host 0.0.0.0 --port 8109`. O `lifespan` abre o pool e inicia três rotinas: consumidor, publicador da outbox e viagens (a cada 1 s). |
| Configuração | As da ESP-LOG-001 (`DB_*`, `KAFKA_BOOTSTRAP_SERVERS`, `JWT_ALGORITHM`, `AUTH_JWKS_URL`, `JWT_SECRET_KEY`, `LOG_LEVEL`) e `RASTREIO_INTERVALO_SEGUNDOS` (30). |
| Formato de data/hora | Instante e Data. Na cotação digitada, `validaAte` sem fuso é lido no horário de Brasília. |
| Formato monetário | Valor monetário. |
| Logs | JSON no stdout, como na ESP-LOG-001. Proibido `print()`. |

### 5.1 Portas (interfaces de infraestrutura)

As mesmas da ESP-LOG-001 (§5.1): `gravar_evento` (outbox), tratador de consumo com `EventoInvalido`, `Relogio.agora(conn)` e `BancoDeDados.transacao()`.

Comportamento das portas:

- **Publicação** pela outbox, na mesma transação, como na ESP-LOG-001. Ordem de uma escrita: validar → alterar o estado → gravar o evento → commit.
- **Consumo.** Grupo `transportadoras-service`, tópicos `solicitacao_frete_criada`, `frete_selecionado`, `pedido_atualizado` e `relogio_ajustado`. Idempotência, retentativas e DLT `transportadoras.dlt` como na RN-30 da ESP-LOG-001.
- **Relógio.** Tabela `transportadoras.relogio` (mesma forma da logística). Só o consumo de `relogio_ajustado` grava nela, e só se a `versao` recebida for maior que a gravada. Cada `agora` lê o banco.
- **Hora real** só no agendamento técnico do passo da viagem (`proximo_passo_em`) e no `timestamp` do envelope.
- **Reserva de frota.** Motorista e veículo ganham `viagem_atual_id` por gravação condicional (`UPDATE ... WHERE viagem_atual_id IS NULL` e conferência de 1 linha alterada). Duas escalas nas duas cópias nunca pegam o mesmo motorista ou veículo.

## 6. Modelo de domínio

### 6.1 Entidades

Os nomes abaixo são os da resposta da API (§7.2).

#### Transportadora (com a regra de cotação)

| Atributo | Tipo | Obrigatório | Restrições / origem |
|---|---|---|---|
| id | string | Sim | Seed. |
| nome | string | Sim | Seed. |
| telefone_contato | string ou `null` | Não | Seed. |
| ativa | booleano | Sim | Seed. Inativa não cota nem aparece no ranking. |
| simulada | booleano | Sim | Seed. |
| tipos_carga | lista de enum | Sim | Seed; valores `GRANEL`, `REFRIGERADO`, `CARGA_SECA`, `PERIGOSO`. |
| ufs_atendidas | lista de UF ou `null` | Não | Seed; `null` = todo o país. |
| preco_minimo, tarifa_km, tarifa_ton | valor monetário | Sim | Seed (regra de cotação). |
| km_por_dia | inteiro | Sim | Seed; > 0. |
| prazo_base_dias | inteiro | Sim | Seed; ≥ 0. |

Internos (não aparecem na API): `empresa_id`, `prob_atraso` (0 a 1), `fator_tipo_carga` (mapa tipo → fator).

#### Motorista

| Atributo | Tipo | Obrigatório | Restrições / origem |
|---|---|---|---|
| id | string | Sim | `"mot-"` + 10 dígitos hexadecimais, gerado no cadastro. |
| nome | string | Sim | 3 a 200 caracteres. |
| telefone | string ou `null` | Não | Até 30 caracteres. |
| cnh_numero | string | Sim | `^\d{11}$`. Única por transportadora (inclui desativados). |
| cnh_categoria | enum | Sim | `B`, `C`, `D` ou `E`. |
| cnh_validade | data | Sim | Qualquer data; vencida impede a escala. |
| ativo | booleano | Sim | Inicial `true`. |
| em_viagem | booleano | Sim | Derivado: tem viagem em andamento. |

#### Veiculo

| Atributo | Tipo | Obrigatório | Restrições / origem |
|---|---|---|---|
| id | string | Sim | `"vei-"` + 10 dígitos hexadecimais. |
| placa | string | Sim | `^[A-Z]{3}\d[A-Z0-9]\d{2}$` (Mercosul ou antiga, sem traço). Única no serviço (inclui desativados e outras transportadoras). |
| tipo | string | Sim | 2 a 30 caracteres (ex.: `"CARRETA_GRANELEIRA"`). |
| capacidade_kg | número | Sim | > 0 e ≤ 80000. |
| tipos_carga | lista de enum | Sim | Ao menos 1. |
| categoria_cnh_exigida | enum | Sim | `B`, `C`, `D` ou `E`; padrão `E`. |
| ativo, em_viagem | booleano | Sim | Como no motorista. |

#### SolicitacaoRecebida

Cópia de `solicitacao_frete_criada`: `id` (= `solicitacaoFreteId`), `pedido_id`, `produto_nome`, `tipo_carga`, `peso_kg`, `origem_cidade`, `origem_uf`, `origem_lat`, `origem_lon`, `destino_*`, `distancia_km`, `data_coleta_prevista`, `prazo_decisao_em`. Mais: `status` (`"ABERTA"` ou `"ENCERRADA"`), `cancelada` (booleano), `transportadora_vencedora_id` (string ou `null`).

#### CotacaoEmitida

`id` (`cotacaoId`), `solicitacao_id`, `transportadora_id`, `preco`, `prazo_dias`, `data_entrega_prevista`, `valida_ate`, `origem_cotacao` (`"SIMULADA"` ou `"DIGITADA"`), `observacoes`, `usuario_id` (quem digitou), `emitida_em` (hora do módulo). Única por (solicitação, transportadora).

#### Viagem

`id` (UUID4), `entrega_id` (único), `pedido_id`, `solicitacao_id`, `transportadora_id`, `motorista_id`, `veiculo_id`, `rota` (60 pontos), `data_prometida`, `coleta_em`, `chegada_prevista`, `atraso_horas` (sorteado), `atraso_revelado`, `parada_publicada`, `marco_tempo`, `marco_progresso`, `progresso`, `sequencia` (último rastreio publicado), `status`, `proximo_passo_em` (hora real), `entregue_em`, `no_prazo`, `atraso_real_horas`. Não aparece na API; é observada pelos rastreios.

### 6.2 Estados e transições

**Solicitação recebida**

| Estado atual | Evento | Condição | Próximo estado |
|---|---|---|---|
| (inexistente) | `solicitacao_frete_criada` válida | `id` ainda não recebido | ABERTA |
| ABERTA, ENCERRADA | `frete_selecionado` | — | ENCERRADA, com `transportadora_vencedora_id` |
| ABERTA, ENCERRADA | `pedido_atualizado` CANCELADO | — | ENCERRADA, com `cancelada` = true |

**Viagem**

| Estado atual | Evento / passo | Condição | Próximo estado |
|---|---|---|---|
| (inexistente) | `frete_selecionado` da transportadora | Frota livre reservada | AGENDADA (publica `VIAGEM_ALOCADA`) |
| AGENDADA | Passo | `agora ≥ coleta_em` | EM_TRANSITO (publica `COLETA_REALIZADA`) |
| AGENDADA | Passo | `agora < coleta_em` | AGENDADA (nada publicado) |
| EM_TRANSITO | Passo | Progresso < 1 | EM_TRANSITO (publica `PARADA` e `PREVISAO_ATUALIZADA` quando for a hora, e `POSICAO`) |
| EM_TRANSITO | Passo | Progresso ≥ 1 | ENTREGUE (publica `ENTREGA_REALIZADA`; libera a frota) |
| AGENDADA, EM_TRANSITO | `pedido_atualizado` CANCELADO | — | CANCELADA (libera a frota; nada publicado) |

ENTREGUE e CANCELADA são finais. Sem frota livre na escala, não há viagem: publica `VIAGEM_RECUSADA`.

**Motorista e veículo:** ativo ↔ em viagem (reserva na escala; liberação na entrega ou no cancelamento); ativo → inativo (API-13 ou API-17, só fora de viagem). Inativo é final.

## 7. Contratos de interface

### 7.1 Autenticação e contexto da requisição

Igual à ESP-LOG-001 (§7.1): token RS256 da Autenticação pelo JWKS, a mesma tradução de perfis, a mesma ordem de verificação e os mesmos códigos (`NAO_AUTENTICADO`, `TOKEN_INVALIDO`, `TOKEN_EXPIRADO`, `AUTENTICACAO_INDISPONIVEL`, `PERFIL_NAO_PERMITIDO`, `PERFIL_AUSENTE`), e o mesmo tratamento de `X-Correlation-Id`. Rotas públicas: `/health`, `/health/ready`, `/metrics`, `/docs` e `/openapi.json`.

A transportadora do usuário é a que tem `empresa_id` igual ao `tenant_id` do token.

### 7.2 API REST

Prefixo: `/api/v1/transportadoras`. Campos em `snake_case`, exceto a resposta da cotação digitada e os eventos (`camelCase`). Paginação como na ESP-LOG-001: `page` ≥ 1 (padrão 1), `size` de 1 a 100 (padrão 10), corpo `{"items": [...], "page", "size", "total"}`.

As rotas `/minha`, `/ranking` e `/solicitacoes` têm precedência sobre `/{transportadora_id}`.

| ID | Método | Rota | Perfis | Sucesso | Erros possíveis (na ordem de verificação) |
|---|---|---|---|---|---|
| API-01 | GET | `/health` | público | 200 | — |
| API-02 | GET | `/health/ready` | público | 200 | 503 (corpo próprio) |
| API-03 | GET | `/metrics` | público | 200 | — |
| API-04 | GET | `/api/v1/transportadoras` | todos os 4 | 200 | 401/503 (§7.1) → 403 → 422 |
| API-05 | GET | `/api/v1/transportadoras/minha` | transportadora | 200 | 401/503 → 403 → 404 `SEM_TRANSPORTADORA` |
| API-06 | GET | `/api/v1/transportadoras/ranking` | todos os 4 | 200 | 401/503 → 403 → 422 |
| API-07 | GET | `/api/v1/transportadoras/solicitacoes` | transportadora | 200 | 401/503 → 403 `PERFIL_NAO_PERMITIDO` → 422 → 403 `SEM_TRANSPORTADORA` |
| API-08 | POST | `/api/v1/transportadoras/solicitacoes/{solicitacao_id}/cotacoes` | transportadora | 201 | 422 (JSON ilegível) → 401/503 → 403 `PERFIL_NAO_PERMITIDO` → 422 `DADOS_INVALIDOS` → 403 `SEM_TRANSPORTADORA` → 404 `SOLICITACAO_NAO_ENCONTRADA` → 403 `CARGA_INCOMPATIVEL` → 409 `SOLICITACAO_ENCERRADA` → 409 `COTACAO_JA_ENVIADA` → 422 `PRAZO_INVALIDO` → 422 `VALIDADE_INVALIDA` → 422 `SEM_FROTA_LIVRE` |
| API-09 | GET | `/api/v1/transportadoras/{transportadora_id}` | todos os 4 | 200 | 401/503 → 403 → 404 `TRANSPORTADORA_NAO_ENCONTRADA` |
| API-10 | GET | `/api/v1/transportadoras/{transportadora_id}/motoristas` | transportadora, admin | 200 | 401/503 → 403 `PERFIL_NAO_PERMITIDO` → 422 → 404 `TRANSPORTADORA_NAO_ENCONTRADA` → 403 `OUTRA_TRANSPORTADORA` |
| API-11 | POST | `/api/v1/transportadoras/{transportadora_id}/motoristas` | transportadora, admin | 201 | 422 (JSON) → 401/503 → 403 → 422 → 404 `TRANSPORTADORA_NAO_ENCONTRADA` → 403 `OUTRA_TRANSPORTADORA` → 409 `MOTORISTA_DUPLICADO` |
| API-12 | PUT | `/api/v1/transportadoras/{transportadora_id}/motoristas/{motorista_id}` | transportadora, admin | 200 | 422 (JSON) → 401/503 → 403 → 422 → 404 `TRANSPORTADORA_NAO_ENCONTRADA` → 403 `OUTRA_TRANSPORTADORA` → 404 `MOTORISTA_NAO_ENCONTRADO` → 409 `MOTORISTA_DUPLICADO` |
| API-13 | DELETE | `/api/v1/transportadoras/{transportadora_id}/motoristas/{motorista_id}` | transportadora, admin | 200 | 401/503 → 403 → 404 `TRANSPORTADORA_NAO_ENCONTRADA` → 403 `OUTRA_TRANSPORTADORA` → 404 `MOTORISTA_NAO_ENCONTRADO` → 409 `MOTORISTA_EM_VIAGEM` |
| API-14 | GET | `/api/v1/transportadoras/{transportadora_id}/veiculos` | transportadora, admin | 200 | Como a API-10 |
| API-15 | POST | `/api/v1/transportadoras/{transportadora_id}/veiculos` | transportadora, admin | 201 | Como a API-11, com 409 `PLACA_DUPLICADA` |
| API-16 | PUT | `/api/v1/transportadoras/{transportadora_id}/veiculos/{veiculo_id}` | transportadora, admin | 200 | Como a API-12, com 404 `VEICULO_NAO_ENCONTRADO` e 409 `PLACA_DUPLICADA` |
| API-17 | DELETE | `/api/v1/transportadoras/{transportadora_id}/veiculos/{veiculo_id}` | transportadora, admin | 200 | Como a API-13, com 404 `VEICULO_NAO_ENCONTRADO` e 409 `VEICULO_EM_VIAGEM` |

#### API-01 a API-03 — Saúde, prontidão e métricas

Como na ESP-LOG-001, com `"service": "transportadoras-service"`.

#### API-04 — Listar transportadoras

Todas as transportadoras (ativas e inativas), por `nome` crescente. `total` conta todas.

```json
{
  "items": [
    {
      "id": "transp-economica",
      "nome": "Econômica Transportes",
      "telefone_contato": "(11) 4000-1002",
      "ativa": true,
      "simulada": true,
      "tipos_carga": ["CARGA_SECA", "GRANEL"],
      "ufs_atendidas": null,
      "preco_minimo": 900.0,
      "tarifa_km": 2.6,
      "tarifa_ton": 30.0,
      "km_por_dia": 400,
      "prazo_base_dias": 2
    }
  ],
  "page": 1, "size": 10, "total": 6
}
```

#### API-05 — Minha transportadora

Mesmo objeto de um item da API-04, da transportadora da empresa do usuário. Exemplo para `emp-transp-rodovia`: `{"id": "transp-rodovia", "nome": "Rodovia Sul Transportes", "telefone_contato": "(41) 4000-1006", "ativa": true, "simulada": false, "tipos_carga": ["GRANEL", "CARGA_SECA"], "ufs_atendidas": null, "preco_minimo": 1000.0, "tarifa_km": 3.2, "tarifa_ton": 40.0, "km_por_dia": 600, "prazo_base_dias": 1}`.

#### API-06 — Ranking

Parâmetros: `tipoCarga` (opcional, um dos 4 tipos), `page`, `size`. Só transportadoras ativas; `total` conta as ativas.

```json
{
  "items": [
    {
      "id": "transp-graneleira",
      "nome": "Graneleira Centro-Oeste",
      "simulada": true,
      "tipos_carga": ["GRANEL"],
      "entregas": 6,
      "no_prazo": 6,
      "atraso_medio_horas": 0.0,
      "vezes_escolhida": 7,
      "cotacoes": 34,
      "preco_medio_t_km": 0.1416,
      "posicao": 1,
      "pct_no_prazo": 1.0
    }
  ],
  "page": 1, "size": 10, "total": 6
}
```
Campos derivados (RN-17): `entregas`, `no_prazo`, `atraso_medio_horas`, `vezes_escolhida`, `cotacoes`, `preco_medio_t_km`, `pct_no_prazo` e `posicao`.

#### API-07 — Cargas para a transportadora

Parâmetros: `todas` (booleano, padrão `false`), `page`, `size`. Resposta: a paginação mais `horaDoModulo`.

```json
{
  "items": [
    {
      "id": "8a2d6f14-5c3b-4e7a-b9d0-3e1f7c5a9b28",
      "pedido_id": "PED-1002",
      "produto_nome": "Fertilizante ensacado",
      "tipo_carga": "CARGA_SECA",
      "peso_kg": 20000.0,
      "origem_cidade": "Rio Verde", "origem_uf": "GO",
      "destino_cidade": "Paranaguá", "destino_uf": "PR",
      "distancia_km": 1163.0,
      "data_coleta_prevista": "2026-11-11",
      "prazo_decisao_em": "2026-11-11T00:00:00.000Z",
      "status": "ABERTA",
      "cancelada": false,
      "transportadora_vencedora_id": null,
      "minha_cotacao_id": null,
      "minha_cotacao_preco": null,
      "minha_cotacao_prazo": null,
      "minha_cotacao_entrega": null,
      "minha_cotacao_origem": null,
      "minha_cotacao_emitida_em": null,
      "situacao": "ACEITANDO_COTACOES",
      "pode_cotar": true
    }
  ],
  "page": 1, "size": 10, "total": 1,
  "horaDoModulo": "2026-11-10T12:01:00.000Z"
}
```
Filtro, ordem e `situacao` na RN-15 e na RN-16.

#### API-08 — Cotação digitada

Requisição:
```json
{"valor": 5800.00, "dataEntregaPrevista": "2026-11-17", "validaAte": "2026-11-10T18:00:00Z", "observacoes": "Coleta pela manhã"}
```
- `valor`: número > 0 e ≤ 10000000 (R$). `dataEntregaPrevista`: data. `validaAte`: instante (sem fuso = Brasília). `observacoes`: opcional, até 500 caracteres; vazio vira `null`.

Resposta 201:
```json
{
  "cotacaoId": "4ec74218-2a41-5ef2-8032-cb8c1dc41e28",
  "solicitacaoFreteId": "8a2d6f14-5c3b-4e7a-b9d0-3e1f7c5a9b28",
  "transportadoraId": "transp-rodovia",
  "preco": 5800.0,
  "prazoDias": 4,
  "dataEntregaPrevista": "2026-11-17",
  "validaAte": "2026-11-10T18:00:00.000Z",
  "origemCotacao": "DIGITADA",
  "observacoes": "Coleta pela manhã"
}
```

#### API-09 — Detalhe da transportadora

Mesmo objeto de um item da API-04.

#### API-10 e API-14 — Listar motoristas e veículos

Todos os da transportadora (ativos e inativos), motoristas por `nome` e veículos por `placa`, crescentes. Itens como as respostas da API-11 e da API-15.

#### API-11 e API-12 — Cadastrar e alterar motorista

Requisição (igual nas duas):
```json
{"nome": "Teste ESP", "telefone": "(41) 90000-0000", "cnhNumero": "99999999999", "cnhCategoria": "E", "cnhValidade": "2030-01-31"}
```
Resposta (201 no cadastro, 200 na alteração):
```json
{"id": "mot-8cd7aab104", "nome": "Teste ESP", "telefone": "(41) 90000-0000", "cnh_numero": "99999999999",
 "cnh_categoria": "E", "cnh_validade": "2030-01-31", "ativo": true, "em_viagem": false}
```
A alteração troca todos os campos do corpo e não muda `ativo`. A CNH completa só sai nas rotas de frota (RNF-11).

#### API-15 e API-16 — Cadastrar e alterar veículo

Requisição:
```json
{"placa": "TST9Z99", "tipo": "CARRETA_SIDER", "capacidadeKg": 28000, "tiposCarga": ["CARGA_SECA"], "categoriaCnhExigida": "E"}
```
Resposta (201 ou 200):
```json
{"id": "vei-971d41534b", "placa": "TST9Z99", "tipo": "CARRETA_SIDER", "capacidade_kg": 28000.0,
 "tipos_carga": ["CARGA_SECA"], "categoria_cnh_exigida": "E", "ativo": true, "em_viagem": false}
```

#### API-13 e API-17 — Desativar motorista e veículo

Sem corpo. Resposta 200: `{"id": "mot-8cd7aab104", "ativo": false}`. Desativar um item já inativo responde 200 com o mesmo corpo. O histórico das viagens é mantido.

### 7.3 Eventos consumidos

Envelope e validação como na ESP-LOG-001 (§7.3).

| Tópico | Produtor | Chave | Ação | Em caso de mensagem inválida |
|---|---|---|---|---|
| `solicitacao_frete_criada` | `logistica-service` | `solicitacaoFreteId` | RF-01 | DLT `transportadoras.dlt` |
| `frete_selecionado` | `logistica-service` | `pedidoId` | RF-08 | DLT |
| `pedido_atualizado` | Pedidos | `pedidoId` | RF-10 | DLT |
| `relogio_ajustado` | `logistica-service` | `"relogio"` | RF-11 | DLT |

Os campos e exemplos de `solicitacao_frete_criada`, `frete_selecionado` e `relogio_ajustado` estão na ESP-LOG-001 (§7.4), que é a fonte da verdade desses tópicos; os de `pedido_atualizado`, na ESP-LOG-001 (§7.3). Os campos obrigatórios de `solicitacao_frete_criada` são `solicitacaoFreteId`, `pedidoId`, `tipoCarga`, `pesoKg` (> 0), `origem` e `destino` (`cidade`, `uf`, `lat` de −90 a 90, `lon` de −180 a 180), `distanciaKm` (≥ 0), `dataColetaPrevista`, `prazoDecisaoEm` e `status` (`"ABERTA"`); `produtoNome` é opcional.

Exemplo de `frete_selecionado` recebido (FS-1 do §8.0):
```json
{
  "eventId": "783964f2-440c-4f9b-b744-6cb2fb263720",
  "eventType": "frete_selecionado",
  "eventVersion": "1.0",
  "timestamp": "2026-11-10T12:05:00.100Z",
  "source": "logistica-service",
  "correlationId": "3e46ad25-60ba-46b7-abe1-250ad2717009",
  "aggregateId": "PED-1001",
  "payload": {
    "pedidoId": "PED-1001",
    "solicitacaoFreteId": "5c0e7b9a-3d2f-4e8a-9b1c-7f6a2d4e8c10",
    "entregaId": "e7a41c22-6b0d-4f3e-8a5c-1d9b2e7f4a63",
    "tentativa": 1,
    "cotacaoId": "3996972a-f710-5b2d-bb56-e01716c4cf05",
    "transportadoraId": "transp-economica",
    "preco": 6156.86,
    "prazoDias": 8,
    "dataEntregaPrevista": "2026-11-23",
    "criterio": "AUTOMATICO_MENOR_PRECO",
    "status": "FRETE_SELECIONADO"
  }
}
```

### 7.4 Eventos publicados

Envelope comum como na ESP-LOG-001 (§7.4), com `"source": "transportadoras-service"`.

| Tópico | Quando | Chave de partição (`aggregateId`) | Payload |
|---|---|---|---|
| `cotacao_recebida` | Cotação automática (RF-01) ou digitada (RF-05) | `solicitacaoFreteId` | `cotacaoId`, `solicitacaoFreteId`, `transportadoraId`, `transportadoraNome`, `preco`, `prazoDias`, `dataEntregaPrevista`, `validaAte`, `origemCotacao`, `observacoes` |
| `rastreio_atualizado` | Escala (RF-08) e cada evento da viagem (RF-09) | `pedidoId` | Comuns: `pedidoId`, `entregaId`, `transportadoraId`, `sequencia`, `tipo`, `descricao`, `ocorridoEm`. Por tipo: tabela abaixo |
| `transportadoras.dlt` | Mensagem consumida que não pôde ser processada | `aggregateId` da original, ou `"desconhecido"` | Como `logistica.dlt` (ESP-LOG-001, §7.4) |

| `tipo` | Campos além dos comuns | `ocorridoEm` | `descricao` |
|---|---|---|---|
| `VIAGEM_ALOCADA` | `motorista` (`nome`, `telefone`, `cnhMascarada`), `veiculo` (`placa`, `tipo`), `transportadora` (`nome`, `telefone`), `coletaPrevista`, `previsaoChegada`, `rota` (60 pontos `[lat, lon]`), `posicao` (origem), `progresso` 0.0 | Hora do módulo da escala | `"Motorista <nome> e veículo <placa> escalados."` |
| `VIAGEM_RECUSADA` | `motivo`: `"SEM_VEICULO"` (nenhum veículo livre compatível) ou `"SEM_MOTORISTA"` (há veículo, mas nenhum motorista livre que possa dirigi-lo) | Hora do módulo da escala | `"A transportadora não tem motorista e veículo livres para esta carga."` |
| `COLETA_REALIZADA` | `posicao` (origem), `progresso` 0.0, `previsaoChegada` | `coleta_em` do plano | `"Carga coletada em <local da origem>."` |
| `POSICAO` | `posicao`, `progresso`, `previsaoChegada` | Hora do módulo do passo | `"Veículo em deslocamento conforme rota planejada."` |
| `PARADA` | `posicao` (a 45%), `progresso` 0.45, `previsaoChegada`, `local`, `duracaoPrevistaMin` 480 | Instante em que o progresso chega a 0,45 | `"Parada para descanso do motorista em <local>."` ou `"Parada para descanso do motorista na rodovia."` |
| `PREVISAO_ATUALIZADA` | `posicao`, `progresso` (o marco), `previsaoChegada` (nova), `previsaoAnterior` | Instante do marco | `"Previsão de chegada ajustada para <dd/mm/aaaa HH:MM em Brasília>."` |
| `ENTREGA_REALIZADA` | `posicao` (destino), `progresso` 1.0, `previsaoChegada`, `noPrazo`, `atrasoHoras` | Chegada prevista | `"Entrega realizada em <local do destino>."` |

Exemplo `cotacao_recebida` (C-ECO de SF-1):
```json
{
  "eventId": "845fd983-28a6-4c3a-b8e9-5adeb0830aa6",
  "eventType": "cotacao_recebida",
  "eventVersion": "1.0",
  "timestamp": "2026-11-10T12:00:00.250Z",
  "source": "transportadoras-service",
  "correlationId": "3e46ad25-60ba-46b7-abe1-250ad2717009",
  "aggregateId": "5c0e7b9a-3d2f-4e8a-9b1c-7f6a2d4e8c10",
  "payload": {
    "cotacaoId": "3996972a-f710-5b2d-bb56-e01716c4cf05",
    "solicitacaoFreteId": "5c0e7b9a-3d2f-4e8a-9b1c-7f6a2d4e8c10",
    "transportadoraId": "transp-economica",
    "transportadoraNome": "Econômica Transportes",
    "preco": 6156.86,
    "prazoDias": 8,
    "dataEntregaPrevista": "2026-11-23",
    "validaAte": "2026-11-11T00:00:00.000Z",
    "origemCotacao": "SIMULADA",
    "observacoes": null
  }
}
```

Exemplo `rastreio_atualizado` `VIAGEM_ALOCADA` (FS-1; rota com 3 dos 60 pontos):
```json
{
  "pedidoId": "PED-1001",
  "entregaId": "e7a41c22-6b0d-4f3e-8a5c-1d9b2e7f4a63",
  "transportadoraId": "transp-economica",
  "sequencia": 1,
  "tipo": "VIAGEM_ALOCADA",
  "descricao": "Motorista Marcos Vieira e veículo QWE3F45 escalados.",
  "motorista": {"nome": "Marcos Vieira", "telefone": "(11) 97766-5544", "cnhMascarada": "*******1243"},
  "veiculo": {"placa": "QWE3F45", "tipo": "CARRETA_GRANELEIRA"},
  "transportadora": {"nome": "Econômica Transportes", "telefone": "(11) 4000-1002"},
  "coletaPrevista": "2026-11-10T14:05:00.300Z",
  "previsaoChegada": "2026-11-23T17:00:00.000Z",
  "rota": [[-12.5453, -55.7114], [-12.738783, -55.552454], [-23.9608, -46.3336]],
  "posicao": {"lat": -12.5453, "lon": -55.7114},
  "progresso": 0.0,
  "ocorridoEm": "2026-11-10T12:05:00.300Z"
}
```

Exemplo `rastreio_atualizado` `ENTREGA_REALIZADA` (FS-1):
```json
{
  "pedidoId": "PED-1001", "entregaId": "e7a41c22-6b0d-4f3e-8a5c-1d9b2e7f4a63", "transportadoraId": "transp-economica",
  "sequencia": 15, "tipo": "ENTREGA_REALIZADA", "descricao": "Entrega realizada em Santos - SP.",
  "posicao": {"lat": -23.9608, "lon": -46.3336}, "progresso": 1.0,
  "previsaoChegada": "2026-11-24T19:36:00.000Z", "ocorridoEm": "2026-11-24T19:36:00.000Z",
  "noPrazo": false, "atrasoHoras": 16.6
}
```
A `sequencia` final depende de quantos passos a viagem levou (RN-12); o resto do payload não depende.

## 8. Requisitos funcionais

### 8.0 Cenário base dos critérios de aceitação

Os CAs são verificados como caixa-preta no ambiente do `docker-compose.yml`, como na ESP-LOG-001 (§8.0, Q-01). Para isolar este serviço, o QA publica os eventos de entrada direto no Kafka. A logística também os recebe: cotações e rastreios de solicitações que ela não conhece vão para a `logistica.dlt`, o que é esperado nesses testes.

**S0 — ambiente.** Recém-criado, com os seeds do Apêndice A, nenhuma viagem e relógio sem ajuste.

**T0 — hora de referência.** As solicitações são consumidas com a hora do módulo em `2026-11-10T12:00:00.000Z` (terça-feira); a escala de FS-1 acontece em `2026-11-10T12:05:00.300Z`. O relógio só anda para a frente (ESP-LOG-001, Q-02): em outro horário, confira as mesmas relações.

**Usuários** (tokens como na ESP-LOG-001):

| Nome | `sub` | `tenant_id` | `active_scope` | `permissions` | Perfil |
|---|---|---|---|---|---|
| U-ROD | `usr-transp-rodovia` | `emp-transp-rodovia` | `CARRIER` | `[]` | transportadora (`transp-rodovia`) |
| U-EXP | `usr-transp-expressa` | `emp-transp-expressa` | `CARRIER` | `[]` | transportadora (`transp-expressa`) |
| U-SEMT | `usr-transp-sem` | `emp-sem-frota` | `CARRIER` | `[]` | transportadora sem transportadora homologada |
| U-COMP | `usr-comprador-1` | `emp-comprador-1` | `BUYER` | `[]` | comprador |
| U-ADM | `usr-admin` | `emp-portal` | `TENANT_ADMIN` | `["logistica:admin"]` | admin |

**Solicitações de referência** (publicadas em `solicitacao_frete_criada`; todas com `dataColetaPrevista` `"2026-11-11"`, `prazoDecisaoEm` `"2026-11-11T00:00:00.000Z"` e `status` `"ABERTA"`):

| Nome | `solicitacaoFreteId` | `pedidoId` | Carga | Rota (`distanciaKm`) |
|---|---|---|---|---|
| SF-1 | `5c0e7b9a-3d2f-4e8a-9b1c-7f6a2d4e8c10` | `PED-1001` | `GRANEL`, 24000 kg | Sorriso/MT → Santos/SP (2091.1) |
| SF-2 | `8a2d6f14-5c3b-4e7a-b9d0-3e1f7c5a9b28` | `PED-1002` | `CARGA_SECA`, 20000 kg | Rio Verde/GO → Paranaguá/PR (1163.0) |
| SF-3 | `3b8e1f2a-6c4d-4e9b-a7f0-5d2c8e1b4a96` | `PED-1003` | `REFRIGERADO`, 30000 kg | Sorriso/MT → Santos/SP (2091.1) |
| SF-4 | `2f7c9b10-4e6d-4a8b-9c3f-1a5e7d2b8c64` | `PED-1004` | `PERIGOSO`, 10000 kg | Sorriso/MT → Santos/SP (2091.1) |
| SF-5 | `6d1a4c8e-2b7f-4d3a-9e5c-8f0b3a6d2c17` | `PED-1005` | `GRANEL`, 24000 kg | Sorriso/MT → Salvador/BA (2426.6) |
| SF-6 | `7e2b5d9f-3c8a-4e4b-8f6d-9a1c4b7e3d28` | `PED-1006` | `GRANEL`, 1000 kg | Campinas/SP → Santos/SP (180.1) |

As coordenadas são as da tabela da ESP-LOG-001 (Apêndice A).

**FS-1**: o `frete_selecionado` do §7.3: SF-1, transportadora `transp-economica`, `entregaId` `e7a41c22-6b0d-4f3e-8a5c-1d9b2e7f4a63`, `dataEntregaPrevista` `"2026-11-23"`.

### RF-01 — Cotar automaticamente

- **Prioridade:** Must
- **Enunciado (EARS):** Quando uma mensagem válida de `solicitacao_frete_criada` com `solicitacaoFreteId` ainda não recebido chegar, o serviço deve emitir uma `cotacao_recebida` para cada transportadora ativa, simulada, que atende a carga e tem frota livre compatível.
- **Regras aplicáveis:** RN-01 a RN-06
- **Interface:** tópico `solicitacao_frete_criada`, tópico `cotacao_recebida`

```gherkin
# CA-01
Cenário: Três cotações para o granel de Sorriso a Santos
  Dado o cenário S0
  Quando SF-1 é publicada
  Então em até 5 s há exatamente 3 mensagens em "cotacao_recebida" com chave igual ao id de SF-1 e correlationId igual ao de SF-1:
    | transportadoraId  | cotacaoId                            | preco   | prazoDias | dataEntregaPrevista |
    | transp-expressa   | c5d00486-d2af-5884-8ed9-0a0dafa8c84d | 9026.18 | 4         | 2026-11-17          |
    | transp-economica  | 3996972a-f710-5b2d-bb56-e01716c4cf05 | 6156.86 | 8         | 2026-11-23          |
    | transp-graneleira | 1613289a-100e-598d-bc42-9b1f9f1d2293 | 7113.3  | 5         | 2026-11-18          |
  E cada payload tem transportadoraNome da tabela do Apêndice A, validaAte "2026-11-11T00:00:00.000Z", origemCotacao "SIMULADA" e observacoes null

# CA-02
Cenário: Só quem atende e tem frota
  Quando SF-2 é publicada
  Então há exatamente 1 cotação: transp-expressa, preco 5851.34, prazoDias 3, dataEntregaPrevista "2026-11-16", cotacaoId "1dde1f52-d7cf-5007-ac83-2ae1b0c3dc16" (a Econômica não tem veículo de carga seca para 20 t, a Graneleira não leva carga seca e a Rodovia não é simulada)
  Quando SF-3 é publicada
  Então em 5 s não há nenhuma cotação para SF-3 (a Frio Sul não tem veículo para 30 t)
  Quando SF-4 é publicada
  Então há exatamente 1 cotação: transp-perigosos, preco 18677.95, prazoDias 7, dataEntregaPrevista "2026-11-20", cotacaoId "9ef07023-8d02-5c4a-aad6-4360b0a261b6"
  Quando SF-5 é publicada
  Então há exatamente 2 cotações: transp-expressa (10301.08, 5 dias, "2026-11-18") e transp-economica (7029.16, 9 dias, "2026-11-24"); a Graneleira não atende a BA

# CA-03
Cenário: Preço mínimo
  Quando SF-6 é publicada
  Então as cotações são transp-expressa 1500.00 em 2 dias ("2026-11-13"), transp-economica 900.00 em 3 dias ("2026-11-16") e transp-graneleira 1100.00 em 2 dias ("2026-11-13")

# CA-04
Cenário: Frota ocupada não cota
  Dado FS-1 escalada (vei-eco-1, o único veículo da Econômica para granel de 24 t, em viagem)
  Quando uma solicitação igual a SF-1, com outro solicitacaoFreteId, é publicada
  Então há cotações de transp-expressa e transp-graneleira, e nenhuma de transp-economica

# CA-05
Cenário: Solicitação repetida
  Dado SF-1 já recebida
  Quando SF-1 é publicada de novo, com outro eventId e pesoKg 99999
  Então continua havendo exatamente 3 cotações para SF-1, sem mensagem em "transportadoras.dlt"

# CA-06
Cenário: Solicitação fora do contrato
  Quando é publicada uma solicitacao_frete_criada com qualquer uma destas mudanças em SF-1 (e outro id): origem.lat 95; tipoCarga "VIVO"; status "COTADA"; sem prazoDecisaoEm
  Então não há cotação para ela e há uma mensagem em "transportadoras.dlt" com failedAtAttempt 1 e error começando com "Payload de solicitacao_frete_criada fora do contrato:"
```

### RF-02 — Consultar transportadoras

- **Prioridade:** Must
- **Enunciado (EARS):** Quando um usuário autenticado consultar a API-04 ou a API-09, o serviço deve devolver as transportadoras com a regra de cotação; quando um usuário com perfil transportadora consultar a API-05, deve devolver a transportadora da empresa dele.
- **Regras aplicáveis:** RN-14
- **Interface:** API-04, API-05, API-09

```gherkin
# CA-07
Cenário: Lista e detalhe
  Quando U-COMP consulta a API-04 com size=2
  Então a resposta é 200 com total 6 e items "transp-economica" e "transp-expressa", nessa ordem (por nome), com os campos do exemplo da API-04
  Quando U-COMP consulta a API-09 de "transp-economica"
  Então a resposta é 200 com o mesmo objeto do primeiro item
  Quando consulta a API-09 de "nao-existe"
  Então a resposta é 404 com codigo "TRANSPORTADORA_NAO_ENCONTRADA"

# CA-08
Cenário: Minha transportadora
  Quando U-ROD consulta a API-05
  Então a resposta é 200 com o objeto do exemplo da API-05
  Quando U-SEMT consulta
  Então a resposta é 404 com codigo "SEM_TRANSPORTADORA"
  Quando U-COMP ou U-ADM consulta
  Então a resposta é 403 com codigo "PERFIL_NAO_PERMITIDO"
  Quando a API-04 é chamada sem Authorization
  Então a resposta é 401 com codigo "NAO_AUTENTICADO"
```

### RF-03 — Ranking de desempenho

- **Prioridade:** Should
- **Enunciado (EARS):** Quando um usuário autenticado consultar a API-06, o serviço deve devolver as transportadoras ativas ordenadas pela pontualidade, com os números de viagens e cotações, filtrados pelo tipo de carga quando informado.
- **Regras aplicáveis:** RN-17
- **Interface:** API-06

```gherkin
# CA-09
Cenário: Ranking sem histórico
  Dado o cenário S0
  Quando U-COMP consulta a API-06
  Então a resposta é 200 com total 6 e posicao 1 a 6 para Econômica Transportes, Expressa Cargas Rápidas, Frio Sul Refrigerados, Graneleira Centro-Oeste, Rodovia Sul Transportes e Segura Cargas Especiais (por nome)
  E todas com entregas 0, no_prazo 0, pct_no_prazo null, atraso_medio_horas null, vezes_escolhida 0, cotacoes 0 e preco_medio_t_km null

# CA-10
Cenário: Ranking com cotações e uma entrega
  Dado SF-1 cotada e FS-1 entregue (CA-28)
  Quando U-COMP consulta a API-06
  Então o item de transp-economica tem posicao 1, entregas 1, no_prazo 0, pct_no_prazo 0.0, atraso_medio_horas 16.6, vezes_escolhida 1, cotacoes 1 e preco_medio_t_km 0.1227
  E o de transp-expressa tem cotacoes 1 e preco_medio_t_km 0.1799, e o de transp-graneleira cotacoes 1 e preco_medio_t_km 0.1417
  Quando consulta com tipoCarga=REFRIGERADO
  Então total continua 6 e todas têm entregas 0 e cotacoes 0
  Quando consulta com tipoCarga=XYZ ou size=101
  Então a resposta é 422 com codigo "DADOS_INVALIDOS"
```

### RF-04 — Cargas para a transportadora

- **Prioridade:** Must
- **Enunciado (EARS):** Quando um usuário com perfil transportadora consultar a API-07, o serviço deve devolver as cargas compatíveis com a transportadora da empresa dele, com a situação de cada uma para ela.
- **Regras aplicáveis:** RN-15, RN-16
- **Interface:** API-07

```gherkin
# CA-11
Cenário: Cargas abertas e compatíveis
  Dado SF-1, SF-2, SF-3 e SF-4 recebidas e abertas
  Quando U-ROD consulta a API-07
  Então items tem SF-1 e SF-2 (granel e carga seca), não tem SF-3 (refrigerado) nem SF-4 (perigoso), ambas com situacao "ACEITANDO_COTACOES" e pode_cotar true
  E a resposta tem horaDoModulo

# CA-12
Cenário: Situação ao longo do fluxo
  Dado SF-2 aberta
  Quando U-ROD envia a cotação digitada do CA-15 para SF-2
  Então SF-2 aparece com situacao "COTACAO_ENVIADA", pode_cotar false, minha_cotacao_id "4ec74218-2a41-5ef2-8032-cb8c1dc41e28", minha_cotacao_preco 5800.0, minha_cotacao_prazo 4, minha_cotacao_entrega "2026-11-17" e minha_cotacao_origem "DIGITADA"
  Quando é consumido um frete_selecionado de SF-2 com transportadoraId "transp-rodovia"
  Então SF-2 aparece com situacao "VENCEU" e transportadora_vencedora_id "transp-rodovia"
  Dado outra solicitação igual a SF-2, cotada por U-ROD, e o frete_selecionado com transportadoraId "transp-expressa"
  Então ela aparece com situacao "OUTRA_VENCEU"
  Dado SF-1, não cotada por U-ROD, com frete_selecionado para "transp-economica"
  Então SF-1 não aparece na API-07; com todas=true, aparece com situacao "ENCERRADA"
  Dado SF-2 com situacao "VENCEU" e um pedido_atualizado CANCELADO para "PED-1002"
  Então SF-2 aparece com situacao "CANCELADA" e cancelada true

# CA-13
Cenário: Prazo vencido e quem pode consultar
  Dado uma solicitação igual a SF-2, não cotada, e a hora do módulo depois de prazoDecisaoEm
  Então ela não aparece na API-07 de U-ROD; com todas=true, aparece com situacao "ENCERRADA"
  Quando U-COMP consulta a API-07
  Então a resposta é 403 com codigo "PERFIL_NAO_PERMITIDO"
  Quando U-SEMT consulta
  Então a resposta é 403 com codigo "SEM_TRANSPORTADORA"
  Quando U-ROD consulta com size=101
  Então a resposta é 422 com codigo "DADOS_INVALIDOS"
```

### RF-05 — Cotação digitada

- **Prioridade:** Must
- **Enunciado (EARS):** Quando um usuário com perfil transportadora enviar a API-08 válida para uma solicitação aberta, compatível, ainda não cotada pela transportadora dele, com frota livre compatível, o serviço deve emitir a cotação, publicar `cotacao_recebida` e responder 201.
- **Regras aplicáveis:** RN-02, RN-05, RN-07 a RN-09
- **Interface:** API-08, tópico `cotacao_recebida`

```gherkin
# CA-14
Cenário: Cotação digitada aceita
  Dado SF-2 aberta e a hora do módulo T0
  Quando U-ROD envia a API-08 para SF-2 com o corpo do exemplo da API-08
  Então a resposta é 201 com o corpo do exemplo da API-08
  E há uma mensagem em "cotacao_recebida" com chave igual ao id de SF-2, payload com os mesmos valores da resposta e transportadoraNome "Rodovia Sul Transportes"

# CA-15
Cenário: Validade sem fuso e prazo contado em dias úteis
  Quando U-ROD envia {"valor": 5800.00, "dataEntregaPrevista": "2026-11-17", "validaAte": "2026-11-10T15:00:00"} para SF-2
  Então a resposta é 201 com validaAte "2026-11-10T18:00:00.000Z" (15:00 em Brasília) e prazoDias 4
  Quando, em outra solicitação igual a SF-2, U-ROD envia dataEntregaPrevista "2026-11-14" (sábado)
  Então a resposta é 201 com prazoDias 2 (quinta e sexta)

# CA-16
Cenário: Datas inválidas
  Quando U-ROD envia dataEntregaPrevista "2026-11-11" (o dia da coleta) para SF-2
  Então a resposta é 422 com codigo "PRAZO_INVALIDO"
  Quando envia validaAte "2026-11-10T11:00:00Z" (antes de T0)
  Então a resposta é 422 com codigo "VALIDADE_INVALIDA"

# CA-17
Cenário: Corpo inválido
  Quando U-ROD envia qualquer corpo entre: valor 0; valor 10000000.01; sem dataEntregaPrevista; dataEntregaPrevista "17/11/2026"; sem validaAte; observacoes com 501 caracteres
  Então a resposta é 422 com codigo "DADOS_INVALIDOS"

# CA-18
Cenário: Cotação repetida, carga incompatível e solicitação encerrada
  Dado a cotação do CA-14 aceita
  Quando U-ROD envia de novo para SF-2
  Então a resposta é 409 com codigo "COTACAO_JA_ENVIADA"
  Quando U-EXP envia para SF-2 (a Expressa já cotou automaticamente)
  Então a resposta é 409 com codigo "COTACAO_JA_ENVIADA"
  Quando U-ROD envia para SF-4 (perigoso)
  Então a resposta é 403 com codigo "CARGA_INCOMPATIVEL"
  Quando U-ROD envia para SF-1 depois do frete_selecionado de SF-1, ou para uma solicitação com o prazo vencido
  Então a resposta é 409 com codigo "SOLICITACAO_ENCERRADA"
  Quando U-ROD envia para "nao-existe"
  Então a resposta é 404 com codigo "SOLICITACAO_NAO_ENCONTRADA"

# CA-19
Cenário: Quem pode cotar e frota livre
  Quando U-COMP ou U-ADM envia a API-08
  Então a resposta é 403 com codigo "PERFIL_NAO_PERMITIDO"
  Quando U-SEMT envia
  Então a resposta é 403 com codigo "SEM_TRANSPORTADORA"
  Dado mot-rod-1 e mot-rod-2 alterados (API-12) com cnhValidade "2026-11-01"
  Quando U-ROD envia uma cotação válida para uma solicitação igual a SF-2
  Então a resposta é 422 com codigo "SEM_FROTA_LIVRE"

# CA-20
Cenário: Precedência e atomicidade
  Quando U-SEMT envia para "nao-existe"
  Então a resposta é 403 "SEM_TRANSPORTADORA" (transportadora antes da solicitação)
  Quando U-ROD envia para SF-4 depois do frete_selecionado de SF-4
  Então a resposta é 403 "CARGA_INCOMPATIVEL" (compatibilidade antes do status)
  Quando U-ROD envia corpo com valor 0 para "nao-existe"
  Então a resposta é 422 "DADOS_INVALIDOS" (corpo antes da solicitação)
  E nenhuma resposta de erro publica cotacao_recebida nem grava cotação
```

### RF-06 — Motoristas

- **Prioridade:** Must
- **Enunciado (EARS):** Quando o dono da frota usar a API-10 a API-13, o serviço deve listar, cadastrar, alterar ou desativar os motoristas da transportadora.
- **Regras aplicáveis:** RN-18, RN-19
- **Interface:** API-10 a API-13

```gherkin
# CA-21
Cenário: Listar, cadastrar, alterar e desativar
  Quando U-ROD consulta a API-10 de "transp-rodovia"
  Então a resposta é 200 com total 2 e items mot-rod-1 (Eduardo Pereira) e mot-rod-2 (Juliana Martins), com ativo true e em_viagem false
  Quando U-ROD envia a API-11 com o corpo do exemplo
  Então a resposta é 201 com id no formato ^mot-[0-9a-f]{10}$ e os demais campos do exemplo
  Quando U-ROD envia a API-12 desse motorista com nome "Teste ESP 2"
  Então a resposta é 200 com nome "Teste ESP 2" e ativo true
  Quando U-ROD envia a API-13 desse motorista, duas vezes
  Então as duas respostas são 200 com {"id": <id>, "ativo": false}
  E a API-10 mostra o motorista com ativo false

# CA-22
Cenário: CNH duplicada
  Quando U-ROD envia a API-11 com cnhNumero "13345678901" (de mot-rod-1)
  Então a resposta é 409 com codigo "MOTORISTA_DUPLICADO"
  Quando U-ROD envia a API-12 de mot-rod-2 com cnhNumero "13345678901"
  Então a resposta é 409 com codigo "MOTORISTA_DUPLICADO" e mot-rod-2 continua com cnh_numero "14456789012"
  Quando U-ROD envia a API-12 de mot-rod-2 com os dados atuais dele
  Então a resposta é 200 (a própria CNH não conta como duplicidade)
  Quando U-ROD envia a API-12 de "nao-existe" com cnhNumero "13345678901"
  Então a resposta é 404 com codigo "MOTORISTA_NAO_ENCONTRADO" (existência antes da duplicidade)

# CA-23
Cenário: Validação, dono e viagem
  Quando U-ROD envia a API-11 com cnhNumero "123", ou cnhCategoria "A", ou nome "Jo", ou sem cnhValidade
  Então a resposta é 422 com codigo "DADOS_INVALIDOS" (com cnhNumero "123", erros[0].campo é "body.cnhNumero")
  Quando U-ROD consulta a API-10 de "transp-economica"
  Então a resposta é 403 com codigo "OUTRA_TRANSPORTADORA"
  Quando U-ROD consulta a API-10 de "nao-existe"
  Então a resposta é 404 com codigo "TRANSPORTADORA_NAO_ENCONTRADA"
  Quando U-COMP consulta a API-10 de "transp-rodovia"
  Então a resposta é 403 com codigo "PERFIL_NAO_PERMITIDO"
  Quando U-ADM consulta a API-10 de "transp-economica"
  Então a resposta é 200
  Dado FS-1 escalada com mot-eco-2
  Quando U-ADM envia a API-13 de mot-eco-2 em "transp-economica"
  Então a resposta é 409 com codigo "MOTORISTA_EM_VIAGEM" e mot-eco-2 continua ativo
  Quando U-ROD envia a API-11 de "transp-economica" com cnhNumero "123"
  Então a resposta é 422 "DADOS_INVALIDOS" (corpo antes do dono)
```

### RF-07 — Veículos

- **Prioridade:** Must
- **Enunciado (EARS):** Quando o dono da frota usar a API-14 a API-17, o serviço deve listar, cadastrar, alterar ou desativar os veículos da transportadora.
- **Regras aplicáveis:** RN-18, RN-19
- **Interface:** API-14 a API-17

```gherkin
# CA-24
Cenário: Cadastrar, alterar e desativar
  Quando U-ROD envia a API-15 com o corpo do exemplo
  Então a resposta é 201 com id no formato ^vei-[0-9a-f]{10}$ e os demais campos do exemplo
  Quando U-ROD envia a API-15 sem categoriaCnhExigida
  Então a resposta é 201 com categoria_cnh_exigida "E"
  Quando U-ROD envia a API-17 do veículo criado
  Então a resposta é 200 com {"id": <id>, "ativo": false}

# CA-25
Cenário: Placa duplicada e validação
  Quando U-ROD envia a API-15 com placa "QWE3F45" (da Econômica)
  Então a resposta é 409 com codigo "PLACA_DUPLICADA"
  Quando U-ROD envia a API-16 de vei-rod-2 com placa "RSL1A23" (de vei-rod-1)
  Então a resposta é 409 com codigo "PLACA_DUPLICADA" e vei-rod-2 continua com placa "RSL2B34"
  Quando U-ROD envia a API-15 com placa "ABC-1234", ou capacidadeKg 0, ou capacidadeKg 80001, ou tiposCarga [], ou tiposCarga ["VIVO"], ou categoriaCnhExigida "A"
  Então a resposta é 422 com codigo "DADOS_INVALIDOS"
  Quando U-ROD envia a API-16 ou a API-17 de "nao-existe"
  Então a resposta é 404 com codigo "VEICULO_NAO_ENCONTRADO"

# CA-26
Cenário: Veículo em viagem
  Dado FS-1 escalada com vei-eco-1
  Quando U-ADM envia a API-17 de vei-eco-1 em "transp-economica"
  Então a resposta é 409 com codigo "VEICULO_EM_VIAGEM"
  Quando U-ADM consulta a API-14 de "transp-economica"
  Então vei-eco-1 aparece com em_viagem true
```

### RF-08 — Escalar motorista e veículo

- **Prioridade:** Must
- **Enunciado (EARS):** Quando uma mensagem válida de `frete_selecionado` de uma transportadora deste serviço chegar para uma entrega ainda sem viagem e um pedido não cancelado, o serviço deve sortear e reservar um veículo livre compatível e um motorista livre que possa dirigi-lo, agendar a viagem e publicar `VIAGEM_ALOCADA`; se não houver, publicar `VIAGEM_RECUSADA`.
- **Regras aplicáveis:** RN-10, RN-11
- **Interface:** tópico `frete_selecionado`, tópico `rastreio_atualizado`

```gherkin
# CA-27
Cenário: Escala com sorteio reproduzível
  Dado SF-1 recebida e a hora do módulo "2026-11-10T12:05:00.300Z"
  Quando FS-1 é publicado
  Então há exatamente uma mensagem em "rastreio_atualizado" com chave "PED-1001", sequencia 1, tipo "VIAGEM_ALOCADA" e o payload igual ao exemplo do §7.4: veículo vei-eco-1 (QWE3F45), o único livre compatível, e motorista mot-eco-2 (Marcos Vieira), sorteado com a semente "e7a41c22-6b0d-4f3e-8a5c-1d9b2e7f4a63"
  E coletaPrevista é a hora da escala + 2 h, previsaoChegada é "2026-11-23T17:00:00.000Z" (14:00 em Brasília da data prometida) e a rota tem 60 pontos, de Sorriso a Santos
  E a API-10 e a API-14 de "transp-economica" (por U-ADM) mostram mot-eco-2 e vei-eco-1 com em_viagem true

# CA-29
Cenário: Falta de veículo ou de motorista
  Dado FS-1 escalada
  Quando é publicado um frete_selecionado igual a FS-1 para outra solicitação igual a SF-1, com entregaId "0f3b8d21-9c4e-4a7b-8e2d-5b6c1a9f3e07"
  Então o rastreio publicado para ele é sequencia 1, tipo "VIAGEM_RECUSADA", motivo "SEM_VEICULO"
  Dado mot-rod-1 e mot-rod-2 com cnhValidade "2026-11-01"
  Quando é publicado um frete_selecionado de SF-2 com transportadoraId "transp-rodovia"
  Então o rastreio é tipo "VIAGEM_RECUSADA" com motivo "SEM_MOTORISTA" (há veículo livre, mas nenhum motorista com CNH válida)

# CA-30
Cenário: Mensagens que não geram viagem
  Dado FS-1 escalada
  Quando FS-1 é publicado de novo com outro eventId
  Então não há segunda viagem nem segundo "VIAGEM_ALOCADA" para a entrega
  Quando é publicado um frete_selecionado de SF-2 com transportadoraId "transp-teste-a" (não pertence a este serviço)
  Então não há viagem nem rastreio para ele e nenhuma mensagem em "transportadoras.dlt"
  E, se U-ROD não cotou SF-2, SF-2 sai da API-07 de U-ROD e aparece com todas=true e situacao "ENCERRADA"
  Quando é publicado um frete_selecionado com transportadoraId "transp-economica" e solicitacaoFreteId "nao-existe"
  Então há uma mensagem em "transportadoras.dlt" com failedAtAttempt 1 e error "Solicitação desconhecida: nao-existe"
  Quando é publicado um frete_selecionado com criterio "SORTEIO"
  Então há uma mensagem em "transportadoras.dlt" com error começando com "Payload de frete_selecionado fora do contrato:"

# CA-31
Cenário: Cancelamento que chega antes da escolha
  Dado SF-4 recebida e o pedido_atualizado {"pedidoId": "PED-1004", "status": "CANCELADO"} consumido
  Quando é publicado o frete_selecionado de SF-4 com transportadoraId "transp-perigosos"
  Então não há viagem nem rastreio para ele
  E os veículos e motoristas de transp-perigosos continuam com em_viagem false
```

### RF-09 — Simular a viagem

- **Prioridade:** Must
- **Enunciado (EARS):** Enquanto uma viagem estiver `AGENDADA` ou `EM_TRANSITO`, a cada passo o serviço deve avançá-la até a hora do módulo e publicar, em ordem de `sequencia`, os rastreios de coleta, parada, previsão nova, posição e entrega que couberem; ao entregar, deve liberar o motorista e o veículo.
- **Regras aplicáveis:** RN-12, RN-13
- **Interface:** rotina de viagens, tópico `rastreio_atualizado`

```gherkin
# CA-28
Cenário: Viagem completa de FS-1
  Dado FS-1 escalada (CA-27)
  Quando U-ADM ajusta o relógio da logística para {"fator": 20000} (cada passo de 30 s reais ≈ 167 h do módulo; a viagem planejada tem cerca de 343 h)
  Então em até 180 s os rastreios de FS-1 têm sequências consecutivas 1, 2, ..., N e:
    | sequencia | tipo                | conteúdo                                                                                         |
    | 1         | VIAGEM_ALOCADA      | CA-27                                                                                             |
    | 2         | COLETA_REALIZADA    | ocorridoEm = coletaPrevista, posicao de Sorriso, progresso 0.0, descricao "Carga coletada em Sorriso - MT." |
    | entre 3 e N−1 | PARADA (uma vez) | progresso 0.45, posicao {"lat": -17.647621, "lon": -51.519858}, local "Jataí - GO", duracaoPrevistaMin 480, descricao "Parada para descanso do motorista em Jataí - GO." |
    | entre 3 e N−1 | PREVISAO_ATUALIZADA (uma vez, depois da PARADA) | previsaoAnterior "2026-11-23T17:00:00.000Z", previsaoChegada "2026-11-24T19:36:00.000Z" (atraso sorteado de 26.6 h), progresso ≥ 0.6 |
    | N         | ENTREGA_REALIZADA   | o exemplo do §7.4: noPrazo false, atrasoHoras 16.6 (19:36 UTC − 03:00 UTC do dia 24)               |
  E os demais rastreios entre 3 e N−1 são do tipo "POSICAO", com progresso entre 0 e 1
  E o progresso nunca diminui de uma sequência para a seguinte
  E depois da entrega, mot-eco-2 e vei-eco-1 têm em_viagem false

# CA-32
Cenário: Antes da hora da coleta, nada é publicado
  Dado FS-1 escalada e o relógio com fator 1
  Quando passam 90 s reais (3 passos)
  Então FS-1 continua só com o rastreio de sequencia 1
```

### RF-10 — Cancelar a viagem

- **Prioridade:** Must
- **Enunciado (EARS):** Quando uma mensagem válida de `pedido_atualizado` com status `CANCELADO` chegar, o serviço deve encerrar as solicitações do pedido como canceladas, cancelar as viagens em andamento e liberar motorista e veículo.
- **Regras aplicáveis:** RN-20
- **Interface:** tópico `pedido_atualizado`

```gherkin
# CA-33
Cenário: Cancelamento durante a viagem
  Dado FS-1 escalada (viagem AGENDADA ou EM_TRANSITO)
  Quando pedido_atualizado {"pedidoId": "PED-1001", "novoStatus": "CANCELADO"} é publicado
  Então mot-eco-2 e vei-eco-1 têm em_viagem false
  E nenhum rastreio novo de FS-1 é publicado nos 120 s seguintes, mesmo com o relógio a fator 3600
  Quando pedido_atualizado {"pedidoId": "PED-1001", "novoStatus": "EM_SEPARACAO"} é publicado para outro pedido em viagem
  Então a viagem continua
```

### RF-11 — Sincronizar o relógio do módulo

- **Prioridade:** Must
- **Enunciado (EARS):** Quando uma mensagem válida de `relogio_ajustado` com `versao` maior que a gravada chegar, o serviço deve gravar o novo estado do relógio; com `versao` menor ou igual, deve ignorá-la.
- **Regras aplicáveis:** RN-21
- **Interface:** tópico `relogio_ajustado`, API-07 (`horaDoModulo`)

```gherkin
# CA-34
Cenário: Relógio igual nos dois serviços
  Quando U-ADM ajusta o relógio da logística (ESP-LOG-001, API-13) para {"fator": 1, "avancarHoras": 6}
  Então em até 3 s a horaDoModulo da API-07 (U-ROD) difere menos de 1 s da horaDoModulo da API-12 da logística
  Quando é publicado um relogio_ajustado com versao menor que a atual e baseVirtual "2020-01-01T00:00:00.000Z"
  Então a horaDoModulo da API-07 continua igual à da logística
  Quando é publicado um relogio_ajustado sem fator
  Então há uma mensagem em "transportadoras.dlt" com failedAtAttempt 1
```

### RF-12 — Saúde e métricas

- **Prioridade:** Must
- **Enunciado (EARS):** Quando `/health`, `/health/ready` ou `/metrics` for chamado, o serviço deve responder sem exigir autenticação; `/health/ready` deve responder 503 se o banco ou o Kafka não responder em 3 s.
- **Interface:** API-01 a API-03

```gherkin
# CA-35
Cenário: Saúde
  Quando GET /health é chamado nas portas 8109 e 8119
  Então a resposta é 200 com status "UP" e service "transportadoras-service"
  Quando GET /health/ready é chamado com banco e Redpanda no ar
  Então a resposta é 200 com checks {"banco": "UP", "kafka": "UP"}
  Quando o Redpanda é parado
  Então GET /health/ready responde 503 com status "NOT_READY"
```

### RF-13 — Consumo idempotente, retentativas e DLT

- **Prioridade:** Must
- **Enunciado (EARS):** Se uma mensagem consumida for inválida, então o serviço deve publicá-la em `transportadoras.dlt` sem retentativa; se o processamento falhar por outro motivo, então deve tentar de novo depois de 1 s, 2 s e 4 s antes de publicá-la na DLT.
- **Regras aplicáveis:** RN-22
- **Interface:** todos os tópicos consumidos, `transportadoras.dlt`

```gherkin
# CA-36
Cenário: DLT do serviço
  Quando o texto "isto não é json" é publicado em "solicitacao_frete_criada"
  Então há uma mensagem em "transportadoras.dlt" com chave "desconhecido", originalEvent "isto não é json", failedAtAttempt 1 e originalTopic "solicitacao_frete_criada"
  Quando uma solicitação igual a SF-1 é publicada com dataColetaPrevista "31/11/2026" (o schema não confere o formato)
  Então entre 7 s e 15 s depois há uma mensagem em "transportadoras.dlt" com failedAtAttempt 4 e nenhuma cotação para ela
```

## 9. Regras de negócio

| ID | Regra | Exemplo concreto |
|---|---|---|
| RN-01 | Só cotam automaticamente as transportadoras `ativa` **e** `simulada`, na ordem do `id`, e só uma vez por solicitação: um `solicitacaoFreteId` já recebido não gera cotação nova. | CA-05. |
| RN-02 | A transportadora precisa atender a carga (glossário): tipo de carga e, se `ufs_atendidas` não for `null`, as duas UFs. | Graneleira (MT, GO, MS, SP, PR) não cota para Salvador/BA. |
| RN-03 | A transportadora precisa ter frota livre compatível na hora do módulo (D20). Quem não tem não cota e não recebe aviso. | CA-02 (Econômica, SF-2), CA-04. |
| RN-04 | Preço = `max(preco_minimo; (tarifa_km × distancia_km + tarifa_ton × peso_kg ÷ 1000) × fator_tipo_carga)`, ao centavo, meio para cima. Prazo = `prazo_base_dias + teto(distancia_km ÷ km_por_dia)` dias úteis. | Econômica, SF-1: 2,60 × 2091,1 + 30 × 24 = 6156,86; 2 + teto(5,23) = 8. Segura, SF-4: (5,20 × 2091,1 + 80 × 10) × 1,60 = 18677,952 → 18677,95. |
| RN-05 | `dataEntregaPrevista` = `dataColetaPrevista` + prazo em dias úteis. `validaAte` da cotação automática = `prazoDecisaoEm` da solicitação, como recebido. `cotacaoId` = UUID5 (glossário). | Coleta quarta 2026-11-11 + 8 dias úteis = segunda 2026-11-23. |
| RN-06 | `transportadoraNome` vai no evento; `observacoes` é `null` na cotação automática. | CA-01. |
| RN-07 | Cotação digitada: a transportadora é a da empresa do usuário, ativa (simulada ou não); sem ela → 403 `SEM_TRANSPORTADORA`. Solicitação inexistente → 404. Carga não atendida → 403 `CARGA_INCOMPATIVEL`. Solicitação `ENCERRADA`, ou `agora > prazo_decisao_em` → 409 `SOLICITACAO_ENCERRADA`. Já cotada pela transportadora (automática ou digitada) → 409 `COTACAO_JA_ENVIADA`. | CA-18, CA-19. |
| RN-08 | Cotação digitada: `prazoDias` = dias úteis entre `data_coleta_prevista` e `dataEntregaPrevista`; < 1 → 422 `PRAZO_INVALIDO`. A data de entrega pode cair num fim de semana. `validaAte` ≤ hora do módulo → 422 `VALIDADE_INVALIDA`. Sem frota livre compatível → 422 `SEM_FROTA_LIVRE`. `validaAte` sem fuso = Brasília. | Coleta 2026-11-11, entrega 2026-11-17 → 4 dias. |
| RN-09 | A cotação digitada tem `origemCotacao` `"DIGITADA"`, guarda `usuario_id` (`sub`) e publica `cotacao_recebida` como a automática. | CA-14. |
| RN-10 | Escala: se a transportadora do `frete_selecionado` não está neste serviço → ignorado (sem viagem, sem rastreio, sem DLT). Se já existe viagem para o `entregaId` → ignorado. Se a solicitação não existe → DLT `"Solicitação desconhecida: <id>"`. Se o pedido foi cancelado → sem viagem. Em todos os casos, a solicitação recebida (se existir) fica `ENCERRADA` com `transportadora_vencedora_id`. | CA-30, CA-31. |
| RN-11 | Sorteio e reserva: os veículos livres compatíveis, em ordem de `id`, são embaralhados com a semente; para cada veículo, os motoristas livres que podem dirigi-lo, em ordem de `id`, são embaralhados com a semente; vale o primeiro par que se consegue reservar. Sem par: `VIAGEM_RECUSADA` com `motivo` `"SEM_VEICULO"` se não havia veículo livre compatível, senão `"SEM_MOTORISTA"`. A viagem é agendada com `sequencia` 1 e o primeiro passo 30 s reais depois. | CA-27, CA-29. |
| RN-12 | Passo: em `AGENDADA`, só publica `COLETA_REALIZADA` (com `ocorridoEm` = coleta) quando `agora ≥ coleta_em`. Em `EM_TRANSITO`, calcula o progresso e publica, nesta ordem: `PARADA` ao passar de 0,45 (uma vez, com o instante em que teria acontecido); `PREVISAO_ATUALIZADA` ao passar de 0,60 se o atraso sorteado for > 0 (uma vez; nova previsão = anterior + atraso; o marco passa a ser o progresso atual, no máximo 0,95); e então `ENTREGA_REALIZADA` se o progresso chegou a 1, ou `POSICAO`. Cada rastreio soma 1 à `sequencia`. Com o relógio muito acelerado, um passo pode publicar vários rastreios. | CA-28. |
| RN-13 | Entrega: `ocorridoEm` = chegada prevista; `noPrazo` e `atrasoHoras` pelo limite do prazo (glossário); a viagem vai a `ENTREGUE` e o motorista e o veículo são liberados na mesma transação. | FS-1: chegada 24/11 19:36 UTC, limite 24/11 03:00 UTC → 16.6 h. |
| RN-14 | A API-04 lista todas as transportadoras por `nome`; a API-05 devolve a da empresa do usuário (sem ela → 404 `SEM_TRANSPORTADORA`). | CA-07, CA-08. |
| RN-15 | Cargas da API-07: tipo de carga ∈ `tipos_carga` da transportadora do usuário **e** (sem `ufs_atendidas` **ou** as duas UFs nelas) **e** (`todas=true` **ou** (`status` `ABERTA` **e** `prazo_decisao_em` > agora) **ou** a transportadora cotou). Ordem: `data_coleta_prevista` decrescente, depois o recebimento decrescente, depois `id`. Empresa sem transportadora → 403 `SEM_TRANSPORTADORA`. | CA-11, CA-13. |
| RN-16 | `situacao`, na ordem: `cancelada` → `"CANCELADA"`; vencedora = a transportadora do usuário → `"VENCEU"`; outra vencedora → `"OUTRA_VENCEU"` se cotou, senão `"ENCERRADA"`; `ABERTA` e `prazo_decisao_em` > agora → `"COTACAO_ENVIADA"` se cotou, senão `"ACEITANDO_COTACOES"`; senão `"ENCERRADA"`. `pode_cotar` = `situacao` é `"ACEITANDO_COTACOES"`. | CA-12. |
| RN-17 | Ranking (API-06), só ativas: `entregas` = viagens `ENTREGUE`; `no_prazo` = entregues no prazo; `pct_no_prazo` = `no_prazo ÷ entregas` (4 casas) ou `null`; `atraso_medio_horas` = média de `atraso_real_horas` das entregues (1 casa) ou `null`; `vezes_escolhida` = viagens agendadas (qualquer status); `cotacoes` = cotações emitidas; `preco_medio_t_km` = média de `preco ÷ (peso_kg ÷ 1000 × distancia_km)` (4 casas) ou `null`. Com `tipoCarga`, todas as contagens só consideram solicitações desse tipo. Ordem: `pct_no_prazo` decrescente (sem histórico por último), `entregas` decrescente, `nome`. `posicao` = 1 + deslocamento da página + índice. | CA-09, CA-10. |
| RN-18 | Frota: só o dono da frota (glossário) usa as API-10 a API-17. Transportadora inexistente → 404 `TRANSPORTADORA_NAO_ENCONTRADA`; de outra empresa → 403 `OUTRA_TRANSPORTADORA`. CNH única por transportadora e placa única no serviço, contando os desativados, no cadastro e na alteração (a do próprio item não conta) → 409. | CA-22, CA-25. |
| RN-19 | Desativar exige que o item não esteja em viagem (409 `MOTORISTA_EM_VIAGEM` / `VEICULO_EM_VIAGEM`); a desativação é definitiva e repeti-la responde 200. Alterar um item em viagem é permitido e não afeta a viagem em andamento. | CA-21, CA-26. |
| RN-20 | Cancelamento: só age com `novoStatus` (ou `status`) `CANCELADO`, sem diferenciar maiúsculas. As solicitações recebidas do pedido ficam `ENCERRADA` e `cancelada`; as viagens `AGENDADA` ou `EM_TRANSITO` ficam `CANCELADA`, com a frota liberada. Nenhum rastreio é publicado. | CA-33. |
| RN-21 | Relógio: grava o estado de `relogio_ajustado` só se a `versao` for maior que a gravada; mensagem repetida ou atrasada não muda nada. | CA-34. |
| RN-22 | Consumo: idempotente por `eventId`, com retentativas e DLT como na RN-30 da ESP-LOG-001, no tópico `transportadoras.dlt`. | CA-36. |
| RN-23 | Requisição com erro (qualquer 4xx) não altera estado, não grava cotação nem evento. | CA-20. |

## 10. Catálogo de erros

Formato RFC 7807 com `codigo`, igual ao da ESP-LOG-001 (§10), inclusive `DADOS_INVALIDOS` com `erros`. Os códigos de autenticação (`NAO_AUTENTICADO`, `TOKEN_INVALIDO`, `TOKEN_EXPIRADO`, `AUTENTICACAO_INDISPONIVEL`, `PERFIL_NAO_PERMITIDO`, `PERFIL_AUSENTE`) e `DADOS_INVALIDOS` são os mesmos.

| Código | HTTP | Quando ocorre |
|---|---|---|
| `SEM_TRANSPORTADORA` | 404 | API-05: a empresa do usuário não tem transportadora. |
| `SEM_TRANSPORTADORA` | 403 | API-07 e API-08: a empresa do usuário não tem transportadora (ativa, na API-08). |
| `TRANSPORTADORA_NAO_ENCONTRADA` | 404 | `transportadora_id` inexistente (API-09 a API-17). |
| `OUTRA_TRANSPORTADORA` | 403 | Usuário transportadora mexendo na frota de outra empresa. |
| `SOLICITACAO_NAO_ENCONTRADA` | 404 | API-08: solicitação não recebida por este serviço. |
| `CARGA_INCOMPATIVEL` | 403 | API-08: a transportadora não atende o tipo de carga ou a rota. |
| `SOLICITACAO_ENCERRADA` | 409 | API-08: solicitação `ENCERRADA` ou com o prazo vencido. |
| `COTACAO_JA_ENVIADA` | 409 | API-08: a transportadora já cotou a solicitação. |
| `PRAZO_INVALIDO` | 422 | API-08: menos de 1 dia útil entre a coleta e a entrega. |
| `VALIDADE_INVALIDA` | 422 | API-08: `validaAte` não é posterior à hora do módulo. |
| `SEM_FROTA_LIVRE` | 422 | API-08: sem frota livre compatível com a carga. |
| `MOTORISTA_NAO_ENCONTRADO` | 404 | Motorista inexistente na transportadora. |
| `MOTORISTA_DUPLICADO` | 409 | CNH já usada por outro motorista da transportadora. |
| `MOTORISTA_EM_VIAGEM` | 409 | Desativar motorista em viagem. |
| `VEICULO_NAO_ENCONTRADO` | 404 | Veículo inexistente na transportadora. |
| `PLACA_DUPLICADA` | 409 | Placa já usada por outro veículo. |
| `VEICULO_EM_VIAGEM` | 409 | Desativar veículo em viagem. |

`SEM_TRANSPORTADORA` aparece com dois status: 404 na API-05 (o recurso pedido é a transportadora) e 403 na API-07 e na API-08 (falta a permissão para usar a rota). Os dois são literais.

Respostas fora do catálogo: como na ESP-LOG-001 (§10): 404 `NAO_ENCONTRADO`, 405 `METODO_NAO_PERMITIDO`, 500 `ERRO_INTERNO`.

**Ordem de verificação** (vale o primeiro):

1. Corpo que não é JSON legível → 422 `DADOS_INVALIDOS`.
2. Autenticação (ESP-LOG-001, §7.1) → 401 ou 503.
3. Perfil da rota → 403 `PERFIL_NAO_PERMITIDO`.
4. Parâmetros e corpo → 422 `DADOS_INVALIDOS`.
5. Transportadora do usuário (API-07, API-08) → 403 `SEM_TRANSPORTADORA`; ou transportadora da rota (API-09 a API-17) → 404 `TRANSPORTADORA_NAO_ENCONTRADA`, depois 403 `OUTRA_TRANSPORTADORA`.
6. Item da rota → 404 (`SOLICITACAO_NAO_ENCONTRADA`, `MOTORISTA_NAO_ENCONTRADO`, `VEICULO_NAO_ENCONTRADO`).
7. Compatibilidade (API-08) → 403 `CARGA_INCOMPATIVEL`.
8. Estado → 409 (`SOLICITACAO_ENCERRADA`, depois `COTACAO_JA_ENVIADA`; `MOTORISTA_DUPLICADO`, `PLACA_DUPLICADA`, `MOTORISTA_EM_VIAGEM`, `VEICULO_EM_VIAGEM`).
9. Regras da cotação digitada → 422 (`PRAZO_INVALIDO`, `VALIDADE_INVALIDA`, `SEM_FROTA_LIVRE`, nessa ordem).

## 11. Requisitos não funcionais

| ID | Característica (ISO/IEC 25010) | Requisito | Métrica e limiar | Verificação |
|---|---|---|---|---|
| RNF-01 | Confiabilidade — integridade | Reserva exclusiva da frota com duas cópias | Dois `frete_selecionado` simultâneos da mesma transportadora, com um só veículo livre compatível, processados um em cada cópia: exatamente 1 `VIAGEM_ALOCADA` e 1 `VIAGEM_RECUSADA`; nenhum veículo ou motorista em duas viagens | CA-37 (ainda sem teste automatizado no projeto) |
| RNF-02 | Confiabilidade — tolerância a falhas | Uma cópia cai no meio da viagem | Com `transportadoras-1` parada e a viagem `EM_TRANSITO`, a viagem chega a `ENTREGUE` pela cópia 2, com rastreios de sequência 1 a N sem buraco | `testes_integracao/test_cenarios_distribuidos.py` — CA-38 |
| RNF-03 | Adequação funcional — exatidão | Cálculos reproduzíveis | A mesma solicitação gera sempre o mesmo `cotacaoId`, preço e prazo; a mesma entrega gera sempre o mesmo motorista, veículo, plano e atraso | `services/transportadoras-service/tests/` (unitários) — CA-39 |
| RNF-04 | Compatibilidade — interoperabilidade | Formato único de erro | 100% das respostas 4xx e 5xx da API (exceto `/health/ready`) em RFC 7807 com `codigo` | CA-40 |
| RNF-05 | Confiabilidade — ordenação | Chave de partição e sequência | 100% das `cotacao_recebida` com chave = `solicitacaoFreteId`; 100% dos `rastreio_atualizado` com chave = `pedidoId` e `sequencia` consecutiva por entrega | CA-41 |
| RNF-06 | Manutenibilidade — analisabilidade | Correlação | 100% das cotações têm o `correlationId` da solicitação; 100% dos rastreios, o do `frete_selecionado` | CA-41 |
| RNF-07 | Segurança — confidencialidade (LGPD, D19) | CNH protegida | O número completo da CNH só sai nas API-10 a API-12 (dono da frota); em 100% dos eventos sai só `cnhMascarada` com 4 dígitos visíveis | CA-42 |
| RNF-08 | Eficiência — uso de recursos | Pool limitado | No máximo 5 conexões por cópia (`svc_transportadoras` ≤ 10 com as duas) | Inspeção |
| RNF-09 | Manutenibilidade | Logs estruturados | Como o RNF-09 da ESP-LOG-001 | Inspeção |
| RNF-10 | Portabilidade | Só as dependências permitidas (§5) | Nenhum `import` fora da lista, de `comum` e de `transportadoras` | Inspeção |

```gherkin
# CA-37
Cenário: Reserva disputada
  Dado SF-1 recebida duas vezes com ids diferentes (A e B) e só vei-eco-1 livre para granel de 24 t
  Quando dois frete_selecionado da Econômica, um para A e outro para B, com entregaIds diferentes, são publicados juntos
  Então há exatamente um VIAGEM_ALOCADA (com vei-eco-1) e um VIAGEM_RECUSADA (motivo "SEM_VEICULO")

# CA-38
Cenário: Cópia caindo no meio da viagem
  Igual ao CA-65 da ESP-LOG-001, observado nos rastreios publicados por este serviço

# CA-39
Cenário: Reprodutibilidade
  Os testes unitários de cotacao.py e simulacao.py passam: mesmo cálculo para a mesma entrada; embaralhar e planejar com a mesma semente dão o mesmo resultado

# CA-40
Cenário: Formato de erro
  Para cada resposta 4xx dos CAs de erro deste documento
  Então o Content-Type é application/problem+json e o corpo tem type, title, status, detail, instance, correlationId, timestamp e codigo

# CA-41
Cenário: Chaves, sequência e correlação
  Depois dos CA-01 e CA-28
  Então as cotações de SF-1 têm chave igual ao id de SF-1 e o correlationId de SF-1
  E os rastreios de FS-1 têm chave "PED-1001", o correlationId de FS-1 e sequências 1 a N sem repetição nem buraco

# CA-42
Cenário: CNH nos eventos
  Em todos os rastreio_atualizado do tipo VIAGEM_ALOCADA publicados nos CAs
  Então motorista.cnhMascarada casa com ^\*+\d{4}$ e nenhum payload contém o número completo da CNH
```

## 12. Matriz de rastreabilidade

| Requisito | Regras | Interfaces | Critérios de aceitação |
|---|---|---|---|
| RF-01 | RN-01 a RN-06 | `solicitacao_frete_criada`, `cotacao_recebida` | CA-01 a CA-06 |
| RF-02 | RN-14 | API-04, API-05, API-09 | CA-07, CA-08 |
| RF-03 | RN-17 | API-06 | CA-09, CA-10 |
| RF-04 | RN-15, RN-16 | API-07 | CA-11 a CA-13 |
| RF-05 | RN-02, RN-05, RN-07 a RN-09, RN-23 | API-08, `cotacao_recebida` | CA-14 a CA-20 |
| RF-06 | RN-18, RN-19 | API-10 a API-13 | CA-21 a CA-23 |
| RF-07 | RN-18, RN-19 | API-14 a API-17 | CA-24 a CA-26 |
| RF-08 | RN-10, RN-11 | `frete_selecionado`, `rastreio_atualizado` | CA-27, CA-29 a CA-31 |
| RF-09 | RN-12, RN-13 | Rotina de viagens, `rastreio_atualizado` | CA-28, CA-32. Sem CA de erro: a rotina não recebe entrada; o cancelamento está no RF-10 |
| RF-10 | RN-20 | `pedido_atualizado` | CA-31, CA-33 |
| RF-11 | RN-21 | `relogio_ajustado`, API-07 | CA-34 |
| RF-12 | — | API-01 a API-03 | CA-35. Sem CA de erro: rotas públicas sem entrada |
| RF-13 | RN-22 | Todos os tópicos consumidos, `transportadoras.dlt` | CA-36 (e CA-06, CA-30, CA-34) |
| RNF-01 a RNF-10 | — | Todas | CA-37 a CA-42; RNF-08 a RNF-10 por inspeção, como os CA-70 a CA-72 da ESP-LOG-001 |

O CA-28 vem depois do CA-27 no RF-09 porque depende da escala. Os atributos internos da viagem (`marco_*`, `atraso_revelado`, `parada_publicada`, `proximo_passo_em`) são verificados pelo comportamento (CA-28, CA-32).

## 13. Premissas, decisões e questões em aberto

| ID | Tipo | Descrição | Decisão |
|---|---|---|---|
| Q-01 | Premissa | Serviço já implementado (versão 0.3.0). | Como na ESP-LOG-001 (Q-01): CAs verificados como caixa-preta no ambiente, com os eventos de entrada publicados pelo QA. |
| Q-02 | Decisão (D18) | Relógio só anda para a frente. | Como na ESP-LOG-001 (Q-02). |
| Q-03 | Decisão (D7) | Transportadoras reais ou simuladas. | Simuladas, com parâmetros fixos nos seeds (Apêndice A), mais a Rodovia Sul, não simulada, para a cotação digitada (D3). |
| Q-04 | Decisão (D20) | Transportadora sem frota. | Não cota. Se a frota acabar entre a cotação e a escolha, recusa a viagem, e a logística passa para a próxima cotação (ESP-LOG-001, RF-12). |
| Q-05 | Decisão (D8 a D10) | Posição do caminhão. | Simulada pelo relógio do módulo, em linha reta, com passos de 30 s reais. **Depende do professor (P1).** |
| Q-06 | Decisão (D12) | Tópico `rastreio_atualizado`. | Novo; **depende da Infraestrutura (P3)**. |
| Q-07 | Decisão | O atraso só aparece a 60% do caminho. | Representa o motorista percebendo o atraso na estrada; antes disso, a previsão é a planejada. |
| Q-08 | Decisão | `SEM_TRANSPORTADORA` com dois status. | Mantido como implementado (§10). Uma versão futura pode unificar em 403; mudar quebra a tela atual. |
| Q-09 | Decisão | Pedido cancelado aparece como cancelado mesmo para a vencedora. | Corrigido nesta versão (RN-16). Antes, a vencedora via "VENCEU". |
| Q-10 | Decisão | Alteração com CNH ou placa de outro cadastro. | 409, como no cadastro. Corrigido nesta versão (antes respondia 500). |
| Q-11 | Decisão | Ranking: transportadora com 0% no prazo fica acima das que não têm histórico. | Mantido: sem histórico vai para o fim (`NULLS LAST`). |
| Q-12 | Decisão | Motorista com CNH vencida pode ser cadastrado. | Sim; só não é escalado nem conta como frota livre. |

### 13.1 Casos de borda obrigatórios

| Caso de borda | Decisão |
|---|---|
| String vazia ou só com espaços em campos obrigatórios | Na API, `nome` do motorista e `tipo` do veículo seguem só o tamanho mínimo (espaços contam). `observacoes` vazia vira `null`. Nos eventos, como na ESP-LOG-001. |
| Cabeçalho opcional presente porém vazio | `X-Correlation-Id` vazio equivale a ausente. |
| Mensagem duplicada **e** inválida | Como na ESP-LOG-001 (13.1). |
| Campo de chave/ID com tipo inesperado | Nos eventos → DLT pelo contrato. Na rota, ids são texto; inexistente → 404. |
| Data/hora sem fuso horário | `validaAte` da API-08 → Brasília. Nos eventos → UTC (banco). |
| Falha da porta de publicação / banco | Como na ESP-LOG-001 (13.1). |
| Rotas e métodos fora do contrato | 404 `NAO_ENCONTRADO` e 405 `METODO_NAO_PERMITIDO`, em RFC 7807. |
| `frete_selecionado` que chega antes de a solicitação ser recebida | A solicitação não existe aqui → DLT `"Solicitação desconhecida"`. A logística sempre publica `solicitacao_frete_criada` antes, pela outbox, em ordem. |
| Duas cotações digitadas simultâneas da mesma transportadora | A solicitação é travada (`FOR UPDATE`) na cotação digitada: a segunda recebe 409 `COTACAO_JA_ENVIADA`. |
| Relógio muito acelerado | Um passo pode publicar `PARADA`, `PREVISAO_ATUALIZADA` e `ENTREGA_REALIZADA` juntos, com os instantes em que teriam acontecido (RN-12). |

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
| 1.0 | 2026-11-10 | Grupo 5 | Criação, a partir do serviço implementado e de respostas reais do ambiente. Corrigidos no código ao escrever: alteração de motorista ou veículo com CNH ou placa duplicada (500 → 409) e situação da carga de pedido cancelado ("VENCEU" → "CANCELADA"). |

## Apêndice A — Seeds do ambiente de teste

Dados fictícios (migrações 900 a 902). Não aplicar no ambiente do kit sem combinar com o grupo de Banco de Dados.

**Transportadoras e regras de cotação**

| id | empresa_id | nome | simulada | tipos_carga | ufs_atendidas | prob_atraso | preco_minimo | tarifa_km | tarifa_ton | fator_tipo_carga | km_por_dia | prazo_base_dias |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| transp-expressa | emp-transp-expressa | Expressa Cargas Rápidas | sim | CARGA_SECA, GRANEL | todas | 0.050 | 1500.00 | 3.80 | 45.00 | GRANEL 1.00; CARGA_SECA 1.10 | 750 | 1 |
| transp-economica | emp-transp-economica | Econômica Transportes | sim | CARGA_SECA, GRANEL | todas | 0.350 | 900.00 | 2.60 | 30.00 | GRANEL 1.00; CARGA_SECA 1.10 | 400 | 2 |
| transp-graneleira | emp-transp-graneleira | Graneleira Centro-Oeste | sim | GRANEL | MT, GO, MS, SP, PR | 0.150 | 1100.00 | 3.00 | 35.00 | GRANEL 1.00 | 550 | 1 |
| transp-frio | emp-transp-frio | Frio Sul Refrigerados | sim | REFRIGERADO | todas | 0.100 | 2000.00 | 4.50 | 60.00 | REFRIGERADO 1.35 | 600 | 1 |
| transp-perigosos | emp-transp-perigosos | Segura Cargas Especiais | sim | PERIGOSO | todas | 0.100 | 2500.00 | 5.20 | 80.00 | PERIGOSO 1.60 | 500 | 2 |
| transp-rodovia | emp-transp-rodovia | Rodovia Sul Transportes | não | GRANEL, CARGA_SECA | todas | 0.200 | 1000.00 | 3.20 | 40.00 | — | 600 | 1 |

Telefones: Expressa (11) 4000-1001, Econômica (11) 4000-1002, Graneleira (65) 4000-1003, Frio Sul (41) 4000-1004, Segura (31) 4000-1005, Rodovia (41) 4000-1006. Todas ativas.

**Motoristas** (todos categoria E)

| id | transportadora | nome | telefone | cnh_numero | cnh_validade |
|---|---|---|---|---|---|
| mot-exp-1 | transp-expressa | Carlos Mendes | (65) 99988-7766 | 03345678910 | 2029-05-10 |
| mot-exp-2 | transp-expressa | Ana Paula Ribeiro | (65) 99911-2233 | 04456789021 | 2028-09-22 |
| mot-eco-1 | transp-economica | José Almeida | (11) 98877-6655 | 05567890132 | 2027-12-01 |
| mot-eco-2 | transp-economica | Marcos Vieira | (11) 97766-5544 | 06678901243 | 2030-03-15 |
| mot-gra-1 | transp-graneleira | Luciana Prado | (65) 99655-4433 | 07789012354 | 2029-01-30 |
| mot-gra-2 | transp-graneleira | Roberto Nunes | (66) 99544-3322 | 08890123465 | 2028-06-18 |
| mot-fri-1 | transp-frio | Fernanda Costa | (41) 99433-2211 | 09901234576 | 2029-08-08 |
| mot-fri-2 | transp-frio | Paulo Henrique Dias | (41) 99322-1100 | 10012345687 | 2027-11-11 |
| mot-per-1 | transp-perigosos | Ricardo Gomes | (31) 99211-0099 | 11123456798 | 2030-02-02 |
| mot-per-2 | transp-perigosos | Sandra Lima | (31) 99100-9988 | 12234567809 | 2028-10-10 |
| mot-rod-1 | transp-rodovia | Eduardo Pereira | (41) 99877-1122 | 13345678901 | 2029-04-20 |
| mot-rod-2 | transp-rodovia | Juliana Martins | (41) 99766-2233 | 14456789012 | 2028-12-05 |

**Veículos**

| id | transportadora | placa | tipo | capacidade_kg | tipos_carga | categoria_cnh_exigida |
|---|---|---|---|---|---|---|
| vei-exp-1 | transp-expressa | ABC1D23 | CARRETA_GRANELEIRA | 32000 | GRANEL | E |
| vei-exp-2 | transp-expressa | BRA2E34 | CARRETA_SIDER | 28000 | CARGA_SECA, GRANEL | E |
| vei-eco-1 | transp-economica | QWE3F45 | CARRETA_GRANELEIRA | 30000 | GRANEL | E |
| vei-eco-2 | transp-economica | RTY4G56 | TRUCK_BAU | 14000 | CARGA_SECA | C |
| vei-gra-1 | transp-graneleira | UIO5H67 | BITREM_GRANELEIRO | 37000 | GRANEL | E |
| vei-gra-2 | transp-graneleira | PAS6J78 | CARRETA_GRANELEIRA | 30000 | GRANEL | E |
| vei-fri-1 | transp-frio | DFG7K89 | CARRETA_FRIGORIFICA | 26000 | REFRIGERADO | E |
| vei-fri-2 | transp-frio | HJK8L90 | TRUCK_FRIGORIFICO | 12000 | REFRIGERADO | C |
| vei-per-1 | transp-perigosos | ZXC9M01 | CARRETA_TANQUE | 30000 | PERIGOSO | E |
| vei-per-2 | transp-perigosos | VBN0N12 | TRUCK_TANQUE | 15000 | PERIGOSO | C |
| vei-rod-1 | transp-rodovia | RSL1A23 | CARRETA_GRANELEIRA | 30000 | GRANEL | E |
| vei-rod-2 | transp-rodovia | RSL2B34 | CARRETA_SIDER | 28000 | CARGA_SECA, GRANEL | E |
