# transportadoras-service (porta 8109, schema `transportadoras`)

Ainda sem código.

Dono das transportadoras, dos motoristas e veículos, das cotações e da viagem:

- consome `solicitacao_frete_criada`, `frete_selecionado`, `empresa_cadastrada` e `relogio_ajustado` (novo);
- publica `cotacao_recebida` e `rastreio_atualizado` (novo);
- mantém o cadastro operacional, os motoristas e veículos, o motor de cotação simulada, a escala do motorista, o simulador de viagem e o ranking de desempenho.

Detalhes em [Arquitetura](../../docs/02-arquitetura-proposta.md), seções 2.2, 5.4, 6 e 10.2. O ponto de partida será o boilerplate do kit, com as correções da [Análise do kit](../../docs/04-analise-do-kit.md).
