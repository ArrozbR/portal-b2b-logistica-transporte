# 14. Revisão visual das telas

Em 23/11/2026, as telas foram revistas uma a uma, com prints de cada perfil (comprador, transportadora e administrador) e dados realistas: uma entrega em viagem, uma entregue, solicitações esperando escolha e canceladas. As mudanças mantêm a identidade do mockup do grupo de UX (paleta verde, cartões, linha do tempo) e mexem no que atrapalhava o uso.

## 1. O que foi encontrado e o que mudou

| Tela | Problema | Mudança |
|---|---|---|
| Todas | Sem destaque de foco: quem usa o teclado não via onde estava | Contorno verde em tudo que recebe foco (`:focus-visible`) |
| Todas | Abaixo de 900 px (celular, tablet), o menu sumia e não havia como trocar de tela | O menu vira uma barra no topo; as tabelas rolam dentro do cartão, sem a página rolar para o lado |
| Todas | Em monitor largo, o conteúdo ficava encostado à esquerda | Conteúdo centralizado (até 1400 px) |
| Todas | Texto pequeno (14 px; tabelas com 12 a 13 px) e botões sem reação ao passar o mouse | Texto base de 15 px, tabelas com 14 px; botões com estado de passar o mouse e de clique; animações desligadas para quem pede menos movimento no sistema |
| Login | Título desalinhado; dica de demonstração colada no botão | Título alinhado; separador "ou entre com um usuário de demonstração" |
| Solicitações | Linhas clicáveis sem nenhum sinal disso; as que esperam a escolha do comprador não se destacavam | Linhas que pedem escolha ficam destacadas, com o botão **Comparar e escolher**; as outras têm **Ver ›**; os filtros mostram quantas há em cada um |
| Comparação | Os três botões "Escolher" com o mesmo peso; barra de pontualidade de 0% parecia quebrada; dois verdes no gráfico | Só a cotação recomendada tem o botão cheio (as outras, contorno); barra com trilho visível; "Escolhida" em azul no gráfico |
| Entregas | Canceladas mostravam previsão de chegada e barra vazia | Canceladas mostram "—"; cada linha tem **Acompanhar ›**; filtros com contagem |
| Rastreio | "Reportar ocorrência" com o botão principal, como se fosse a ação mais importante | Botão secundário (contorno) |
| Minha frota | Não dava para editar motorista ou veículo (a API já permitia); "Desativar" vermelho em toda linha; ícone de pessoa no menu | Botão **Editar**, que abre o formulário preenchido; "Desativar" discreto; ícone de caminhão |
| Cargas (transportadora) | Painel "Enviar cotação" vazio sem orientação | Ícone e instrução: clicar numa carga "Aceitando cotações" |
| Sino | Contador espremido sobre o ícone | Contador no canto, com contorno |

## 2. Onde está cada coisa

| Arquivo | O que mudou |
|---|---|
| `frontend/assets/portal.css` | Foco, botões (`secundario`, `fantasma`), tabelas, filtros com contagem, login, celular |
| `frontend/assets/portal.js` | Separador do login, ícone da frota, ícone de lápis |
| `frontend/assets/solicitacoes.js`, `entregas.js` | Destaque, chamada para ação, contagem nos filtros, canceladas |
| `frontend/assets/comparacao.js` | Hierarquia dos botões, cores do gráfico |
| `frontend/assets/frota.js` | Editar motorista e veículo |
| `frontend/assets/fretes.js`, `rastreio.js`, `ranking.js` | Painel vazio, botão secundário, tabela sem cursor de clique |

## 3. Perguntas que o professor pode fazer

**Por que destacar só as solicitações que esperam a escolha?**
É a única coisa que o comprador precisa fazer na tela, e tem prazo (12 h). Destacar tudo seria o mesmo que não destacar nada.

**Por que só um botão cheio na comparação?**
O botão cheio diz "esta é a ação principal". Com três iguais, o comprador não sabe qual o sistema recomenda. A recomendada (pela regra do menor preço) fica cheia; as outras continuam a um clique.

**Como vocês testaram no celular?**
Abrindo cada tela num quadro de 390 px de largura (o tamanho de um celular comum) e conferindo que a página não rola para o lado: a largura da página ficou igual à da tela.
