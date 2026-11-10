# logistica-service (porta 8108, schema `logistica`)

Ainda sem código.

Dono da solicitação de frete, da seleção e da entrega:

- consome `pedido_criado`, `pedido_atualizado`, `cotacao_recebida` e `rastreio_atualizado` (novo);
- publica `solicitacao_frete_criada`, `frete_selecionado` e `entrega_concluida` (novo);
- expõe as APIs de solicitações, comparação de cotações, entregas e rastreio.

Detalhes em [Arquitetura proposta](../../docs/02-arquitetura-proposta.md), seções 2.1 e 8.1. O ponto de partida será o boilerplate do kit, com as correções da [Análise do kit](../../docs/04-analise-do-kit.md).
