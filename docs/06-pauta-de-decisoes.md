# 06. Pauta de decisões

Registro das decisões do grupo. A primeira versão desta pauta trazia só opções e recomendações; as decisões abaixo foram tomadas numa sessão de perguntas e respostas (o "grill") e, onde o grupo não tinha como decidir, pela melhor recomendação técnica, aceita pelo grupo. Quando uma decisão for confirmada com o professor ou com outro grupo, a situação muda para **Aceita** e ela vira ADR no relatório técnico.

Situações:

- **Aceita:** decidida e sem dependência externa.
- **Aceita, depende de X:** decidida pelo grupo, mas precisa do aval de alguém de fora.
- **Em aberto:** ainda sem decisão.

## 1. Resumo

| ID | Tema | Decisão | Situação |
|---|---|---|---|
| D1 | Quantos serviços | Manter os 2 do kit | Aceita |
| D2 | Origem, destino, carga, peso, produto e valor | `pedido_criado` traz tudo; plano B com cópias locais | Aceita, depende do grupo de Pedidos |
| D3 | Quem cota | Cotações simuladas e digitadas pela transportadora | Aceita |
| D4 | Prazos da cotação | Rodada automática de 10 s; decisão em até 12 h; mínimo 1 cotação | Aceita |
| D5 | Quem escolhe o frete | O comprador, em até 12 h, ou o botão "automático"; depois disso, a regra do kit | Aceita, depende do professor (P2) |
| D6 | O que é a comparação | Cotações lado a lado e ranking de desempenho | Aceita |
| D7 | Transportadoras reais ou simuladas | Simuladas | Aceita |
| D8 | De onde vem a posição do caminhão | Simulador no `transportadoras-service` | Aceita |
| D9 | Rota no mapa | Linha interpolada; estrada como extra | Aceita |
| D10 | Atualização da tela | Posição muda a cada 30 s; a tela consulta a cada 5 s | Aceita |
| D11 | Quem faz as telas | Nós, seguindo o mockup do UX | Aceita |
| D12 | Fim e falha da entrega | Tópicos novos `rastreio_atualizado`, `entrega_concluida` e `frete_indisponivel` | Aceita, depende da Infra (P3) |
| D13 | Banco e Kafka consistentes | Outbox transacional | Aceita |
| D14 | Tarefas com hora marcada em 2 cópias | `FOR UPDATE SKIP LOCKED` | Aceita |
| D15 | Coordenadas | Tabela fixa com ~30 cidades | Aceita |
| D16 | Stack | Igual ao kit; código gerado por IA | Aceita |
| D17 | Ordem e divisão | 5 etapas; responsáveis a definir | Em aberto (responsáveis) |
| D18 | Relógio do módulo | Um relógio só, acelerável pelo administrador | Aceita |
| D19 | Motoristas e veículos | Cadastro nosso; motorista sorteado com filtros | Aceita |
| D20 | Transportadora sem motorista ou veículo | Só cota quem tem; se faltar na hora, passa para a próxima cotação | Aceita |
| D21 | Documentos da entrega | Modelos demonstrativos, sem valor fiscal | Aceita |
| D22 | Avisos a comprador e fornecedor | Notificações dentro do portal | Aceita |
| D23 | Contingência | Script que publica pedidos falsos no Kafka | Aceita |
| D24 | Repasse de conhecimento | Um arquivo de explicação por parte pronta | Aceita |

## 2. Decisões

### D1. Quantos serviços

**Decisão:** manter `logistica-service` e `transportadoras-service`, como no kit. O rastreio fica na logística; cotação, motoristas e simulação da viagem ficam nas transportadoras.

Alternativa rejeitada: um terceiro serviço só de rastreio, que exigiria porta, schema e rota novos de outros dois grupos sem ganho que pague isso.

### D2. Origem, destino, carga, peso, produto e valor

