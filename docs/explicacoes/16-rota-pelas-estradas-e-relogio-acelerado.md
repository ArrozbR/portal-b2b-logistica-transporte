# 16. Rota pelas estradas, relógio acelerado e ajustes do mockup

Em 23/11/2026, três pedidos: o professor achou a rota em linha reta pouco real; o relógio acelerado "não atualizava direito, nem o botão de atualizar"; e os pontos que faltavam do mockup publicado pelo grupo de UX.

## 1. Rota pelas estradas (D9)

**Antes:** a rota era uma linha reta de 60 pontos entre as duas cidades.

**Agora:** a rota segue as estradas.

1. Uma ferramenta (`comum/comum/ferramentas/gerar_estradas.py`) liga cada uma das 132 cidades da tabela às 5 vizinhas mais próximas e pede ao **OSRM**, um motor de rotas que usa o mapa do OpenStreetMap, o caminho de carro de cada ligação. São 401 ligações.
2. O traçado de cada ligação é simplificado (de ~2.500 pontos para ~40, sem mudar o desenho) e gravado em `comum/comum/dados/estradas.json` (277 KB). Esse arquivo vai para o repositório.
3. Quando uma viagem começa, o serviço de transportadoras procura o caminho mais curto, em km de estrada, entre a origem e o destino, juntando esses trechos (algoritmo de Dijkstra, o mesmo dos GPS).

Sorriso a Santos, por exemplo, passa por Cuiabá e Uberlândia: 216 pontos e 2.115 km.

| Situação | O que acontece |
|---|---|
| Ligação com volta absurda (mais de 3 vezes a linha reta) | Descartada ao gerar o arquivo. Foram 7, todas travessias de rio (Macapá, Santarém, Barcarena) |
| Caminho mais que o dobro da distância estimada (Belém a Macapá, que na vida real se faz de balsa) | A rota volta a ser a linha reta |
| Arquivo ausente | A rota volta a ser a linha reta |

**Por que não chamar o OSRM a cada viagem?** A demonstração ficaria dependendo de internet e de um servidor público com limite de uma consulta por segundo. Com o arquivo no repositório, a rota sai na hora, é sempre a mesma e nada sai da rede da turma.

**O preço mudou?** Não. O preço e o prazo continuam usando a distância estimada (linha reta × 1,3, D15); senão, todos os valores das especificações mudariam. Na rota do cenário a diferença é de 1%; em outras passa de 20% (Rio Verde a Paranaguá).

**Um tropeço ao gerar:** o Python desta máquina recusava o certificado do servidor ("certificate has expired"), e a ferramenta ficou mais de meia hora tentando de novo cada ligação. A verificação do certificado não foi desligada: a ferramenta passou a baixar pelo `curl` do sistema, que usa os certificados do Windows, e agora para depois de 5 falhas seguidas.

## 2. Relógio acelerado (D10)

**O defeito:** a viagem dava um passo a cada 30 segundos **reais**, qualquer que fosse a velocidade do relógio. Em 3600×, 30 s reais são 30 horas do módulo: o caminhão saltava 30 h de estrada de uma vez, e por até 30 s nenhuma consulta (nem o botão "Atualizar localização") tinha posição nova para mostrar. Além disso, o relógio do topo da tela só mudava a cada 5 s, pulando 5 horas.

**A correção:**

| Parte | Antes | Agora |
|---|---|---|
| Passo da viagem | 30 s reais | 30 min do módulo, entre 2 s e 30 s reais |
| Mudança de velocidade | O passo já marcado esperava até 30 s | As viagens dão o próximo passo na hora |
| Telas (rastreio, entregas, comparação, cargas) | Consulta a cada 5 s | 5 s, ou 2 s com o relógio acelerado, e na hora quando a velocidade muda |
| Relógio do topo | Mudava a cada 5 s | Anda a cada segundo, calculado na tela, e acerta com o serviço a cada 5 s |

