# logistica-service (porta 8108, schema `logistica`)

Ainda sem código.

Dono da solicitação de frete, da escolha, da entrega, do rastreio, das notificações e do relógio do módulo:

- consome `pedido_criado`, `pedido_atualizado`, `cotacao_recebida` e `rastreio_atualizado` (novo);
- publica `solicitacao_frete_criada`, `frete_selecionado`, `entrega_concluida` (novo), `frete_indisponivel` (novo) e `relogio_ajustado` (novo);
- expõe as APIs de solicitações, comparação e escolha do frete, entregas, rastreio, documentos, notificações e relógio.

Detalhes em [Arquitetura](../../docs/02-arquitetura-proposta.md), seções 2.1 e 10.1. O ponto de partida será o boilerplate do kit, com as correções da [Análise do kit](../../docs/04-analise-do-kit.md).
