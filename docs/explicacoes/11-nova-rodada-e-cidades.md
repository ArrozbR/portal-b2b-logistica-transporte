# 11. Nova rodada de cotação e mais cidades

Esta parte responde à [issue #1](https://github.com/ArrozbR/portal-b2b-logistica-transporte/issues/1) que o grupo de Pedidos abriu no nosso repositório em 23/11/2026, com base na especificação deles ([ESP-PED-001 v2.1](https://github.com/brunnoalexcson/portal-b2b-mercado-negociacao-pedidos/blob/main/docs/pedidos/requisitos.md)). Ela tem duas mudanças:

1. **Frete indisponível não cancela mais o pedido** (decisão D27): a logística abre uma nova rodada de cotação.
2. **Lista de cidades de 35 para 132**, com todas as capitais. O exemplo do grupo de Pedidos usa Anápolis (GO), que não estava na lista.

## 1. Frete indisponível: nova rodada

### O que mudou

O frete fica indisponível em dois casos: nenhuma transportadora cotou em 12 h, ou nenhuma das que cotaram tinha caminhão livre. Antes, o grupo de Pedidos cancelava o pedido (o nosso `pedidos-falso` fazia isso).

Na especificação deles, isso mudou. A venda é concluída no fechamento da negociação, e nessa hora o estoque já teve baixa. Cancelar exigiria devolver o estoque, o que está fora da versão deles. Então o pedido **continua valendo** e espera uma nova cotação.

| | Antes | Agora |
|---|---|---|
| Frete indisponível | Pedidos cancelava o pedido | O pedido continua; a logística abre uma nova solicitação para ele |
| Solicitações por pedido | Uma | Uma por **rodada** (1, 2, 3…) |
| `tentativa` da entrega | Única por pedido | Única por solicitação: recomeça em 1 em cada rodada |
| Notificação | "O pedido será cancelado" | "O pedido continua valendo: uma nova cotação foi aberta" |

### Como funciona

```text
Rodada 1: aberta ──► sem cotação ──► 12 h depois: INDISPONIVEL
                                               │  (mesma transação)
                                               ├──► frete_indisponivel (para Pedidos)
                                               └──► Rodada 2: aberta ──► solicitacao_frete_criada (rodada 2)
```

A rodada nova copia a carga da anterior (produto, peso, origem, destino, comprador, fornecedor, valor). O resto recomeça: novo id, nova hora de abertura, novo prazo de 12 h, nova rodada de 10 s. As transportadoras cotam de novo, e quem agora tem caminhão livre pode cotar.

Tudo acontece **na mesma transação** do `frete_indisponivel`. Se algo falhar, nem o aviso nem a rodada nova são gravados. As duas cópias do serviço não abrem a rodada 2 duas vezes, porque o banco só aceita uma solicitação por (pedido, rodada).

### Por que não há limite de rodadas

Um pedido que nenhuma transportadora consegue levar (por exemplo, 30 t de carga refrigerada) fica tentando. Isso não vira um laço rápido: cada rodada sem cotação dura pelo menos 10 s reais e as 12 h do relógio do módulo. O grupo de Pedidos não definiu um limite. Isso está registrado como limitação no relatório técnico.

## 2. Mais cidades

A simulação calcula a distância e desenha o mapa a partir de uma tabela de cidades com coordenadas. Uma cidade fora da tabela faz o pedido ir para a DLT, a fila de erros. O exemplo do grupo de Pedidos usa **Anápolis/GO**, que não estava na lista.

A tabela foi de 35 para **132 cidades**, de todas as 27 unidades da federação:

| Grupo | Exemplos |
|---|---|
| Todas as capitais | Brasília, Palmas, Belém, Manaus, Fortaleza, Florianópolis… (Goiânia já estava) |
| Goiás e DF | Anápolis, Aparecida de Goiânia, Itumbiara, Catalão, Mineiros, Cristalina |
| Polos do agronegócio | Tangará da Serra, Nova Mutum, Chapadão do Sul, Barreiras, Uruçuí, Patos de Minas |
| Cidades médias | Juiz de Fora, Maringá, Caxias do Sul, São José do Rio Preto, Campina Grande |
| Portos | São Francisco do Sul, Barcarena, Itaguaí, Itacoatiara |

As coordenadas são aproximadas (centro da cidade), como as que já existiam. Conferimos que a parada da viagem de referência da ESP-TRP-001 continua sendo "Jataí - GO": nenhuma cidade nova ficou mais perto daquele ponto.

## 3. Onde está cada coisa

| Arquivo | O que mudou |
|---|---|
| `comum/comum/geo.py` | 97 cidades novas |
| `services/logistica-service/migracoes/006_nova_rodada.sql` | Coluna `rodada`; solicitação única por (pedido, rodada); entrega única por (solicitação, tentativa) |
| `services/logistica-service/logistica/servico.py` | `_reabrir` (abre a rodada seguinte), `pedido_da_solicitacao`; cancelamento age na rodada mais recente |
| `services/logistica-service/logistica/notificacoes.py` | Textos sem "será cancelado" |
| `services/logistica-service/logistica/api.py` | Campo `rodada` nas solicitações; a entrega do pedido vem da rodada mais recente |
| `comum/comum/contratos/solicitacao_frete_criada.schema.json` | Campo `rodada` (o schema do grupo de Pedidos aceita campos extras) |
| `comum/comum/ferramentas/pedidos_falso.py` | Não cancela no `frete_indisponivel`; o fechamento do leilão sai como `AGUARDANDO_FRETE`, como no grupo de Pedidos |
| `frontend/assets/solicitacoes.js` | Mostra "2ª cotação" e "Indisponível; nova cotação aberta" |
| `testes_integracao/test_frete_indisponivel.py` | Carga refrigerada de 30 t sem cotação → rodada 1 indisponível, rodada 2 aberta, mesmo `correlationId`, pedido não cancelado |
| ESP-LOG-001 1.4 | RF-21, RN-36, CA-87, CA-88, Q-13 e Q-14, Apêndice A |

## 4. Perguntas que o professor pode fazer

**Por que a logística reabre, e não o grupo de Pedidos?**
Quem sabe que o frete falhou e tem os dados da carga é a logística. O grupo de Pedidos só recebe o aviso. Se eles tivessem que pedir uma nova cotação, seria preciso um evento novo, do pedido para a logística, só para isso.

**As duas cópias do serviço podem abrir a rodada 2 ao mesmo tempo?**
Não. A rodada nova é aberta na mesma transação que marca a anterior como indisponível, e a rotina de prazos pega cada solicitação com trava (`FOR UPDATE SKIP LOCKED`). Mesmo assim, o banco só aceita uma solicitação por (pedido, rodada): uma segunda tentativa seria ignorada.

**Por que a `tentativa` recomeça em 1?**
Foi o que o grupo de Pedidos pediu. Para eles, a `tentativa` conta as trocas de transportadora **dentro** de uma solicitação. Uma solicitação nova é uma cotação nova, e a contagem recomeça.

**E se a transportadora mandar uma cotação para a rodada antiga?**
A rodada antiga está `INDISPONIVEL`: a cotação é gravada como `RECUSADA_TARDE` e não pode ser escolhida, como qualquer cotação atrasada.

**Por que não pegar todas as cidades do Brasil?**
São 5.570 municípios. Para a simulação, bastam as capitais e os polos de carga. A base completa do IBGE é a melhoria natural e está registrada nas limitações.
