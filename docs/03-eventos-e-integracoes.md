# 03. Eventos e integrações

Payloads que o grupo publica e o que precisamos nos eventos dos outros grupos. Quando um contrato for aprovado, ele ganha JSON Schema e exemplo em `docs/contratos/`. O pedido ao grupo de Pedidos está pronto para envio em [`contratos/proposta-grupo-pedidos.md`](contratos/proposta-grupo-pedidos.md).

## 1. Envelope

Todos os eventos usam o envelope do kit (`services/common/events.py`):

```json
{
  "eventId": "uuid",
  "eventType": "nome_do_topico",
  "eventVersion": "1.0",
  "timestamp": "2026-11-09T21:30:00.000Z",
  "source": "logistica-service",
  "correlationId": "uuid herdado da requisição ou do evento de origem",
  "aggregateId": "chave de partição",
  "payload": {}
}
```

O guia do kit chama o campo de versão de `version`, mas o código e o `CONTRACTS.md` usam `eventVersion`. Seguimos o código.

O `correlationId` do `pedido_criado` é repassado em todos os eventos que ele origina, para dar para seguir um pedido inteiro nos logs.

O `timestamp` do envelope é a **hora real**. As datas de negócio dentro do `payload` (previsão, coleta, entrega) estão no **relógio do módulo** (D18).

## 2. Tópicos do grupo

| Tópico | Produtor | Consumidores | Chave | Situação |
|---|---|---|---|---|
| `pedido_criado` | pedidos | **logística**, fornecimentos | `pedidoId` | Kit. Precisamos de campos a mais (seção 3.1) |
| `pedido_atualizado` | pedidos | **logística**, **transportadoras** (novo consumidor), fornecimentos | `pedidoId` | Kit. Usamos só o cancelamento |
| `empresa_cadastrada` | usuarios | **transportadoras**, outros | `empresaId` | Kit. Precisamos de endereço e tipo (seção 4) |
| `solicitacao_frete_criada` | **logística** | **transportadoras** | `solicitacaoFreteId` | Kit |
| `cotacao_recebida` | **transportadoras** | **logística** | `solicitacaoFreteId` | Kit |
| `frete_selecionado` | **logística** | pedidos, **transportadoras** (novo consumidor) | `pedidoId` | Kit, com consumidor e campos a mais |
| `rastreio_atualizado` | **transportadoras** | **logística** | `pedidoId` | **Novo** (D12) |
| `entrega_concluida` | **logística** | pedidos | `pedidoId` | **Novo** (D12) |
| `frete_indisponivel` | **logística** | pedidos | `pedidoId` | **Novo** (D12) |
| `relogio_ajustado` | **logística** | **transportadoras** | `"relogio"` | **Novo** (D18), interno ao grupo |
| `logistica.dlt`, `transportadoras.dlt` | nós | — | a do evento original | Kit |

## 3. Payloads

### 3.1 `pedido_criado` (consumido)

O exemplo do guia traz `pedidoId`, `negociacaoId`, `compradorId`, `fornecedorId`, `produtoId`, `quantidade`, `valorTotal` e `status`. **Pedimos ao grupo de Pedidos** que inclua também:

| Campo novo | Tipo | Exemplo | Para quê |
|---|---|---|---|
| `produtoNome` | texto | `"Soja em grão"` | Dados da carga na tela |
| `unidade` | texto | `"KG"` | Converter `quantidade` em peso |
| `pesoKg` | número | `24000` | Peso para cotar e escalar o veículo |
| `tipoTransporte` | texto | `"GRANEL"` | Filtrar transportadoras e veículos (P-27 do grupo de Produtos) |
| `origem` | objeto | `{"cidade": "Sorriso", "uf": "MT"}` | Local de coleta (vem do fornecimento) |
| `destino` | objeto | `{"cidade": "Santos", "uf": "SP"}` | Local de entrega (vem da demanda ou do cadastro do comprador) |
| `dataEntregaDesejada` | data | `"2026-11-20"` | Prazo prometido, para medir atraso (opcional) |

`valorTotal`, que já existe, vira o **valor da carga** na tela. Plano B, se Pedidos não puder: cópias locais de `produto_cadastrado`, `fornecimento_criado` e `empresa_cadastrada` (D2).

### 3.2 `solicitacao_frete_criada` (publicado pela logística)

