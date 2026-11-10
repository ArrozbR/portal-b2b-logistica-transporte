# 02. Escolha pelo comprador, relógio do módulo, notificações e cancelamento

Etapa 2 do [plano](../05-plano-de-trabalho.md). Continua a [explicação 01](01-base-e-fluxo-automatico.md).

## 1. O que esta parte faz

| Antes (etapa 1) | Agora (etapa 2) |
|---|---|
| O frete era sempre escolhido pela regra do menor preço quando o prazo vencia | O **comprador escolhe** qualquer cotação em até 12 h, ou clica em **"automático"**. Se não fizer nada, vale a regra do menor preço |
| O relógio era sempre a hora real | O **administrador acelera o relógio do módulo** (ex.: 3600 vezes) para a apresentação |
| Ninguém era avisado de nada | **Notificações** para comprador e fornecedor, com contador de não lidas |
| Um pedido cancelado continuava no fluxo | **Cancelamento**: o pedido cancelado encerra a solicitação ou a entrega |
| Ninguém fazia o papel do grupo de Pedidos | O **"Pedidos falso"** consome os nossos eventos e reage como o grupo de Pedidos deveria |

## 2. Onde está cada coisa

| Arquivo | O que tem |
|---|---|
| `services/logistica-service/logistica/servico.py` | `escolher`, `cancelar_pedido`, `ajustar_relogio` e a rotina de prazos |
| `services/logistica-service/logistica/api.py` | Rotas novas: `selecionar-frete`, `notificacoes`, `relogio`, `admin/relogio` |
| `services/logistica-service/logistica/notificacoes.py` | Textos das notificações e a gravação delas |
| `services/logistica-service/migracoes/002_*.sql` | Tabelas `notificacao` e `pedido_cancelado`; quem escolheu o frete |
| `services/transportadoras-service/transportadoras/servico.py` | `sincronizar_relogio`: recebe o `relogio_ajustado` |
| `comum/comum/relogio.py` | Cálculo do relógio, gravação com versão |
| `comum/comum/ferramentas/pedidos_falso.py` | O "Pedidos falso" |
| `comum/comum/ferramentas/cancelar_pedido_falso.py` | Publica um cancelamento de teste |

## 3. As ideias principais

### 3.1 Escolha do frete pelo comprador

```
POST /api/v1/logistica/solicitacoes/{id}/selecionar-frete
Idempotency-Key: 6f1c...            ← obrigatório
{"cotacaoId": "..."}                 ← o comprador escolhe
{"modo": "AUTOMATICO"}               ← botão "automático": menor preço agora
```

Regras:

- Só o comprador dono do pedido (ou um administrador) escolhe. Outra empresa recebe 404; um fornecedor recebe 403.
- Só dá para escolher com a solicitação `COTADA`, ou seja, com pelo menos uma cotação. Depois de escolhido, qualquer nova tentativa recebe 409.
- O comprador tem até o fim do prazo de 12 h. Depois disso, o sistema escolhe sozinho pela regra do menor preço.
- Fica gravado **quem** escolheu (`escolhida_por`) e o critério (`ESCOLHA_COMPRADOR` ou `AUTOMATICO_MENOR_PRECO`), que vai também no `frete_selecionado`.

### 3.2 Idempotency-Key: clicar duas vezes não escolhe duas vezes

A internet falha. O comprador clica em "Escolher", a resposta demora, ele clica de novo; ou a tela tenta outra vez sozinha. Sem cuidado, a segunda tentativa receberia um erro "frete já escolhido", mesmo a primeira tendo dado certo.

A tela gera um código único (`Idempotency-Key`) para cada **intenção** de escolher e manda junto. O serviço guarda a resposta associada ao código, na tabela `idempotency_keys`, **na mesma transação** da escolha. Se o mesmo código chegar de novo, mesmo na **outra cópia** do serviço, ele devolve a mesma resposta, com o cabeçalho `X-Idempotent-Replay: true`, sem escolher de novo.

### 3.3 Cinco cliques ao mesmo tempo

Teste feito: 5 pedidos de escolha **no mesmo instante**, divididos entre as duas cópias do serviço, cada um com uma chave diferente (uns escolhendo a Expressa, outros no "automático"). Resultado: **1 deu certo e 4 receberam 409**, e saiu **um único** `frete_selecionado`.

