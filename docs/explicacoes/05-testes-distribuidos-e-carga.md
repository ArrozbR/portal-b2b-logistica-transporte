# 05. Testes distribuídos, teste de carga e relatório técnico

Etapa 5 do [plano](../05-plano-de-trabalho.md). Continua a [explicação 04](04-comparacao-cotacao-documentos.md). Até aqui, cada etapa era conferida com roteiros manuais no ambiente. Agora os cenários mais importantes viraram **testes automáticos** que qualquer pessoa do grupo roda com um comando, e o projeto ganhou o [relatório técnico](../07-relatorio-tecnico.md).

## 1. O que esta parte faz

| Entrega | O que é |
|---|---|
| **Testes de integração** (`testes_integracao/`) | 4 testes que rodam contra o ambiente no ar (Redpanda e PostgreSQL de verdade, duas cópias de cada serviço) e conferem o resultado no banco e nos tópicos |
| **Teste de carga** (`testes_carga/leitura.js`) | 200 usuários simultâneos lendo entregas, rastreio e comparação, para conferir o critério de desempenho do kit |
| **Relatório técnico** (`docs/07-relatorio-tecnico.md`) | Arquitetura, testes, resultados, limitações e as decisões em formato ADR |

A diferença para os testes unitários: o unitário testa uma regra isolada (por exemplo, "o menor preço vence"), sem banco nem Kafka. O de integração testa o sistema montado, com as mensagens passando de verdade pelo Kafka e as cópias disputando os mesmos dados.

## 2. Onde está cada coisa

| Arquivo | O que tem |
|---|---|
| `testes_integracao/apoio.py` | Funções de apoio: consultar o banco, publicar um pedido no Kafka, ler um tópico do começo ao fim, esperar uma condição, parar e subir contêineres, ler métricas |
| `testes_integracao/conftest.py` | Preparação: confere se o ambiente está no ar (senão, os testes são pulados), faz o login dos usuários de demonstração e controla o relógio |
| `testes_integracao/test_cenarios_distribuidos.py` | Os 3 cenários distribuídos do plano |
| `testes_integracao/test_fluxo_completo.py` | Do pedido à entrega, passando por todos os eventos |
| `testes_carga/leitura.js` | O cenário do k6 |
| `pytest.ini` | Acrescenta `testes_integracao` ao caminho do Python. O `pytest` sozinho continua rodando só os unitários |

## 3. As ideias principais

### 3.1 Conferir onde o resultado fica, não só na resposta

Uma API pode responder "200 OK" e mesmo assim o sistema ter feito a coisa duas vezes por trás. Por isso cada teste confere **três lugares**:

| Lugar | Exemplo de conferência |
|---|---|
| Banco | Quantas solicitações existem para o pedido; quantas linhas em `processed_events` |
| Outbox | Quantos eventos o serviço **decidiu** publicar |
| Tópico do Kafka | Quantos eventos **chegaram** de fato ao Redpanda |

Para ler o tópico, o teste cria um leitor sem grupo (não atrapalha os serviços), posiciona no começo de cada partição e lê até o fim, filtrando pela chave do pedido.

### 3.2 Cenário 1: mensagem duplicada

O teste publica **o mesmo** `pedido_criado` (mesmo `eventId`) 5 vezes, como aconteceria se o grupo de Pedidos reenviasse depois de uma falha de rede.

| Conferência | Esperado | Por quê |
|---|---|---|
| Mensagens no tópico | 5 | Prova que o Kafka realmente recebeu as repetições |
| Solicitações no banco | 1 | O efeito aconteceu uma vez só |
| `processed_events` com esse `eventId` | 1 | É o registro que barra as repetições |
| Métrica de duplicadas | +4 | As outras 4 foram reconhecidas e descartadas |
| `solicitacao_frete_criada` (outbox e tópico) | 1 | Não houve efeito em cascata repetido |
| Cotações | 3 | Uma por transportadora compatível, e não 15 |

### 3.3 Cenário 2: várias coisas ao mesmo tempo

No mesmo instante, o teste dispara:

- 6 escolhas de frete, alternando a cópia 1 e a cópia 2 e misturando "escolher esta cotação" com "automático";
- o relógio acelerado 100.000×, o que faz as 12 h de prazo vencerem em menos de 1 s, e aí a rotina de prazos **das duas cópias** também tenta escolher.

