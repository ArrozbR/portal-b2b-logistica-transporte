# 06. Pauta de decisões

Registro das decisões do grupo. A primeira versão desta pauta trazia só opções e recomendações; as decisões abaixo foram tomadas numa sessão de perguntas e respostas (o "grill") e, onde o grupo não tinha como decidir, pela melhor recomendação técnica, aceita pelo grupo. Quando uma decisão for confirmada com o professor ou com outro grupo, a situação muda para **Aceita** e o ADR correspondente no [relatório técnico](07-relatorio-tecnico.md) (seção 12) é atualizado.

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
| D9 | Rota no mapa | Pelas estradas: trechos do OSRM entre cidades vizinhas, gravados no repositório; linha reta só sem caminho | Mudou em 23/11/2026, a pedido do professor (antes: linha reta) |
| D10 | Atualização da tela | Posição muda a cada 30 min do módulo (entre 2 s e 30 s reais); a tela consulta a cada 5 s, ou 2 s acelerado | Ajustada em 23/11/2026 (antes: 30 s reais fixos) |
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
| D25 | Token do grupo de Autenticação | Token RS256 da Autenticação (JWKS, `tenant_id`, `active_scope`); o formato do kit (HS256) continua por configuração | Aceita; admin pelo `platform_role` `PLATFORM_ADMIN` do Identity-Service. Depende da Infra (kit) |
| D26 | Pedido que nasce sem comprador (leilão) | O frete só abre quando o pedido tem comprador e destino; no leilão, isso chega no fechamento (`pedido_atualizado`) | Aceita; confirmada pelo grupo de Pedidos (`VENDA_CONCLUIDA` e `AGUARDANDO_FRETE`, 19/11/2026) |
| D27 | Frete indisponível depois da venda | Não cancela o pedido: abre uma nova rodada de cotação para o mesmo pedido | Aceita (pedido do grupo de Pedidos, issue #1, 23/11/2026) |
| D28 | Funcionar sem os falsos | Login real nas telas (formato do Identity-Service), transportadora real criada pelo `empresa_cadastrada` e falsos opcionais | Aceita; o ambiente da turma depende da Infraestrutura |

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

Implementado na etapa 4: a transportadora de demonstração **Rodovia Sul** é real (não simulada) e só cota digitando, pela tela "Solicitações de frete" do mockup. As regras de validação estão na [arquitetura](02-arquitetura-proposta.md), seção 5.5.

### D4. Prazos da cotação

**Decisão:**

| Prazo | Valor | O que acontece quando vence |
|---|---|---|
| Rodada automática | 10 s (o tempo do kit), em hora real (D18) | Se nenhuma cotação chegou, a solicitação vai para `SEM_COTACAO` e comprador e fornecedor são avisados |
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

Implementado na etapa 4: tela de comparação (cartões, selos, pontualidade, gráfico preço × prazo e escolha) e tela de ranking, com filtro por tipo de carga.

### D7. Transportadoras reais ou simuladas

**Decisão:** simuladas, com perfis diferentes (cara e rápida, barata e lenta, graneleira regional, refrigerada, perigosos). O motor de cotação fica atrás de uma interface, para uma API real poder entrar depois como extra.

### D8. De onde vem a posição do caminhão

**Decisão:** do simulador de viagem no `transportadoras-service`. A transportadora também pode informar eventos à mão (extra).

### D9. Rota no mapa

**Decisão (23/11/2026):** a rota segue as estradas. A ferramenta `comum/ferramentas/gerar_estradas.py` pediu ao OSRM (motor de rotas sobre o OpenStreetMap), uma vez só, o traçado entre cada cidade da tabela e as suas 5 vizinhas mais próximas, e gravou o resultado em `comum/comum/dados/estradas.json`. A rota de uma viagem é o caminho mais curto, em km de estrada, por esses trechos. Sem caminho (cidade isolada), volta a ser a linha reta.

**Por que mudou:** o professor achou a linha reta pouco real.

**Por que não chamar o OSRM a cada viagem:** a demonstração ficaria dependendo de internet e de um servidor público com limite de uso. Com o arquivo no repositório, a rota é a mesma sempre e não sai nada da rede da turma.

**O que não mudou:** o preço e o prazo continuam usando a distância estimada (linha reta × 1,3, D15), para não mudar os valores das especificações. Na rota do cenário, Sorriso a Santos, a estrada tem 2.115 km, e a estimativa, 2.091 km (1% de diferença); em outras rotas, a diferença passa de 20% (Rio Verde a Paranaguá: 1.466 km de estrada, 1.163 km estimados).

**Travessias de balsa:** quando o caminho pelas estradas é mais que o dobro da distância estimada (Belém a Macapá, por exemplo, que na vida real atravessa de balsa), a rota volta a ser a linha reta.

**Antes:** linha interpolada entre origem e destino, com a estrada como extra.

### D10. Atualização da tela

**Decisão (ajustada em 23/11/2026):** o caminhão muda de posição a cada **30 minutos da hora do módulo**, com no mínimo 2 s e no máximo 30 s reais entre um passo e outro. A tela consulta a API a cada 5 s, ou a cada 2 s com o relógio acelerado, e atualiza na hora quando o administrador muda a velocidade. SSE fica como extra.

**Por que mudou:** antes, o passo era de 30 s reais fixos. Com o relógio em 3600×, cada passo equivalia a 30 h de estrada: o caminhão saltava pelo mapa e, por até 30 s, nem o botão "Atualizar localização" tinha posição nova para mostrar.

| Relógio | Passo real | Estrada por passo |
|---|---|---|
| 1× | 30 s | 30 s |
| 360× | 5 s | 30 min |
| 3600× | 2 s | 2 h |

### D11. Quem faz as telas

**Decisão:** nós, seguindo o mockup do UX sem simplificar. O grupo de UX já entregou o design; não há conflito. Telas:

- rastreamento da entrega (`portal_b2b_07_rastreamento.png`);
- solicitações de frete e envio de cotação (`portal_b2b_06_fretes.png`);
- comparação de cotações e escolha do frete;
- ranking de transportadoras;
- cadastro de motoristas e veículos (não existe no mockup; segue o mesmo estilo);
- relógio do módulo (só administrador).

Implementado na etapa 3: lista de entregas, rastreamento com mapa e relógio do módulo, servidos pelo contêiner `portal` (http://localhost:8088). Na etapa 4: solicitações e comparação (comprador), solicitações de frete e minha frota (transportadora), ranking, documentos e ocorrências. O menu muda conforme o perfil. O login dessas telas, no ambiente de desenvolvimento, vem do contêiner `usuarios-falso` (D23), que faz o papel do `usuarios-service`.

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

**Exceção (etapa 2):** a rodada automática de 10 s (D4) corre na **hora real**. É um tempo técnico de espera das respostas automáticas; no relógio acelerado, acabaria antes de as cotações chegarem.

Como funciona está na [arquitetura](02-arquitetura-proposta.md), seção 7.

### D19. Motoristas e veículos

**Decisão:**

- Cadastro de motoristas (nome, telefone, CNH) e veículos (placa, tipo, capacidade, tipos de carga) no `transportadoras-service`, com tela para a transportadora.
- O sistema **sorteia** o motorista e o veículo entre os que passam nos filtros: da transportadora vencedora, livres, com tipo de carga compatível e capacidade suficiente para o peso.
- Telefone e CNH são dados pessoais (LGPD): só aparecem para o comprador e o fornecedor daquela entrega, e a CNH aparece mascarada.

Implementado na etapa 3: API de cadastro (a tela fica para a etapa 4); filtro também pela categoria da CNH (C para caminhão, E para carreta); sorteio reproduzível, com o id da entrega como semente; reserva por gravação condicional, para o mesmo caminhão nunca ficar em duas viagens. A CNH sai do `transportadoras-service` já mascarada (só os 4 últimos dígitos).

### D20. Transportadora sem motorista ou veículo

**Decisão:** duas proteções.

1. Uma transportadora só cota, simulada ou digitando, se tiver motorista e veículo livres e compatíveis naquele momento.
2. Se, mesmo assim, ninguém estiver livre quando o frete for escolhido (outra viagem ocupou o veículo entre a cotação e a escolha), a transportadora recusa a viagem. A logística passa para a próxima cotação pela regra do kit e avisa o comprador. Se não sobrar nenhuma cotação, o frete é dado como indisponível (D12).

Testado na etapa 3: três compradores escolheram a mesma transportadora, que tinha dois caminhões, ao mesmo tempo. Dois ficaram com ela (caminhões e motoristas diferentes) e o terceiro passou automaticamente para a próxima cotação.

### D21. Documentos da entrega

**Decisão:** CT-e, romaneio, nota fiscal e comprovante de coleta são **modelos demonstrativos** gerados pela logística com os dados reais da entrega, com a marca "documento demonstrativo, sem valor fiscal". Nota fiscal e CT-e reais são emitidos por fornecedor e transportadora junto à SEFAZ, o que está fora do escopo de qualquer grupo.

Implementado na etapa 4: PDFs gerados na hora com a biblioteca `fpdf2` (nada é guardado), baixados pela tela de rastreamento. O comprovante de coleta só existe depois da coleta.

### D22. Avisos a comprador e fornecedor

**Decisão:** notificações dentro do portal, no sino que aparece no mockup. A logística guarda as notificações e as expõe pela API. E-mail e SMS ficam fora do escopo.

Quem recebe o quê está na [arquitetura](02-arquitetura-proposta.md), seção 8.

### D23. Contingência

**Decisão:** um script publica no Kafka um `pedido_criado` falso, no formato do contrato combinado com o grupo de Pedidos (D2), e um consumidor de teste faz o papel do grupo de Pedidos na outra ponta. Ele é usado nos testes durante todo o desenvolvimento e na apresentação, caso a integração com os outros grupos não esteja pronta.

Para o script não esconder uma divergência de contrato, ele valida o evento contra o mesmo JSON Schema que o serviço usa.

Implementado: `comum.ferramentas.publicar_pedido_falso` (etapa 1), `comum.ferramentas.cancelar_pedido_falso` e o contêiner `pedidos-falso` (etapa 2), que consome os nossos eventos, registra as mudanças de status do pedido e cancela o pedido ao receber `frete_indisponivel`. Na etapa 3, o contêiner `usuarios-falso` faz o papel do grupo de Autenticação no login das telas, só no ambiente de desenvolvimento. Depois, o `pedidos-falso` ganhou rotas só do admin para criar e cancelar pedidos de teste, usadas pelo botão "Novo pedido de teste" da tela de solicitações e pelo teste de carga de escrita ([explicação 09](explicacoes/09-pedido-de-teste-e-carga-de-escrita.md)).

### D24. Repasse de conhecimento

**Decisão:** cada parte entregue vem com um arquivo em `docs/explicacoes/`: o que a parte faz, por que foi feita assim e as perguntas que o professor pode fazer, já com as respostas. Qualquer membro lê no seu tempo, e o apresentador estuda por eles.

**Risco aceito:** o apresentador é uma pessoa só e o estudo concentrado fica para o fim. Os arquivos de explicação reduzem, mas não eliminam, esse risco.

### D25. Token do grupo de Autenticação

**Contexto:** o grupo de Autenticação definiu o token na issue #2 do repositório de Fornecimento e Produtos (09/11/2026): RS256, chaves públicas no `/.well-known/jwks.json` e claims `sub`, `tenant_id`, `group_id`, `active_scope` (`BUYER`, `SUPPLIER`, `CARRIER`, `TENANT_ADMIN`), `roles` e `permissions`. O kit ainda usa HS256 com `empresaId` e `perfil` (L16). O grupo de Produtos já mudou para RS256 e pediu à Infra que alinhe o kit.

**Decisão:** seguir o formato da Autenticação, que é o dono do login, como o grupo de Produtos fez.

1. O token é validado com RS256 e a chave pública do `kid`, buscada no JWKS (`AUTH_JWKS_URL`) e guardada por 1 hora. O algoritmo vem da configuração, nunca do token. Um `kid` novo (troca de chave) faz uma nova busca, no máximo a cada 5 s.
2. Tradução para os perfis do módulo: `BUYER` → comprador, `SUPPLIER` → fornecedor, `CARRIER` → transportadora; `tenant_id` é a empresa.
3. `TENANT_ADMIN` **não** vira o nosso `admin`: ele administra uma empresa, e o nosso admin vê as entregas de todas e mexe no relógio do módulo. O admin da plataforma é quem tem `platform_role` `PLATFORM_ADMIN` no token (o administrador global do Identity-Service, como o `platform-admin@agrobrasil.com.br` do seed deles), ou, como alternativa nossa, a permissão `logistica:admin`. `TENANT_ADMIN` sem isso recebe 403 com a orientação de trocar o contexto.
7. (10/11/2026, conforme o código do Identity-Service) O token traz `iss` `identity-service` e `aud` `b2b-platform`, conferidos (`JWT_ISSUER`, `JWT_AUDIENCE`). Token sem empresa ou sem escopo ativo (`view_mode` `NONE`, logo depois do login, ou `MACRO_GROUP`) recebe 403 `CONTEXTO_NAO_SELECIONADO`, não 401, para a tela pedir a troca de contexto em vez de deslogar.
4. A transportadora continua ligada à empresa pelo `empresa_id`, que passa a ser o `tenant_id` da empresa com escopo `CARRIER`.
5. `JWT_ALGORITHM=HS256` volta ao formato do kit (`empresaId`, `perfil`, `JWT_SECRET_KEY`), para rodar com o kit enquanto ele não for atualizado.
6. No desenvolvimento, o `usuarios-falso` emite tokens RS256 no formato da Autenticação e publica o próprio JWKS (também em `/.well-known/jwks.json` pelo portal).

Implementado: `comum/comum/auth.py`, `comum/comum/ferramentas/usuarios_falso.py` e `gerar_token.py`, com 16 testes em `comum/tests/test_auth.py`.

**Situação:** aceita. O administrador da plataforma está resolvido pelo `platform_role`. Falta a Infra atualizar o kit.

### D26. Pedido que nasce sem comprador (leilão)

**Contexto:** em 12/11/2026, o professor respondeu ao grupo de Fornecimento e Produtos (pelo Teams; registrado como F14 no documento de requisitos deles) que o pedido é criado na **abertura** do leilão ou da negociação, e não no fechamento. O leilão é o "portador do pedido": o comprador só é definido quando ele fecha, com o último lance válido, e a compra e venda acontece depois. O professor pediu à Infraestrutura que mude o kit, que hoje cria o pedido a partir de `negociacao_fechada`. Produtos passou a aceitar `compradorId` nulo no `pedido_criado` (contrato de eventos 1.3).

Para nós, isso quebrava o fluxo: o nosso contrato exigia `compradorId` e `destino`, então o pedido de leilão iria para a DLT. E não faz sentido cotar frete antes do fechamento: o destino é o local do comprador, o prazo de 12 h é para o comprador escolher, e o leilão pode nem fechar.

**Decisão:** a solicitação de frete só abre quando o pedido tem **comprador e destino**.

1. `pedido_criado` com comprador e destino (negociação direta, ou se Pedidos já mandar no fechamento): abre na hora, como antes.
2. `pedido_criado` sem comprador ou sem destino (leilão): o pedido fica guardado (`logistica.pedido_aguardando`), sem solicitação e sem aviso a ninguém.
3. `pedido_atualizado` que não seja `CANCELADO` e traga `compradorId` ou `destino` é tratado como o fechamento. Os campos dele (inclusive `valorTotal` e `pesoKg` do lance vencedor) vão por cima dos do pedido, e a solicitação abre com o `correlationId` do `pedido_criado`.
4. Os dois eventos vêm de tópicos diferentes e podem chegar em qualquer ordem: o fechamento que chega antes também é guardado.
5. Cancelamento antes do fechamento tira o pedido da espera, e um fechamento posterior é ignorado.

**Resposta do grupo de Pedidos** (ESP-PED-001 v2.1, D-03, e issue #1 deste repositório, 19 e 23/11/2026): o pedido nasce sem comprador e sem destino tanto no leilão quanto na negociação direta, só para reservar o estoque. O `pedido_atualizado` `VENDA_CONCLUIDA` traz o comprador (sem destino); depois, o comprador informa o destino, e o `pedido_atualizado` `AGUARDANDO_FRETE` traz a carga completa. Pela regra 3, os campos se juntam e a solicitação abre no `AGUARDANDO_FRETE`. Os exemplos deles passam nos nossos schemas. O `pedidos-falso` passou a publicar `AGUARDANDO_FRETE`.

Implementado: `services/logistica-service/logistica/pedidos.py` (regras puras), `servico.py` (`abrir_solicitacao`, `atualizar_pedido`), migração `005_pedido_aguardando.sql`, contratos `pedido_criado` e `pedido_atualizado`, opção "Pedido de leilão" no botão do admin, ESP-LOG-001 1.3 (RF-20) e [explicação 10](explicacoes/10-pedido-de-leilao.md).

**Situação:** aceita e confirmada pelo grupo de Pedidos.

### D27. Frete indisponível depois da venda

**Contexto:** o frete fica indisponível quando nenhuma transportadora cota no prazo de 12 h ou quando nenhuma das que cotaram tem frota livre. Até aqui, o grupo de Pedidos cancelava o pedido (o nosso `pedidos-falso` fazia isso). Na ESP-PED-001 v2.1 (RN-22 e D-05), eles decidiram não cancelar: a venda já foi concluída no fechamento e o estoque já teve baixa, e o estorno está fora da versão deles. Na issue #1 do nosso repositório (23/11/2026), pediram que a logística abra uma nova `solicitacao_frete_criada` para o mesmo pedido, com a `tentativa` recomeçando em 1.

**Decisão:** o frete indisponível abre uma nova rodada de cotação.

1. Na mesma transação do `frete_indisponivel`, a logística abre outra solicitação para o mesmo pedido, com `rodada` + 1 e a mesma carga. Prazos, coleta e rodada de 10 s recomeçam.
2. Cada solicitação é única por (pedido, rodada), e a `tentativa` da entrega é única por solicitação: recomeça em 1.
3. Não há limite de rodadas. Sem cotação, cada uma dura no mínimo 10 s reais e as 12 h do módulo, então não há laço rápido.
4. O cancelamento age sobre a rodada mais recente. As notificações dizem que uma nova cotação foi aberta.
5. O `pedidos-falso` não cancela mais o pedido ao receber `frete_indisponivel`.

**Alternativa rejeitada:** manter o cancelamento. O pedido ficaria parado do lado de Pedidos, que não cancela depois da venda.

Implementado: `servico.py` (`_reabrir`, `pedido_da_solicitacao`), migração `006_nova_rodada.sql`, campo `rodada` no `solicitacao_frete_criada`, tela de solicitações, `pedidos-falso`, teste de integração `test_frete_indisponivel.py`, ESP-LOG-001 1.4 (RF-21) e [explicação 11](explicacoes/11-nova-rodada-e-cidades.md).

**Situação:** aceita.

### D28. Funcionar sem os falsos

**Contexto:** até aqui, dois contêineres falsos faziam o papel de outros grupos: o `usuarios-falso` (Autenticação) e o `pedidos-falso` (Pedidos). O back-end já aceitava o token e os eventos reais, mas três coisas dependiam dos falsos: o login das telas, a existência das transportadoras (só dos seeds, ligadas a empresas inventadas) e o botão de pedido de teste.

**Decisão:**

1. **Login real nas telas.** O portal usa o fluxo do Identity-Service: `POST /api/v1/auth/login` (e-mail e senha), escolha da empresa e do perfil (`POST /api/v1/auth/switch-context`) e renovação automática do token, que vale 15 min (`POST /api/v1/auth/refresh`). O `usuarios-falso` passou a imitar essas rotas no mesmo formato, então as telas não sabem se falam com o falso ou com o real. O endereço é a variável `AUTH_URL` do portal.
2. **Transportadora real pelo `empresa_cadastrada`.** Empresa com escopo `CARRIER` no Identity-Service vira transportadora real (`simulada` false), com o `tenantId` como id. O usuário dela entra pelo login real e encontra a sua transportadora; ela cota digitando e cadastra a própria frota.
3. **Falsos opcionais.** O portal sobe sem eles; o botão "Novo pedido de teste" só aparece se o `pedidos-falso` responde.

**O que depende de outros grupos** (anotado nas issues do nosso repositório): a Infraestrutura criar os tópicos novos e as rotas no gateway (inclusive `/api/v1/auth/` para o Identity-Service), o grupo de Banco aplicar as nossas migrações, e a Autenticação dizer no `empresa_cadastrada` que cargas a transportadora leva (hoje ela começa com os 4 tipos).

Implementado: `frontend/assets/portal.js` (login), `comum/comum/ferramentas/usuarios_falso.py` (rotas `/api/v1/auth/*`), `services/transportadoras-service/transportadoras/empresas.py` e `registrar_empresa`, `infra/portal/nginx.conf` (modelo com `AUTH_URL`), ESP-TRP-001 1.2 (RF-14) e [explicação 12](explicacoes/12-sem-os-falsos.md).

**Situação:** aceita.

## 3. Perguntas para o professor

| ID | Pergunta | Afeta | Situação |
|---|---|---|---|
| P1 | O rastreio visual pode usar posição simulada? | D8 | Em aberto |
| P2 | Podemos deixar o comprador escolher o frete, mantendo a regra do menor preço como padrão automático? | D5 | Em aberto |
| P3 | Podemos propor tópicos novos ao kit? | D12, D18 | Em aberto |
| P4 | As telas de comparação e rastreio são nossas ou do UX? | D11 | Respondida pelo grupo: nossas, sobre o mockup do UX |
| P5 | Qual o prazo final e o que é entregue? Código gerado por IA é aceito? | D16, D17 | Parcial: até dezembro, data exata a confirmar; IA aceita |
