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
| `pesoKg` | número | sim | `24000` | Calculado de `quantidade` e `unidade`: `KG` → a própria quantidade; `TON` → quantidade × 1000; `UN`, `CX` e `L` → quantidade × `pesoUnitarioKg` do produto |
| `tipoTransporte` | texto | sim | `"GRANEL"` | Produto (`GRANEL`, `REFRIGERADO`, `CARGA_SECA`, `PERIGOSO`) |
| `origem.cidade`, `origem.uf` | texto | sim | `"Sorriso"`, `"MT"` | Fornecimento |
| `destino.cidade`, `destino.uf` | texto | sim, exceto no leilão (seção 1.1) | `"Santos"`, `"SP"` | Demanda ou cadastro do comprador |
| `dataEntregaDesejada` | data | não | `"2026-11-20"` | Demanda |

Exemplo completo do payload:

```json
{
  "pedidoId": "ped-998811",
  "negociacaoId": "neg-7788",
  "compradorId": "emp-12",
  "fornecedorId": "emp-34",
  "produtoId": "prod-1",
  "fornecimentoId": "forn-55",
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

Todos esses dados já existem nos eventos do grupo de Fornecimento e Produtos (contrato de eventos 1.1, de 10/11/2026): `tipoTransporte` e `pesoUnitarioKg` em `produto_cadastrado` e `produto_atualizado`, e `origem` (`cidade` e `uf`) em `fornecimento_criado`. Eles pediram o mesmo cálculo de `pesoKg` a vocês.

### 1.1 Pedido de leilão (sem comprador no começo)

O professor definiu em 12/11/2026 (resposta ao grupo de Fornecimento e Produtos) que o pedido nasce na **abertura** do leilão ou da negociação, e que no leilão o comprador só é definido quando ele fecha. Então, num pedido de leilão, o `pedido_criado` pode vir com `compradorId` e `destino` nulos ou ausentes. Já aceitamos isso: o pedido fica guardado, e a cotação do frete **só começa no fechamento**, quando já se sabe quem compra e para onde vai a carga.

Para isso, pedimos que o fechamento do leilão publique um `pedido_atualizado` com o comprador e o destino:

```json
{
  "pedidoId": "ped-998811",
  "statusAnterior": "CRIADO",
  "novoStatus": "LEILAO_FECHADO",
  "compradorId": "emp-12",
  "destino": { "cidade": "Santos", "uf": "SP" },
  "valorTotal": 195000.00,
  "quantidade": 24000,
  "pesoKg": 24000
}
```

O nome `LEILAO_FECHADO` é só um exemplo: aceitamos qualquer status que traga `compradorId` ou `destino` (exceto `CANCELADO`). `valorTotal`, `quantidade` e `pesoKg` são opcionais e, se vierem, valem no lugar dos do `pedido_criado` (o lance vencedor). Na negociação direta, se o `pedido_criado` já vier com comprador e destino, nada muda: a cotação começa na hora.

O `fornecimentoId` do exemplo não é pedido nosso: é do grupo de Fornecimento e Produtos, que precisa dele para reservar o estoque (issue #1 do repositório deles). Os dois pedidos são compatíveis e podem entrar juntos. Pelo mesmo motivo, eles propõem os status `CANCELADO` e `VENDA_CONCLUIDA` no `pedido_atualizado`; o nosso consumidor age só no `CANCELADO` e ignora os outros.

## 2. Eventos da logística que o `pedidos-service` precisa consumir

| Tópico | Quando chega | O que fazer com o pedido |
|---|---|---|
| `solicitacao_frete_criada` | Logística abriu a cotação | `CRIADO` → `AGUARDANDO_FRETE` |
| `frete_selecionado` | Frete escolhido | `AGUARDANDO_FRETE` → `FRETE_SELECIONADO` e guardar transportadora, preço e prazo |
| `frete_selecionado` com `tentativa` > 1 | A transportadora escolhida não tinha caminhão e trocamos por outra | Continua `FRETE_SELECIONADO`; atualizar transportadora, preço e prazo |
| `entrega_concluida` | Caminhão chegou | `FRETE_SELECIONADO` → `ENTREGUE` |
| `frete_indisponivel` | 12 h sem cotação, ou nenhuma transportadora com caminhão | Não cancelar: a logística abre uma nova `solicitacao_frete_criada` para o mesmo pedido, com `rodada` + 1 e a `tentativa` recomeçando em 1 (resposta de vocês, ESP-PED-001 RN-22; nossa D27) |

Todos usam a chave `pedidoId`. Payloads completos em [`03-eventos-e-integracoes.md`](../03-eventos-e-integracoes.md), seção 3.

`entrega_concluida` e `frete_indisponivel` são tópicos novos que vamos propor à Infraestrutura.

**Resposta do grupo de Pedidos (19 e 23/11/2026, ESP-PED-001 v2.1 e issue #1 deste repositório):** a proposta foi atendida nos campos de carga. O pedido nasce sem comprador e sem destino (leilão e negociação direta); a logística ignora esse `pedido_criado` e cota a partir do `pedido_atualizado` `AGUARDANDO_FRETE`, que traz a carga completa (D26). A venda é concluída no fechamento da negociação, não no `entrega_concluida`; a entrega leva o pedido a `ENTREGUE`. O `frete_indisponivel` não cancela o pedido (D27).

## 3. O que já consumimos de vocês

| Tópico | O que fazemos |
|---|---|
| `pedido_criado` com comprador e destino | Abrimos a solicitação de frete |
| `pedido_criado` sem comprador ou destino (leilão) | Guardamos o pedido e esperamos o fechamento (seção 1.1) |
| `pedido_atualizado` com `compradorId` ou `destino` | Fechamento do leilão: abrimos a solicitação de frete |
| `pedido_atualizado` com `status: "CANCELADO"` | Cancelamos a cotação ou a entrega e liberamos motorista e caminhão; se o leilão ainda não fechou, só deixamos de esperar |

## 4. Perguntas para vocês

1. Vocês conseguem incluir os campos da seção 1? Se algum não estiver disponível no momento da criação do pedido, qual?
2. O `pedido_atualizado` traz o novo status no campo `novoStatus`, como no boilerplate do kit?
3. Concordam que o pedido vá para `AGUARDANDO_FRETE` ao consumir `solicitacao_frete_criada`?
4. Tudo bem receber mais de um `frete_selecionado` para o mesmo pedido (campo `tentativa`)?
5. Como o fechamento do leilão é avisado: um `pedido_atualizado` (com qual status?) ou outro tópico?
6. O evento do fechamento consegue trazer `compradorId` e `destino` (`{cidade, uf}`)? O destino vem da demanda do comprador: o `demanda_criada` do grupo de Compra e Demanda já traz `destino` em `{cidade, uf}`.
7. O valor e a quantidade finais (lance vencedor) vêm no fechamento?
8. Na negociação direta (sem leilão), o `pedido_criado` já chega com comprador e destino?
9. Quando o pedido vai para `AGUARDANDO_FRETE` num leilão: só depois do fechamento, quando consumirem a `solicitacao_frete_criada`?

Quando houver acordo, transformamos esta proposta em JSON Schemas em `docs/contratos/`, e os dois grupos testam contra os mesmos schemas.