Por quê: a escolha trava a linha da solicitação (`SELECT ... FOR UPDATE`) e grava com a condição `status = 'COTADA'` ([explicação 01](01-base-e-fluxo-automatico.md), seção 3.6). O banco executa um de cada vez. O primeiro muda o status; os outros encontram `SELECIONADA` e desistem.

### 3.4 Relógio do módulo

```
hora do módulo = hora em que o fator mudou + (tempo real passado desde então) × fator
```

- `POST /api/v1/logistica/admin/relogio` com `{"fator": 3600}`: só administrador. Com 3600, as 12 h de prazo passam em 12 segundos.
- A mudança é **sem salto**: a hora do módulo continua de onde estava, só muda a velocidade. Também dá para adiantar (`avancarHoras`), nunca voltar.
- A logística grava na tabela dela e publica `relogio_ajustado`; o serviço de transportadoras grava na tabela dele. Cada ajuste tem um número de **versão**, e um ajuste mais antigo que o gravado é ignorado. Isso protege contra mensagens repetidas ou fora de ordem.

**Problema encontrado e corrigido:** na primeira versão, cada cópia guardava o relógio em memória por 2 segundos. Com o relógio 3600 vezes mais rápido, 2 segundos viram **2 horas**: uma cópia poderia achar que o prazo do comprador já tinha acabado enquanto a outra ainda aceitava a escolha. Agora cada cópia lê o relógio do banco a cada uso, e as duas sempre veem a mesma hora.

**Exceção:** a rodada automática de 10 s conta na **hora real**. Ela existe para esperar as respostas automáticas das transportadoras, que levam ~150 ms de verdade. Se usasse o relógio acelerado, a rodada acabaria antes de qualquer cotação chegar.

### 3.5 Notificações

Gravadas **na mesma transação** da mudança que as gera: se a mudança for desfeita, a notificação também é.

| Quando | Comprador | Fornecedor |
|---|:---:|:---:|
| Chega a primeira cotação | ✔ | |
| A rodada de 10 s acaba sem cotação | ✔ | ✔ |
| O frete é escolhido pelo comprador | | ✔ |
| O frete é escolhido pela regra automática (prazo venceu) | ✔ | ✔ |
| O prazo vence sem nenhuma cotação (frete indisponível) | ✔ | ✔ |

`GET /api/v1/logistica/notificacoes` devolve a lista e o campo `naoLidas`, para o número no sino. `PATCH /api/v1/logistica/notificacoes/{id}` com `{"lida": true}` marca como lida. Cada empresa só vê e só mexe nas suas.

### 3.6 Cancelamento e mensagens fora de ordem

O grupo de Pedidos avisa o cancelamento com `pedido_atualizado` e `novoStatus: CANCELADO`:

| Situação do frete | O que acontece |
|---|---|
| Ainda sem escolha | A solicitação vira `CANCELADA` e não aceita mais escolha |
| Já escolhido | A entrega vira `CANCELADA` (na etapa 3, a transportadora libera o caminhão) |
| A logística ainda não conhece o pedido | O cancelamento é **guardado**; quando o `pedido_criado` chegar, a solicitação não é aberta |

O último caso existe porque `pedido_criado` e `pedido_atualizado` são **tópicos diferentes**. O Kafka só garante a ordem dentro de uma mesma partição de um mesmo tópico; entre tópicos diferentes, o cancelamento pode chegar antes da criação.

### 3.7 O "Pedidos falso"

Um contêiner (`pedidos-falso`) que faz o que o grupo de Pedidos deveria fazer ao receber os nossos eventos:

| Evento | Pedido vai para |
|---|---|
| `solicitacao_frete_criada` | `AGUARDANDO_FRETE` |
| `frete_selecionado` | `FRETE_SELECIONADO` |
| `entrega_concluida` | `ENTREGUE` |
| `frete_indisponivel` | `CANCELADO`, e publica `pedido_atualizado` com `CANCELADO` |

Ele só registra no log; não tem banco. Serve para os testes e, se preciso, para a apresentação. Quando o grupo de Pedidos real estiver integrado, ele é desligado.

## 4. Como ver funcionando

```bash
docker compose up -d --build
docker compose logs -f pedidos-falso        # o "grupo de Pedidos" reagindo

# um pedido
docker compose exec logistica-1 python -m comum.ferramentas.publicar_pedido_falso --pedido-id ped-demo

# tokens
docker compose exec logistica-1 python -m comum.ferramentas.gerar_token --perfil comprador --empresa emp-comprador-1
docker compose exec logistica-1 python -m comum.ferramentas.gerar_token --perfil admin
```

