# 03. Eventos e integrações

Proposta dos payloads que o grupo publica e do que precisamos nos eventos dos outros grupos. Quando estiver aprovada, cada evento ganha um JSON Schema e um exemplo em `docs/contratos/`, como fez o grupo de Fornecimento e Produtos.

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

O `correlationId` do `pedido_criado` deve ser repassado em todos os eventos que ele origina (solicitação, cotações, seleção, rastreio e conclusão), para dar para seguir um pedido inteiro nos logs.

## 2. Tópicos do grupo

| Tópico | Produtor | Consumidores | Chave | Situação |
|---|---|---|---|---|
| `pedido_criado` | pedidos | **logística**, fornecimentos | `pedidoId` | Kit. Precisamos de campos a mais (seção 3.1) |
| `pedido_atualizado` | pedidos | **logística**, fornecimentos | `pedidoId` | Kit. Usamos só o cancelamento |
| `empresa_cadastrada` | usuarios | **transportadoras**, outros | `empresaId` | Kit. Precisamos de endereço e tipo (seção 4) |
| `solicitacao_frete_criada` | **logística** | **transportadoras** | `solicitacaoFreteId` | Kit |
| `cotacao_recebida` | **transportadoras** | **logística** | `solicitacaoFreteId` | Kit |
| `frete_selecionado` | **logística** | pedidos, **transportadoras** (novo consumidor) | `pedidoId` | Kit, com consumidor a mais |
| `rastreio_atualizado` | **transportadoras** | **logística** | `pedidoId` | **Novo** |
| `entrega_concluida` | **logística** | pedidos | `pedidoId` | **Novo** |
| `logistica.dlt`, `transportadoras.dlt` | nós | — | a do evento original | Kit |

## 3. Payloads

### 3.1 `pedido_criado` (consumido)

O exemplo do guia traz `pedidoId`, `negociacaoId`, `compradorId`, `fornecedorId`, `produtoId`, `quantidade`, `valorTotal` e `status`. Para cotar e desenhar a rota, **pedimos ao grupo de Pedidos** que inclua:

| Campo novo | Tipo | Exemplo | Para quê |
|---|---|---|---|
| `unidade` | texto | `"KG"` | Converter `quantidade` em peso |
| `pesoKg` | número | `24000` | Alternativa a `unidade`, se o produto não for medido em massa |
| `tipoTransporte` | texto | `"GRANEL"` | Filtrar transportadoras compatíveis (pendência P-27 do grupo de Produtos) |
| `origem` | objeto | `{"cidade": "Sorriso", "uf": "MT"}` | Local de coleta (vem do fornecimento) |
| `destino` | objeto | `{"cidade": "Santos", "uf": "SP"}` | Local de entrega (vem da demanda ou do cadastro do comprador) |
| `dataEntregaDesejada` | data | `"2026-11-20"` | Prazo prometido, para medir atraso (opcional) |

Se Pedidos não puder incluir esses dados, a alternativa é a logística montar cópias locais consumindo `produto_cadastrado`, `fornecimento_criado` e `empresa_cadastrada`. Funciona, mas são três consumidores a mais e o endereço do comprador continua faltando (D2).

### 3.2 `solicitacao_frete_criada` (publicado pela logística)

```json
{
  "solicitacaoFreteId": "sol-5521",
  "pedidoId": "ped-998811",
  "produtoId": "prod-1",
  "compradorId": "emp-12",
  "fornecedorId": "emp-34",
  "tipoCarga": "GRANEL",
  "pesoKg": 24000,
  "origem": { "cidade": "Sorriso", "uf": "MT", "lat": -12.5453, "lon": -55.7114 },
  "destino": { "cidade": "Santos", "uf": "SP", "lat": -23.9608, "lon": -46.3336 },
  "distanciaKm": 2091,
  "dataColetaPrevista": "2026-11-10",
  "cotacoesAte": "2026-11-09T21:30:10.000Z",
  "status": "ABERTA"
}
```