O `pedido_criado` do kit não traz nada disso, e sem esses dados não há cotação, mapa nem tela igual ao mockup.

**Decisão:** pedir que o `pedido_criado` traga todos esses campos. O formato está em [`contratos/proposta-grupo-pedidos.md`](contratos/proposta-grupo-pedidos.md). Meta: enviar ao grupo de Pedidos na semana de 09/11 e ter a resposta até 16/11.

**Plano B**, se o grupo de Pedidos recusar: a logística monta os dados sozinha, guardando cópias locais de `produto_cadastrado` (tipo de carga e nome), `fornecimento_criado` (origem) e `empresa_cadastrada` (endereço do comprador).

**Risco:** é a maior dependência do projeto. A prioridade número 1 (D17) não começa sem esse acordo.

### D3. Quem cota

**Decisão:** as duas formas.

- **Simulada:** o `transportadoras-service` calcula e publica as cotações das transportadoras compatíveis segundos depois da solicitação.
- **Digitada:** um usuário com perfil `transportadora` envia a cotação pela tela "Solicitações de frete" do mockup.

Uma cotação digitada é aceita enquanto o frete não foi escolhido. Depois da escolha, é recusada (409).

### D4. Prazos da cotação

**Decisão:**

| Prazo | Valor | O que acontece quando vence |
|---|---|---|
| Rodada automática | 10 s (o tempo do kit) | Se nenhuma cotação chegou, a solicitação vai para `SEM_COTACAO` e comprador e fornecedor são avisados |
| Prazo de decisão | 12 h a partir da abertura | Com pelo menos 1 cotação: escolha automática pela regra do kit. Sem nenhuma: o frete é dado como indisponível e o pedido é cancelado (D12) |

- Mínimo de cotações para escolher: **1**. Carga refrigerada ou perigosa pode ter uma transportadora só.
- Enquanto está em `SEM_COTACAO`, a solicitação continua recebendo cotações. Se uma transportadora voltar e cotar, o fluxo segue normalmente.
- Os dois prazos correm no relógio do módulo (D18) e são configuráveis, para teste e apresentação.

### D5. Quem escolhe o frete

**Decisão:** o comprador. Ele vê a comparação e escolhe qualquer cotação dentro do prazo de decisão (12 h), ou clica em **"automático"**. A regra do kit (menor preço, desempate pelo menor prazo, depois pela maior pontualidade e por fim pelo `transportadoraId`) continua valendo em dois casos: no botão "automático" e quando o prazo vence.

O `frete_selecionado` informa o critério: `ESCOLHA_COMPRADOR` ou `AUTOMATICO_MENOR_PRECO`.

**Depende de:** aval do professor (P2), porque o guia chama a regra do menor preço de "inegociável". O argumento é que a regra não foi abandonada, virou o comportamento padrão. Também é preciso avisar os grupos de Testes e de Infraestrutura.

### D6. O que é a comparação

**Decisão:** as duas partes.

- **Cotações de um pedido lado a lado:** preço, preço por t·km, prazo, data prevista, validade, origem da cotação e pontualidade da transportadora, com os selos "mais barata", "mais rápida", "mais pontual" e "recomendada pela regra", e um gráfico preço × prazo.
- **Ranking geral:** entregas feitas, % no prazo, atraso médio e preço médio por t·km, por transportadora e tipo de carga.

### D7. Transportadoras reais ou simuladas

**Decisão:** simuladas, com perfis diferentes (cara e rápida, barata e lenta, graneleira regional, refrigerada, perigosos). O motor de cotação fica atrás de uma interface, para uma API real poder entrar depois como extra.

### D8. De onde vem a posição do caminhão

**Decisão:** do simulador de viagem no `transportadoras-service`. A transportadora também pode informar eventos à mão (extra).

### D9. Rota no mapa

**Decisão:** linha interpolada entre origem e destino. Rota por estrada (OSRM) fica como extra.

