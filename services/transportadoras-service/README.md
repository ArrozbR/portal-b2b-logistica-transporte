# transportadoras-service (porta 8109, schema `transportadoras`)

Ainda sem código.

Dono das transportadoras, das cotações que elas emitem e da viagem:

- consome `solicitacao_frete_criada`, `frete_selecionado` e `empresa_cadastrada`;
- publica `cotacao_recebida` e `rastreio_atualizado` (novo);
- mantém o cadastro operacional, o motor de cotação simulada, o simulador de viagem e o ranking de desempenho.

Detalhes em [Arquitetura proposta](../../docs/02-arquitetura-proposta.md), seções 2.2, 5.3, 6.1 e 8.2. O ponto de partida será o boilerplate do kit, com as correções da [Análise do kit](../../docs/04-analise-do-kit.md).