O boilerplate do kit publica só `solicitacaoFreteId`, `pedidoId` e `status`.

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
  "origemCotacao": "AUTOMATICA",
  "observacoes": null
}
```

O boilerplate do kit publica `cotacaoId`, `solicitacaoFreteId`, `transportadoraId`, `preco` e `prazoDias`. Os campos novos são opcionais para o consumidor, para não quebrar a compatibilidade `BACKWARD` do kit.

### 3.4 `frete_selecionado` (publicado pela logística)

```json
{
  "pedidoId": "ped-998811",
  "solicitacaoFreteId": "sol-5521",
  "entregaId": "ent-3301",
  "cotacaoId": "cot-8890",
  "transportadoraId": "transp-expressa",
  "preco": 9850.00,
  "prazoDias": 4,
  "dataEntregaPrevista": "2026-11-16",
  "criterio": "AUTOMATICO_MENOR_PRECO",
  "status": "FRETE_SELECIONADO"
}
```

Campos novos em relação ao boilerplate: `entregaId` (o simulador precisa dele para publicar o rastreio), `dataEntregaPrevista` e `criterio` (`AUTOMATICO_MENOR_PRECO` ou `ESCOLHA_COMPRADOR`, ver D5).

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
  "veiculo": { "placa": "ABC1D23", "tipo": "CARRETA_GRANELEIRA" },
  "ocorridoEm": "2026-11-14T10:42:00.000Z"
}
```

`tipo`: `COLETA_REALIZADA`, `POSICAO`, `PARADA`, `PREVISAO_ATUALIZADA`, `OCORRENCIA` ou `ENTREGA_REALIZADA`. No `ENTREGA_REALIZADA`, o payload traz também `noPrazo` (booleano) e `atrasoHoras`.

`sequencia` cresce a cada evento da mesma entrega. Com a chave `pedidoId`, os eventos de um pedido ficam na mesma partição e chegam em ordem; mesmo assim, a logística ignora um evento com `sequencia` menor ou igual à última aplicada, para não voltar o caminhão no mapa depois de uma reentrega.

Chave `pedidoId` (e não `entregaId`) porque cada pedido tem uma entrega só e isso alinha a chave com `frete_selecionado` e `entrega_concluida`.

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

**Por que um tópico novo:** o pedido só chega a `ENTREGUE` hoje por `PATCH` HTTP no `pedidos-service`, o que vai contra a regra do guia de não avançar o fluxo por chamada síncrona. E `pedido_atualizado` pertence ao `pedidos-service`, então não podemos publicar nele.

## 4. O que precisamos de cada grupo

| Grupo | Pedido | Prioridade |
|---|---|---|
| **Mercado, Negociação e Pedidos** | Incluir no `pedido_criado` os campos da seção 3.1 | Alta |
| | Consumir `frete_selecionado` (hoje o boilerplate só aceita `PATCH /status`) e o novo `entrega_concluida` | Alta |
| | Definir quem move o pedido de `CRIADO` para `AGUARDANDO_FRETE`. Sugestões: criar o pedido já em `AGUARDANDO_FRETE`, ou consumir `solicitacao_frete_criada` | Média |
| | Confirmar que `pedido_atualizado` traz o status `CANCELADO` | Média |
| **Fornecimento e Produtos** | Responder a P-06 e P-27 do documento deles: fechar a lista de tipos de transporte (`GRANEL`, `REFRIGERADO`, `CARGA_SECA`, `PERIGOSO`) e confirmar que o tipo chega pelo `pedido_criado` | Alta |
| | Origem do fornecimento em cidade e UF, para servir de origem da coleta | Alta |
| **Autenticação** | `empresa_cadastrada` com tipo da empresa (para cadastrar transportadoras) e endereço com cidade e UF (destino do comprador) | Alta |
| | Confirmar o nome do claim da empresa no JWT (`empresaId` no código, `empresa_id` no guia) | Média |
| **Compra e Demanda** | Se o destino vier da demanda, incluir cidade e UF de entrega em `demanda_criada` para chegar até o pedido | Média |
| **Infraestrutura** | Criar `rastreio_atualizado` e `entrega_concluida` no `init_topics.sh` e no `CONTRACTS.md` | Alta |
| | Registrar `transportadoras-service` como consumidor de `frete_selecionado` | Média |
| | Correções do kit listadas na [análise](04-analise-do-kit.md) | Alta |
| | Se usarmos SSE: `proxy_buffering off` e timeout maior em `/api/v1/logistica/entregas/` | Baixa |
| **Banco de Dados** | Aplicar a proposta de DDL dos schemas `logistica` e `transportadoras` ([arquitetura](02-arquitetura-proposta.md), seção 7) e a correção dos GRANTs (K1) | Alta |
| **UX/UI** | Alinhar o formato da API com as telas `/fretes/solicitacoes` e `/fretes/entregas/{id}`, e combinar quem implementa o mapa (D11) | Alta |
| **Teste e Qualidade** | Entregar as especificações ESP-LOG-001 e ESP-TRP-001 no modelo ERS-LLM, com critérios de aceitação | Alta |