```json
{
  "solicitacaoFreteId": "sol-5521",
  "pedidoId": "ped-998811",
  "produtoId": "prod-1",
  "produtoNome": "Soja em grão",
  "compradorId": "emp-12",
  "fornecedorId": "emp-34",
  "tipoCarga": "GRANEL",
  "pesoKg": 24000,
  "origem": { "cidade": "Sorriso", "uf": "MT", "lat": -12.5453, "lon": -55.7114 },
  "destino": { "cidade": "Santos", "uf": "SP", "lat": -23.9608, "lon": -46.3336 },
  "distanciaKm": 2091,
  "dataColetaPrevista": "2026-11-10",
  "prazoDecisaoEm": "2026-11-10T09:30:00.000Z",
  "status": "ABERTA"
}
```

O boilerplate do kit publica só `solicitacaoFreteId`, `pedidoId` e `status`. `prazoDecisaoEm` é o fim do prazo de 12 h (D4): até lá, transportadoras podem cotar.

### 3.3 `cotacao_recebida` (publicado pelas transportadoras)

```json
{
  "cotacaoId": "cot-8890",
  "solicitacaoFreteId": "sol-5521",
  "transportadoraId": "transp-expressa",
  "preco": 9850.00,
  "prazoDias": 4,
  "dataEntregaPrevista": "2026-11-16",
  "validaAte": "2026-11-11T21:30:00.000Z",
  "origemCotacao": "SIMULADA",
  "observacoes": null
}
```

`origemCotacao`: `SIMULADA` ou `DIGITADA` (D3). Os campos novos são opcionais para o consumidor, para não quebrar a compatibilidade `BACKWARD` do kit.

### 3.4 `frete_selecionado` (publicado pela logística)

```json
{
  "pedidoId": "ped-998811",
  "solicitacaoFreteId": "sol-5521",
  "entregaId": "ent-3301",
  "tentativa": 1,
  "cotacaoId": "cot-8890",
  "transportadoraId": "transp-expressa",
  "preco": 9850.00,
  "prazoDias": 4,
  "dataEntregaPrevista": "2026-11-16",
  "criterio": "ESCOLHA_COMPRADOR",
  "status": "FRETE_SELECIONADO"
}
```

- `criterio`: `ESCOLHA_COMPRADOR` ou `AUTOMATICO_MENOR_PRECO` (D5).
- `tentativa`: começa em 1. Se a transportadora recusar a viagem por falta de motorista ou veículo (D20), a logística publica **outro** `frete_selecionado` para o mesmo pedido, com `tentativa` 2 e outra transportadora. O grupo de Pedidos precisa aceitar isso como atualização do frete, não como erro.
- `entregaId`: o simulador usa para publicar o rastreio.

### 3.5 `rastreio_atualizado` (novo, publicado pelas transportadoras)

```json
{
  "pedidoId": "ped-998811",
  "entregaId": "ent-3301",
  "transportadoraId": "transp-expressa",
  "sequencia": 14,
  "tipo": "POSICAO",
  "descricao": "Veículo em deslocamento conforme rota planejada",
  "posicao": { "lat": -20.4697, "lon": -54.6201 },
  "progresso": 0.68,
  "previsaoChegada": "2026-11-16T14:30:00.000Z",
  "ocorridoEm": "2026-11-14T10:42:00.000Z"
}
```

| `tipo` | Campos extras |
|---|---|
| `VIAGEM_ALOCADA` | `motorista` (`nome`, `telefone`, `cnhMascarada`), `veiculo` (`placa`, `tipo`), `transportadora` (`nome`, `telefone`), `coletaPrevista`, `rota` (60 pontos `[lat, lon]`) |
| `VIAGEM_RECUSADA` | `motivo` (`SEM_MOTORISTA`, `SEM_VEICULO`) |
| `COLETA_REALIZADA` | — |
| `POSICAO` | — |
| `PARADA` | `duracaoPrevistaMin` |
| `PREVISAO_ATUALIZADA` | `previsaoAnterior` |
| `OCORRENCIA` | — |
| `ENTREGA_REALIZADA` | `noPrazo`, `atrasoHoras` |

`sequencia` cresce a cada evento da mesma entrega. Com a chave `pedidoId`, os eventos de um pedido chegam em ordem; mesmo assim, a logística ignora `sequencia` menor ou igual à última aplicada, para o caminhão não voltar no mapa depois de uma reentrega.

A CNH vai **mascarada** (ex.: `"***.***.789-10"`): a logística só precisa mostrá-la, e assim o dado pessoal completo fica só com a transportadora (D19).

### 3.6 `entrega_concluida` (novo, publicado pela logística)

```json
{
  "pedidoId": "ped-998811",
  "entregaId": "ent-3301",
  "transportadoraId": "transp-expressa",
  "entregueEm": "2026-11-16T15:10:00.000Z",
  "prazoPrometido": "2026-11-16T23:59:59.000Z",
  "noPrazo": true,
  "atrasoHoras": 0
}
```