| Relógio | Passo real | Estrada por passo |
|---|---|---|
| 1× | 30 s | 30 s |
| 360× | 5 s | 30 min |
| 3600× | 2 s | 2 h |

Conferido no navegador: em 3600×, o relógio do topo anda 1 hora por segundo e o progresso sobe a cada 2 s (de 5% para 9% em 10 s).

## 3. Ajustes do mockup do UX

| Ponto | Decisão |
|---|---|
| Telefone e CNH do motorista | Dependem do perfil. O **comprador** vê o nome do motorista e o contato da transportadora (como no mockup); o **fornecedor** vê também o telefone, porque combina a coleta; o **admin** vê tudo. O corte é feito no serviço, e não só na tela: quem não pode ver recebe `null` na API e "CNH -" no comprovante de coleta |
| Validade da cotação | Só com a data ("último dia"), como no mockup: vale até 23:59:59 desse dia, no horário de Brasília. A API continua aceitando data e hora |
| Prazo de entrega da carga | A transportadora vê "Entrega desejada" (vem do pedido, no `solicitacao_frete_criada`). Uma entrega depois dessa data é aceita, com uma confirmação antes de enviar: a data é um desejo do comprador, e ele decide na comparação |

## 4. Onde está cada coisa

| Arquivo | O que mudou |
|---|---|
| `comum/comum/ferramentas/gerar_estradas.py`, `comum/comum/dados/estradas.json` | Ferramenta e traçado das estradas |
| `comum/comum/geo.py` | `rota_por_estrada` (Dijkstra) e `rota_da_viagem` |
| `services/transportadoras-service/transportadoras/simulacao.py`, `servico.py` | Passo pela hora do módulo; passo na hora depois do ajuste do relógio; rota pelas estradas |
| `services/transportadoras-service/transportadoras/api.py`, `migracoes/005_entrega_desejada.sql` | Validade só com a data; entrega desejada |
| `services/logistica-service/logistica/regras.py`, `api.py`, `servico.py` | Dados do motorista por perfil; `dataEntregaDesejada` no evento |
| `frontend/assets/portal.js` | Relógio que anda sozinho; `Portal.repetir` |
| `frontend/assets/rastreio.js`, `fretes.js`, `entregas.js`, `comparacao.js` | Atualização pelo relógio; cartão do motorista; formulário de cotação |
| ESP-LOG-001 1.7, ESP-TRP-001 1.4 | RN-37, CA-91; RN-25, RN-26, CA-45, CA-46 |
| `testes_integracao/test_perfis_e_rota.py` | Os três ajustes, conferidos no banco e na API |

## 5. Perguntas que o professor pode fazer

**De onde vêm as estradas?**
Do OpenStreetMap, um mapa aberto, pelo OSRM, um motor de rotas livre. A ferramenta pediu o traçado uma vez e guardou no repositório, com a fonte e a licença (ODbL) escritas no arquivo.

**Por que juntar trechos entre cidades vizinhas, e não pedir cada par de cidades?**
Com 132 cidades, são mais de 8.600 pares: várias horas no limite de uma consulta por segundo, e um arquivo bem maior. Com as vizinhas são 401 consultas, e o caminho mais curto pelos trechos fica próximo do caminho real.

**Por que o passo da viagem tem mínimo de 2 s?**
Para não sobrecarregar o Kafka e o banco com o relógio muito acelerado. Em 100.000×, um passo a cada 30 min do módulo seria 50 por segundo para cada viagem.

**Como as duas cópias do serviço sabem que o relógio mudou?**
Pelo evento `relogio_ajustado`. Quem o consome grava o relógio novo e, na mesma transação, marca as viagens em andamento para dar o próximo passo já. As duas cópias leem o mesmo banco, então a próxima que passar faz o passo.

**Por que esconder o telefone do motorista do comprador?**
É dado pessoal de quem não é parte do contrato do comprador (o motorista trabalha para a transportadora). O comprador fala com a transportadora; o fornecedor precisa combinar a coleta, então vê o telefone. É o mínimo necessário para cada um, a ideia da LGPD.