### D10. Atualização da tela

**Decisão:** o caminhão muda de posição a cada **30 s reais**. A tela consulta a API a cada 5 s, então mostra a nova posição em até 5 s. SSE fica como extra.

Consequência para a apresentação: com o relógio acelerado (D18) para que os 3 dias de viagem durem cerca de 12 minutos, o caminhão anda 24 vezes. Acelerar mais reduz o número de movimentos.

### D11. Quem faz as telas

**Decisão:** nós, seguindo o mockup do UX sem simplificar. O grupo de UX já entregou o design; não há conflito. Telas:

- rastreamento da entrega (`portal_b2b_07_rastreamento.png`);
- solicitações de frete e envio de cotação (`portal_b2b_06_fretes.png`);
- comparação de cotações e escolha do frete;
- ranking de transportadoras;
- cadastro de motoristas e veículos (não existe no mockup; segue o mesmo estilo);
- relógio do módulo (só administrador).

### D12. Fim e falha da entrega

**Decisão:** três tópicos novos, a propor à Infraestrutura:

| Tópico | De | Para | Para quê |
|---|---|---|---|
| `rastreio_atualizado` | transportadoras | logística | Posição e eventos da viagem |
| `entrega_concluida` | logística | pedidos | Pedido vai a `ENTREGUE` |
| `frete_indisponivel` | logística | pedidos | Pedido sem frete possível deve ser cancelado |

A logística não cancela o pedido: ela **avisa** que não há frete, e quem cancela é o grupo de Pedidos. Payloads em [eventos](03-eventos-e-integracoes.md).

**Depende de:** aprovação da Infra (P3) e de o grupo de Pedidos consumir esses tópicos.

### D13. Banco e Kafka consistentes

**Decisão:** outbox transacional. O evento é gravado numa tabela na mesma transação da alteração e uma rotina publica no Kafka.

### D14. Tarefas com hora marcada em 2 cópias

**Decisão:** cada cópia roda as rotinas (prazos de cotação, passos da viagem, outbox) e pega o trabalho vencido com `SELECT ... FOR UPDATE SKIP LOCKED`. Se uma cópia cai, a outra continua.

### D15. Coordenadas

**Decisão:** tabela fixa com cerca de 30 cidades (polos do agro e portos). Base do IBGE se os outros grupos usarem cidades fora da lista.

### D16. Stack

**Decisão:** Python 3.12, FastAPI, `aiokafka`, `psycopg` 3 com `psycopg_pool` (pool de até 5 conexões), `pytest` com `httpx`; telas em HTML, JavaScript e Leaflet. O código é gerado por IA, com conhecimento do professor (P5).

**Mudança em relação ao kit (etapa 1):** o kit usa `psycopg2`, que é **síncrono**. Os serviços são assíncronos (FastAPI e `aiokafka` rodam num laço só), e cada consulta do `psycopg2` pararia o processo inteiro até o banco responder, inclusive o consumidor do Kafka. O `psycopg` 3 é a versão nova da mesma biblioteca e tem modo assíncrono. Não muda nada para os outros grupos.

O código compartilhado fica no pacote `comum/`, instalado nas imagens dos dois serviços, em vez da pasta `common/` do kit (que não entrava na imagem, K4).

### D17. Ordem e divisão

**Decisão sobre a ordem:** 5 etapas, descritas no [plano de trabalho](05-plano-de-trabalho.md). A prioridade é o fluxo do frete integrado; o rastreio visual vem em seguida. Nada foi cortado do escopo; se o tempo apertar, os itens do fim da etapa 4 são os que correm mais risco.

**Em aberto:** quem é responsável por cada etapa e quem procura o grupo de Pedidos. É a primeira tarefa da reunião.

### D18. Relógio do módulo

**Decisão:** os dois serviços usam um **relógio único do módulo**, não a hora do computador. Só o administrador pode acelerar. Acelerar vale para tudo que depende de tempo: viagem, previsão de chegada, atraso, ranking e os prazos de 12 h.