São até 8 atores tentando escolher o frete da mesma solicitação. O teste exige:

| Conferência | Esperado |
|---|---|
| Respostas | Só 200 ou 409; no máximo um 200 (pode ser zero, se a rotina de prazos ganhou) |
| `frete_selecionado` na outbox e no tópico | 1 |
| Entregas criadas | 1 |

Quem garante é a gravação condicional (`UPDATE ... WHERE status = 'COTADA'`): o banco só deixa uma gravação mudar a linha; as outras encontram a solicitação já escolhida e recebem 409.

### 3.4 Cenário 3: uma cópia caindo no meio da viagem

1. O teste cria um pedido, escolhe o frete e acelera o relógio até o caminhão sair (`EM_TRANSITO`).
2. Derruba a cópia 1 **dos dois serviços** (`docker compose stop logistica-1 transportadoras-1`).
3. Acelera o relógio pelo portal. O Nginx percebe que a cópia 1 caiu e manda para a 2.
4. Espera a entrega terminar só com as cópias 2. No fim, sobe as cópias 1 de novo (mesmo se o teste falhar).

| Conferência | Esperado | O que prova |
|---|---|---|
| Entrega | `ENTREGUE` | A cópia 2 assumiu as rotinas e as partições do Kafka |
| Sequências no banco da logística | 1, 2, 3, ..., N, sem buraco nem repetição | Nenhum evento se perdeu nem foi aplicado duas vezes |
| Sequência da viagem nas transportadoras | N | O que a transportadora publicou é exatamente o que a logística aplicou |
| Sequências no tópico | Todas de 1 a N | Tudo chegou ao Kafka |
| Primeiro e último evento | Viagem alocada, coleta, ..., entrega realizada | A ordem foi mantida |
| `entrega_concluida` na outbox | 1 | A conclusão não foi duplicada |

No tópico, uma repetição seria aceita: o Kafka entrega "pelo menos uma vez", e a proteção contra repetição está no consumidor. Por isso o teste exige "sem repetição" no **banco**, e no tópico só "nenhuma falta".

### 3.5 O fluxo completo

Um quarto teste percorre o caminho inteiro: pedido → solicitação → 3 cotações → comparação (com os selos certos) → escolha da Expressa pelo comprador (não a mais barata) → viagem → `entrega_concluida`. Confere também que o **mesmo `correlationId`** do pedido aparece em todos os eventos, as notificações do fornecedor, a pontualidade contabilizada e os 4 PDFs.

### 3.6 Teste de carga

O kit pede (guia, seção 10.2): **p95 de leitura até 500 ms com 200 requisições simultâneas** e menos de 1% de erros. "p95 de 474 ms" quer dizer que 95% das requisições responderam em até 474 ms.

O k6 roda dentro de um contêiner, na mesma rede do ambiente, então ninguém precisa instalar nada. São 200 usuários virtuais, sem pausa, por 30 s, chamando pelo portal a lista de entregas, o rastreio e a comparação.

| Métrica | Resultado |
|---|---|
| Requisições | 26.433 (866 por segundo) |
| Erros | 0% |
| p95 entregas / rastreio / comparação | 477 / 474 / 470 ms |

Passou, mas **com pouca folga**. O motivo é o limite do kit de 5 conexões com o banco por cópia: com 200 usuários, as requisições fazem fila esperando uma conexão livre. Na prática a carga é bem menor: 200 telas de rastreio abertas, consultando a cada 5 s, dão 40 requisições por segundo, 20 vezes menos que o teste.

## 4. Como rodar

```bash
docker compose up -d --build                         # ambiente no ar
.venv/Scripts/python -m pytest                       # unitários (78, segundos)
.venv/Scripts/python -m pytest testes_integracao -v  # integração (4, cerca de 2 min 40 s)
docker run --rm -i --network logistica-grupo5_default grafana/k6:0.54.0 run - < testes_carga/leitura.js
```

Cuidados:

- Os testes de integração **mexem no ambiente**: aceleram o relógio e derrubam contêineres. Não rode durante uma demonstração. No fim, o relógio volta para 1× e as cópias sobem de novo.
- Se o ambiente não estiver no ar, os testes são **pulados**, não falham.
- O teste de carga precisa de pelo menos uma entrega no banco (rode os de integração antes, ou crie uma pela tela).
- A senha do banco vem do `.env`, o mesmo que o `docker compose` usa.

