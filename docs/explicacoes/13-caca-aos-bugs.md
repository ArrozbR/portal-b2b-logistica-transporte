# 13. Caça aos bugs

Em 23/11/2026, fizemos uma procura de defeitos em todo o código, em três frentes:

1. **Análise estática** (ruff): erros de Python, variáveis não usadas, exceções mal tratadas. Não achou nada grave.
2. **Leitura do código de maior risco**: consumo de eventos, DLT, escolha do frete, cotação, frota, relógio, login e telas.
3. **Sondagens no ambiente real**: cada suspeita virou um teste contra o ambiente no ar, antes e depois da correção.

Foram 6 defeitos, todos corrigidos e cobertos por teste. Os dois primeiros eram os mais graves.

## 1. Os defeitos

| # | Onde | O que acontecia | Gravidade | Agora |
|---|---|---|---|---|
| 1 | Consumo de eventos | Um evento com `eventId` nulo, vazio ou com mais de 64 caracteres falhava ao gravar em `processed_events`. Ao mandar para a DLT, o consumidor tentava gravar o **mesmo** `eventId`, falhava de novo e repetia **para sempre**. O consumidor do serviço inteiro ficava parado. O mesmo acontecia com um `aggregateId` de mais de 100 caracteres, que não cabia na chave da DLT | **Alta**: uma mensagem ruim parava todo o consumo | O envelope é conferido na chegada: `eventId` de 1 a 64 caracteres e `correlationId` de até 128. Quem não passa vai direto para a DLT. A chave da DLT é cortada em 100 |
| 2 | Pedido do grupo de Pedidos | Eles aceitam `correlationId` de até 128 caracteres; as nossas colunas guardavam 64. Um pedido real com um identificador maior ia para a DLT, e o frete nunca abria | **Alta**: pedido real perdido | Colunas com 128 (migrações 007 da logística e 004 das transportadoras) |
| 3 | Cotação digitada | A rota aceitava qualquer valor maior que zero, como R$ 0,004. A transportadora recebia "cotação enviada" (201), mas a logística arredondava para R$ 0,00, o banco recusava (preço tem que ser maior que zero) e a cotação ia para a DLT. O comprador nunca a via | Média | Valor de R$ 0,01 a R$ 10 milhões, com no máximo 2 casas (422 fora disso). A tela também avisa |
| 4 | Escolha do frete | A chave de idempotência era só (usuário, `Idempotency-Key`). A mesma chave em **outra** solicitação devolvia a resposta da primeira, com 200, sem escolher nada | Média | A solicitação entra na chave |
| 5 | Escolha do frete | A chave era gravada como texto numa coluna de 128 caracteres. Com o id de usuário do Identity-Service (UUID, 36) e uma `Idempotency-Key` de 100, passava de 128, e a escolha respondia **500** | Média: só com o login real | A chave é um resumo SHA-256, sempre com 64 caracteres |
| 6 | Notificações | Quando o administrador escolhia o frete pelo comprador, o comprador não era avisado: o aviso só saía quando a escolha era da rotina de prazos | Baixa | O comprador é avisado sempre que não foi ele quem escolheu |

## 2. Como cada um foi confirmado

Nenhuma correção foi feita "no escuro". Cada defeito foi reproduzido no ambiente antes da correção e conferido de novo depois:

| # | Antes | Depois |
|---|---|---|
| 1 | O log mostrava "Não foi possível gravar na DLT, tentando de novo" a cada 2 s, sem parar | O evento vai para a DLT; um pedido publicado logo depois é consumido normalmente |
| 2 | Pedido com `correlationId` de 100 caracteres na DLT: "value too long for type character varying(64)" | O frete abre |
| 3 | R$ 0,004: 201 na transportadora; na logística, DLT com "violates check constraint cotacao_preco_check" | 422 |
| 4 | A segunda escolha devolveu a primeira solicitação; a segunda continuou `COTADA` | A segunda solicitação é escolhida; repetir a mesma requisição continua devolvendo a resposta guardada |
| 6 | Nenhuma notificação para o comprador | 1 notificação `FRETE_ESCOLHIDO` |

## 3. O que foi olhado e está certo

- Reserva de caminhão e motorista entre as duas cópias (gravação condicional): conferida no teste de carga, sem nenhum caminhão em duas viagens.
- Permissões da frota: uma transportadora não mexe na frota de outra (403).
- Telas: todo texto que vem do usuário (ocorrências, nomes, cidades) é escapado antes de ir para a página; os avisos usam `textContent`.
- Relógio do módulo, outbox, cancelamento de viagem, troca de transportadora e a nova rodada de cotação.

## 4. Pontos de atenção que ficaram como estão

| Ponto | Por que não mudamos |
|---|---|
| O rastreio não confere se o evento veio da mesma transportadora da entrega | Só os serviços do portal publicam no Kafka; um evento trocado seria um defeito de outro serviço, não uma entrada de usuário |
| A mesma CNH pode existir em duas transportadoras | A unicidade é por transportadora; um motorista que trabalha para duas empresas é um caso real |

## 5. Onde está cada coisa

| Arquivo | Correção |
|---|---|
| `comum/comum/eventos.py`, `comum/comum/consumidor.py` | 1 |
| `services/logistica-service/migracoes/007_correlacao_128.sql`, `services/transportadoras-service/migracoes/004_correlacao_128.sql` | 2 |
| `services/transportadoras-service/transportadoras/api.py`, `frontend/assets/fretes.js` | 3 |
| `services/logistica-service/logistica/api.py` (`chave_de_idempotencia`) | 4 e 5 |
| `services/logistica-service/logistica/servico.py` (`pelo_comprador`) | 6 |
| `comum/tests/test_consumidor.py`, `comum/tests/test_eventos.py`, `services/*/tests/` | Testes de cada correção |
| ESP-LOG-001 1.5, ESP-TRP-001 1.3 | RN-15, RN-30, RN-32 e o valor da cotação |

## 6. Perguntas que o professor pode fazer

**Por que uma mensagem ruim travava o serviço inteiro?**
O consumidor processa as mensagens em ordem e só passa para a próxima depois de terminar a atual, para não perder nada. A DLT existe justamente para tirar a mensagem ruim do caminho. Só que a gravação na DLT também falhava, porque usava o mesmo `eventId` grande demais, e ela tentava de novo para sempre. Agora o envelope é conferido antes, e uma mensagem com `eventId` inválido vai para a DLT sem esse `eventId`.

**Como vocês acharam esses defeitos, se os testes passavam?**
Comparando os limites de cada parte. O grupo de Pedidos aceita 128 caracteres no `correlationId`; nós guardávamos 64. A coluna da chave de idempotência tem 128; a chave montada podia passar disso. Os testes usavam valores "bonitos" (UUIDs curtos, preços redondos), que nunca chegavam ao limite.

**Por que guardar um resumo SHA-256 e não a chave inteira?**
Tem tamanho fixo (64 caracteres), qualquer que seja o tamanho do id do usuário e da chave. E não precisamos ler a chave de volta: só precisamos saber se a mesma requisição já foi feita.