O `pedidos-service` consome e move o pedido para `ENTREGUE`.

### 3.7 `frete_indisponivel` (novo, publicado pela logística)

```json
{
  "pedidoId": "ped-998811",
  "solicitacaoFreteId": "sol-5521",
  "motivo": "SEM_COTACAO",
  "detalhe": "Nenhuma transportadora cotou em 12 h",
  "ocorridoEm": "2026-11-10T09:30:00.000Z"
}
```

`motivo`: `SEM_COTACAO` (12 h sem nenhuma cotação) ou `SEM_TRANSPORTADORA_DISPONIVEL` (todas as cotações recusaram a viagem). O `pedidos-service` consome e cancela o pedido; o `pedido_atualizado` com `CANCELADO` que ele publica fecha o ciclo na logística.

**Por que tópicos novos:** o pedido só muda de status hoje por `PATCH` HTTP no `pedidos-service`, o que vai contra a regra do guia de não avançar o fluxo por chamada síncrona. E `pedido_atualizado` pertence ao `pedidos-service`, então não podemos publicar nele.

### 3.8 `relogio_ajustado` (novo, interno ao grupo)

```json
{
  "versao": 7,
  "baseReal": "2026-11-09T21:30:00.000Z",
  "baseVirtual": "2026-11-12T08:00:00.000Z",
  "fator": 360,
  "ajustadoPor": "usr-admin-1"
}
```

Só os nossos dois serviços usam. O `transportadoras-service` grava o ajuste na sua tabela `relogio`, que as duas cópias dele leem (arquitetura, seção 7). Chave fixa `"relogio"`, para os ajustes ficarem em ordem; mesmo assim, um ajuste com `versao` antiga é ignorado.

## 4. O que precisamos de cada grupo

| Grupo | Pedido | Prioridade |
|---|---|---|
| **Mercado, Negociação e Pedidos** | Tudo o que está em [`contratos/proposta-grupo-pedidos.md`](contratos/proposta-grupo-pedidos.md): campos no `pedido_criado`, consumo de `frete_selecionado` (inclusive a troca de transportadora), `entrega_concluida` e `frete_indisponivel` | Alta |
| **Fornecimento e Produtos** | Responder a P-06 e P-27 do documento deles. A lista de tipos de transporte (`GRANEL`, `REFRIGERADO`, `CARGA_SECA`, `PERIGOSO`) e a de unidades são iguais nos dois lados (10/11/2026); falta dizer que o tipo chega pelo `pedido_criado` (plano B: consumir `produto_cadastrado` e `produto_atualizado`) | Alta |
| | Origem do fornecimento em cidade e UF, para servir de origem da coleta (P-05 deles) | Alta |
| | Peso por unidade no produto (por exemplo `pesoUnitarioKg`), porque com `UN`, `CX` e `L` não dá para calcular o `pesoKg` | Média |
| **Autenticação** | `empresa_cadastrada`: o tipo da empresa já vem em `scopes` (`CARRIER`) e a localização em `geo_lat`/`geo_lng`, mas sem cidade e UF (issue #2 de Fornecimento e Produtos) | Média |
| | Token RS256 com `tenant_id` e `active_scope` já aceito (D25). Confirmar a permissão `logistica:admin` em `permissions` para o administrador da plataforma | Alta |
| **Compra e Demanda** | Se o destino vier da demanda, incluir cidade e UF de entrega em `demanda_criada` para chegar até o pedido | Média |
| **Infraestrutura** | Criar `rastreio_atualizado`, `entrega_concluida`, `frete_indisponivel` e `relogio_ajustado` no `init_topics.sh` e no `CONTRACTS.md` | Alta |
| | Registrar `transportadoras-service` como consumidor de `frete_selecionado` e de `pedido_atualizado` | Média |
| | Correções do kit listadas na [análise](04-analise-do-kit.md) | Alta |
| **Banco de Dados** | Aplicar a proposta de DDL dos schemas `logistica` e `transportadoras` ([arquitetura](02-arquitetura-proposta.md), seção 9) e a correção dos GRANTs (K1) | Alta |
| **UX/UI** | Nenhuma pendência: o design está entregue e as telas são nossas (D11). Avisar que vamos implementá-las | Baixa |
| **Teste e Qualidade** | Entregar as especificações ESP-LOG-001 e ESP-TRP-001 no modelo ERS-LLM. Avisar que o comprador escolhe o frete e que a regra do kit vale no modo automático (D5) | Alta |