## 5. O que foi testado

| Rodada | Resultado |
|---|---|
| Testes de integração, 1ª vez | 4 passaram em 161 s |
| Testes de integração, 2ª vez (para ver se é estável) | 4 passaram em 162 s |
| Teste de carga | Passou nos 4 limites (3 de tempo, 1 de erros) |
| Unitários | 78 passaram |

**Problemas encontrados e corrigidos ao escrever os testes** (eram problemas do teste, não do serviço):

| Problema | Correção |
|---|---|
| O leitor do tópico não achava as partições quando ainda não tinha pedido metadados ao cluster | Pede os metadados de todos os tópicos antes |
| "Voltar para o começo do tópico" não reposicionava o leitor de fato | Busca o primeiro offset de cada partição e posiciona nele |

## 6. O relatório técnico

O [relatório](../07-relatorio-tecnico.md) segue o modelo do grupo de Fornecimento e Produtos. Ele não repete os documentos de referência: resume e aponta para eles. As partes que mais interessam na apresentação:

| Seção | Conteúdo |
|---|---|
| 8 e 9 | Os problemas de sistemas distribuídos e como cada um foi resolvido, com o que foi testado |
| 11 | Testes e resultados (os números desta explicação) |
| 12 | As 25 decisões em formato ADR: contexto, decisão, alternativas e consequências |
| 13 e 14 | Limitações conhecidas e o que mudou em relação ao kit e ao plano |

Cada falha listada na seção 9 diz **como foi verificada**: por teste automático, por roteiro no ambiente ou "só no código". Algumas (3 tentativas antes da DLT, Redpanda fora na subida, supervisor das rotinas) estão só no código, sem teste. O grupo deve saber disso se o professor perguntar.

## 7. Perguntas que o professor pode fazer

**Como vocês provam que uma mensagem repetida não tem efeito duplicado?**
Publicando a mesma mensagem 5 vezes e contando: 5 no tópico, 1 solicitação no banco, 1 registro em `processed_events`, 4 contadas como duplicadas. O registro do evento processado é gravado na mesma transação da solicitação, então ou os dois existem ou nenhum.

**E se as duas cópias tentarem escolher o frete ao mesmo tempo?**
Testamos com 6 escolhas simultâneas nas duas cópias e o prazo vencendo no mesmo instante. Só uma gravação consegue mudar a solicitação de `COTADA` para `SELECIONADA`; as outras recebem 409. Sai um único `frete_selecionado`.

**O que acontece se um servidor cair no meio da entrega?**
O Kafka passa as partições da cópia que caiu para a outra, o Nginx manda as chamadas para a outra, e as rotinas de viagem continuam nela, porque o estado está no banco, não na memória. O teste derruba as duas cópias 1 no meio da viagem e confere que a entrega termina e que a sequência de rastreio vai de 1 a N sem buraco nem repetição.

**Por que não testar com mocks, que é mais rápido?**
Porque o que queremos provar é justamente o comportamento do Kafka e do banco com várias cópias: repetição de mensagem, troca de partição, duas gravações ao mesmo tempo. Um mock não reproduz isso. As regras puras (preço, selos, simulação) têm teste unitário com execução em segundos.

**O teste depende de sorte? A ordem das requisições muda a cada vez.**
O teste não exige uma ordem: aceita qualquer vencedora (inclusive a rotina de prazos), mas exige que haja **uma só**. Rodamos duas vezes seguidas, e passou nas duas.

**Por que o p95 ficou tão perto do limite?**
Por causa do limite de 5 conexões com o banco por cópia, que é regra do kit. Com 200 usuários sem pausa, as requisições esperam conexão. Mesmo assim, passou, e a carga real é 20 vezes menor. Para ter mais folga daria para pôr mais cópias, criar índices específicos ou um cache curto de leitura.

**O que não foi testado?**
A carga de escrita (o kit pede p95 até 1000 ms), as 3 tentativas antes da DLT e o Redpanda fora do ar na subida. Estão no código e listados no relatório como limitação.

**Os testes passam no computador de qualquer pessoa do grupo?**
Sim, se o ambiente estiver no ar com `docker compose up -d --build`. Os testes usam as mesmas portas e o mesmo `.env` do `docker-compose.yml`. Se o ambiente não estiver no ar, eles são pulados com uma mensagem dizendo como subir.