Em <http://localhost:8108/docs>, clique em **Authorize**, cole o token e use as rotas:

1. `GET /solicitacoes`: pegue o `id` da solicitação e veja as cotações em `GET /solicitacoes/{id}`.
2. `POST /solicitacoes/{id}/selecionar-frete` com um `Idempotency-Key` qualquer e `{"cotacaoId": "..."}`.
3. `GET /notificacoes` com o token do comprador ou do fornecedor (`--perfil fornecedor --empresa emp-fornecedor-1`).
4. Com o token de admin, `POST /admin/relogio` com `{"fator": 3600}`; publique outro pedido e veja a escolha automática acontecer em ~12 s. Volte com `{"fator": 1}`.
5. Cancelamento: `docker compose exec logistica-1 python -m comum.ferramentas.cancelar_pedido_falso --pedido-id ped-demo`.

## 5. O que foi testado no ambiente rodando

31 verificações, todas passando:

| Grupo | Verificações |
|---|---|
| Escolha pelo comprador | Notificação de cotações; sem `Idempotency-Key` → 400; corpo com as duas opções → 422; outra empresa → 404; fornecedor → 403; escolha da Expressa (não a mais barata) → 200; mesma chave na outra cópia → mesma resposta; outra chave → 409; fornecedor notificado; quem escolheu ficou gravado |
| Concorrência | 5 escolhas simultâneas nas duas cópias → 1 sucesso, 4 conflitos, 1 `frete_selecionado` |
| Cancelamento | Antes da escolha → `CANCELADA`; depois → entrega `CANCELADA`; antes do pedido chegar → solicitação não é aberta |
| Relógio | Comprador → 403; admin acelera; transportadoras sincroniza; 3 s reais = 3 h no módulo, vistos pela outra cópia |
| Prazos acelerados | Escolha automática em ~12 s, notificando o comprador; carga refrigerada sem transportadora → `INDISPONIVEL`, notificando os dois |
| Pedidos falso | Viu `AGUARDANDO_FRETE` → `FRETE_SELECIONADO`; ao receber `frete_indisponivel`, cancelou e publicou `pedido_atualizado` |
| Notificações | Marcar como lida; contador diminui; outra empresa → 404 |

## 6. Perguntas que o professor pode fazer

**O kit diz que a regra do menor preço é inegociável. Por que o comprador escolhe?**
A regra continua valendo: é o que acontece no botão "automático" e quando o comprador não decide em 12 h. A escolha manual é uma extensão. Isso ainda depende do aval do professor (pergunta P2 da pauta).

**O que é a Idempotency-Key e por que ela é obrigatória?**
É um código único que a tela gera para cada intenção de escolher. Se a mesma requisição chegar duas vezes (clique duplo, nova tentativa por falha de rede), o serviço devolve a mesma resposta em vez de tentar escolher de novo. Funciona nas duas cópias porque a resposta fica no banco, não na memória.

**E se dois compradores, ou o comprador e a rotina de prazos, escolherem ao mesmo tempo?**
Só um consegue. A escolha trava a linha da solicitação e só grava se o status ainda for `COTADA`. Testamos com 5 escolhas simultâneas nas duas cópias: 1 sucesso e 4 recusas.

**Como as duas cópias e os dois serviços concordam sobre que horas são, se o relógio pode ser acelerado?**
A logística é a dona do relógio. Ela grava o estado no banco (as duas cópias leem a mesma linha, sem cache) e publica `relogio_ajustado`, que as transportadoras gravam no banco delas. Cada ajuste tem versão, então um ajuste velho ou repetido não desfaz um novo.

**Por que a rodada de 10 s não acelera junto?**
Porque ela mede o tempo que as respostas automáticas levam para chegar pela rede, que é tempo real. Acelerada, ela acabaria antes das respostas.

**O que acontece se o cancelamento chegar antes do pedido?**
Pode acontecer, porque são tópicos diferentes, e o Kafka não garante ordem entre tópicos. A logística guarda o cancelamento numa tabela e, quando o pedido chegar, não abre a solicitação.

**Por que as notificações são gravadas na mesma transação?**
Para nunca avisar algo que não aconteceu. Se a escolha falhar e for desfeita, a notificação dela também é desfeita.