A diferença em relação aos outros grupos foi aceita: o relógio acelerado vale só para o módulo de logística, e isso é explicado na apresentação. O pedido no serviço de Pedidos registra a hora real.

Como funciona está na [arquitetura](02-arquitetura-proposta.md), seção 7.

### D19. Motoristas e veículos

**Decisão:**

- Cadastro de motoristas (nome, telefone, CNH) e veículos (placa, tipo, capacidade, tipos de carga) no `transportadoras-service`, com tela para a transportadora.
- O sistema **sorteia** o motorista e o veículo entre os que passam nos filtros: da transportadora vencedora, livres, com tipo de carga compatível e capacidade suficiente para o peso.
- Telefone e CNH são dados pessoais (LGPD): só aparecem para o comprador e o fornecedor daquela entrega, e a CNH aparece mascarada.

### D20. Transportadora sem motorista ou veículo

**Decisão:** duas proteções.

1. Uma transportadora só cota, simulada ou digitando, se tiver motorista e veículo livres e compatíveis naquele momento.
2. Se, mesmo assim, ninguém estiver livre quando o frete for escolhido (outra viagem ocupou o veículo entre a cotação e a escolha), a transportadora recusa a viagem. A logística passa para a próxima cotação pela regra do kit e avisa o comprador. Se não sobrar nenhuma cotação, o frete é dado como indisponível (D12).

### D21. Documentos da entrega

**Decisão:** CT-e, romaneio, nota fiscal e comprovante de coleta são **modelos demonstrativos** gerados pela logística com os dados reais da entrega, com a marca "documento demonstrativo, sem valor fiscal". Nota fiscal e CT-e reais são emitidos por fornecedor e transportadora junto à SEFAZ, o que está fora do escopo de qualquer grupo.

### D22. Avisos a comprador e fornecedor

**Decisão:** notificações dentro do portal, no sino que aparece no mockup. A logística guarda as notificações e as expõe pela API. E-mail e SMS ficam fora do escopo.

Quem recebe o quê está na [arquitetura](02-arquitetura-proposta.md), seção 8.

### D23. Contingência

**Decisão:** um script publica no Kafka um `pedido_criado` falso, no formato do contrato combinado com o grupo de Pedidos (D2), e um consumidor de teste faz o papel do grupo de Pedidos na outra ponta. Ele é usado nos testes durante todo o desenvolvimento e na apresentação, caso a integração com os outros grupos não esteja pronta.

Para o script não esconder uma divergência de contrato, ele valida o evento contra o mesmo JSON Schema que o serviço usa.

### D24. Repasse de conhecimento

**Decisão:** cada parte entregue vem com um arquivo em `docs/explicacoes/`: o que a parte faz, por que foi feita assim e as perguntas que o professor pode fazer, já com as respostas. Qualquer membro lê no seu tempo, e o apresentador estuda por eles.

**Risco aceito:** o apresentador é uma pessoa só e o estudo concentrado fica para o fim. Os arquivos de explicação reduzem, mas não eliminam, esse risco.

## 3. Perguntas para o professor

| ID | Pergunta | Afeta | Situação |
|---|---|---|---|
| P1 | O rastreio visual pode usar posição simulada? | D8 | Em aberto |
| P2 | Podemos deixar o comprador escolher o frete, mantendo a regra do menor preço como padrão automático? | D5 | Em aberto |
| P3 | Podemos propor tópicos novos ao kit? | D12, D18 | Em aberto |
| P4 | As telas de comparação e rastreio são nossas ou do UX? | D11 | Respondida pelo grupo: nossas, sobre o mockup do UX |
| P5 | Qual o prazo final e o que é entregue? Código gerado por IA é aceito? | D16, D17 | Parcial: até dezembro, data exata a confirmar; IA aceita |
