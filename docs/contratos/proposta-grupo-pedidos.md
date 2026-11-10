# Proposta de contrato: Pedidos ↔ Logística

**De:** Grupo 5, Logística e Transporte (`logistica-service`, `transportadoras-service`)
**Para:** Grupo 4, Mercado, Negociação e Pedidos (`pedidos-service`)
**Contato do Grupo 5:** _(preencher)_
**Resposta pedida até:** 16/11/2026

## Por que estamos pedindo

A logística começa a trabalhar quando recebe o `pedido_criado`. Com o payload atual do kit (`pedidoId`, `negociacaoId`, `compradorId`, `fornecedorId`, `produtoId`, `quantidade`, `valorTotal`, `status`), não conseguimos cotar o frete nem mostrar a entrega no mapa: falta saber **de onde sai, para onde vai, o que é e quanto pesa**.

Também precisamos que o pedido mude de status pelos nossos eventos, porque hoje o `pedidos-service` só muda status por `PATCH` HTTP, e o guia do kit pede que o fluxo avance por eventos.

## 1. Campos a incluir no `pedido_criado`

| Campo | Tipo | Obrigatório | Exemplo | De onde vem |
|---|---|:---:|---|---|
| `produtoNome` | texto | sim | `"Soja em grão"` | Produto |
| `unidade` | texto | sim | `"KG"` | Produto (`KG`, `TON`, `UN`, `CX`, `L`) |
| `pesoKg` | número | sim | `24000` | Calculado de `quantidade` e `unidade` |
| `tipoTransporte` | texto | sim | `"GRANEL"` | Produto (`GRANEL`, `REFRIGERADO`, `CARGA_SECA`, `PERIGOSO`) |
| `origem.cidade`, `origem.uf` | texto | sim | `"Sorriso"`, `"MT"` | Fornecimento |
| `destino.cidade`, `destino.uf` | texto | sim | `"Santos"`, `"SP"` | Demanda ou cadastro do comprador |
| `dataEntregaDesejada` | data | não | `"2026-11-20"` | Demanda |

Exemplo completo do payload:

```json
{
  "pedidoId": "ped-998811",
  "negociacaoId": "neg-7788",
  "compradorId": "emp-12",
  "fornecedorId": "emp-34",
  "produtoId": "prod-1",
  "produtoNome": "Soja em grão",
  "quantidade": 24000,
  "unidade": "KG",
  "pesoKg": 24000,
  "tipoTransporte": "GRANEL",
  "valorTotal": 192000.00,
  "origem": { "cidade": "Sorriso", "uf": "MT" },
  "destino": { "cidade": "Santos", "uf": "SP" },
  "dataEntregaDesejada": "2026-11-20",
  "status": "CRIADO"
}
```

Os campos são **adicionais**: quem já consome o `pedido_criado` (Fornecimentos) não é afetado.

## 2. Eventos da logística que o `pedidos-service` precisa consumir

| Tópico | Quando chega | O que fazer com o pedido |
|---|---|---|
| `solicitacao_frete_criada` | Logística abriu a cotação | `CRIADO` → `AGUARDANDO_FRETE` |
| `frete_selecionado` | Frete escolhido | `AGUARDANDO_FRETE` → `FRETE_SELECIONADO` e guardar transportadora, preço e prazo |
| `frete_selecionado` com `tentativa` > 1 | A transportadora escolhida não tinha caminhão e trocamos por outra | Continua `FRETE_SELECIONADO`; atualizar transportadora, preço e prazo |
| `entrega_concluida` | Caminhão chegou | `FRETE_SELECIONADO` → `ENTREGUE` |
| `frete_indisponivel` | 12 h sem cotação, ou nenhuma transportadora com caminhão | Cancelar o pedido e publicar `pedido_atualizado` com `CANCELADO` |

Todos usam a chave `pedidoId`. Payloads completos em [`03-eventos-e-integracoes.md`](../03-eventos-e-integracoes.md), seção 3.

`entrega_concluida` e `frete_indisponivel` são tópicos novos que vamos propor à Infraestrutura.

## 3. O que já consumimos de vocês

| Tópico | O que fazemos |
|---|---|
| `pedido_criado` | Abrimos a solicitação de frete |
| `pedido_atualizado` com `status: "CANCELADO"` | Cancelamos a cotação ou a entrega e liberamos motorista e caminhão |

## 4. Perguntas para vocês

1. Vocês conseguem incluir os campos da seção 1? Se algum não estiver disponível no momento da criação do pedido, qual?
2. O `pedido_atualizado` traz o novo status no campo `novoStatus`, como no boilerplate do kit?
3. Concordam que o pedido vá para `AGUARDANDO_FRETE` ao consumir `solicitacao_frete_criada`?
4. Tudo bem receber mais de um `frete_selecionado` para o mesmo pedido (campo `tentativa`)?

Quando houver acordo, transformamos esta proposta em JSON Schemas em `docs/contratos/`, e os dois grupos testam contra os mesmos schemas.
