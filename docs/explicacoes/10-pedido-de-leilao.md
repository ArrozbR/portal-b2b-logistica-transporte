# 10. Pedido de leilão: o frete só começa no fechamento

## 1. O que mudou e por quê

Em 12/11/2026, o professor respondeu a dúvidas do grupo de Fornecimento e Produtos (pelo Teams; eles registraram no repositório deles). Uma das respostas mexe com a gente:

> o pedido é criado na **abertura** do leilão ou da negociação, não no fechamento. No leilão, o comprador só é definido quando ele fecha.

Até então, o nosso fluxo supunha que o `pedido_criado` já trazia o comprador e o destino. Com a resposta do professor, um pedido de leilão chega **sem comprador** e, como o destino é o local do comprador, **sem destino**. Havia dois problemas:

| Problema | Por quê |
|---|---|
| O evento seria recusado | O nosso contrato exigia `compradorId` e `destino`. O pedido iria direto para a fila de erros (DLT) |
| Não dá para cotar antes do fechamento | Sem destino, não há distância nem preço. O prazo de 12 h é para o comprador escolher, e ainda não há comprador. E o leilão pode nem fechar |

A solução (decisão D26): **a solicitação de frete só abre quando o pedido tem comprador e destino.**

## 2. Como funciona

```text
Negociação direta:   pedido_criado (com comprador e destino) ──► solicitação abre na hora (como antes)

Leilão:              pedido_criado (sem comprador e destino) ──► pedido fica guardado, esperando
                     ... o leilão acontece ...
                     pedido_atualizado (fechamento: comprador, destino, valor final) ──► solicitação abre
```

| Situação | O que a logística faz |
|---|---|
| `pedido_criado` com comprador e destino | Abre a solicitação na hora |
| `pedido_criado` sem comprador ou sem destino | Guarda o pedido na tabela `pedido_aguardando`. Ninguém recebe aviso |
| `pedido_atualizado` com `compradorId` ou `destino` (fechamento) | Junta com o pedido guardado e abre a solicitação. O valor e o peso do lance vencedor valem no lugar dos do pedido |
| Fechamento que chega **antes** do pedido | Guarda o fechamento; quando o pedido chega, abre |
| `pedido_atualizado` `CANCELADO` antes do fechamento | Tira o pedido da espera; um fechamento depois disso é ignorado |
| Fechamento de pedido que já tem solicitação | Ignorado |

O prazo de 12 h para o comprador escolher começa a contar quando a solicitação abre, ou seja, no fechamento.

### Por que o fechamento pode chegar antes do pedido

O `pedido_criado` e o `pedido_atualizado` são tópicos diferentes do Kafka. O Kafka só garante a ordem **dentro** de um tópico (na mesma partição). Entre tópicos, uma mensagem publicada depois pode ser lida antes. Por isso o pedido e o fechamento são guardados em colunas separadas (`pedido` e `fechamento`), e a solicitação só abre quando os dois estão lá. É o mesmo cuidado que já tínhamos com o cancelamento que chega antes do pedido.

### Por que travar a linha

As duas cópias do serviço consomem ao mesmo tempo. Uma pode estar lendo o `pedido_criado` enquanto a outra lê o fechamento do mesmo pedido. A linha da tabela é travada (`SELECT ... FOR UPDATE`) enquanto uma cópia trabalha nela, e a outra espera. Assim nenhuma das duas perde o que a outra gravou, e não abrem duas solicitações.

## 3. O que ainda não está definido

O grupo de Pedidos ainda não disse como o fechamento será avisado. Fizemos do jeito mais tolerante possível e deixamos as perguntas registradas:

| Dúvida | O que fizemos enquanto isso | Onde está registrada |
|---|---|---|
| Qual evento e qual status avisam o fechamento? | Aceitamos **qualquer** `pedido_atualizado` (menos `CANCELADO`) que traga `compradorId` ou `destino`. O `pedidos-falso` usa `LEILAO_FECHADO`, provisório | Proposta ao grupo de Pedidos (perguntas 5 a 9); pauta D26; ESP-LOG-001 Q-13 |
| O fechamento traz o destino? | Esperamos que sim. O destino nasce na demanda do comprador, e o `demanda_criada` do grupo de Compra e Demanda já tem `destino` `{cidade, uf}` | Proposta, pergunta 6 |
| O valor final vem no fechamento? | Se vier, usamos; se não, fica o do pedido | Proposta, pergunta 7 |
| Na negociação direta, o pedido já vem com comprador e destino? | Se vier, nada muda | Proposta, pergunta 8 |

Se o grupo de Pedidos escolher outro tópico para o fechamento, muda só o lugar de onde lemos os dados; a espera e a junção continuam iguais.

## 4. Como testar

Na tela **Solicitações de frete**, como Administrador, use **Novo pedido de teste** e marque **Pedido de leilão**. O `pedidos-falso` publica o pedido sem comprador nem destino e, 10 s depois, fecha o leilão com o comprador e o destino escolhidos no formulário. A solicitação aparece só depois do fechamento.

Testes automáticos:

| Teste | O que confere |
|---|---|
| `services/logistica-service/tests/test_pedidos.py` | Regras puras: o que falta para o frete, o fechamento por cima do pedido, nulo não apaga valor |
| `comum/tests/test_eventos.py` | O contrato aceita o pedido sem comprador e destino, e o fechamento com eles |
| `comum/tests/test_pedidos_falso.py` | O botão de leilão publica o pedido sem comprador e agenda o fechamento |
| `testes_integracao/test_pedido_de_leilao.py` | No ambiente real: só abre no fechamento; fechamento antes do pedido; leilão cancelado não abre frete; o `correlationId` continua o do pedido |

## 5. Onde está cada coisa

| Arquivo | O que tem |
|---|---|
| `services/logistica-service/logistica/pedidos.py` | Regras puras da junção |
| `services/logistica-service/logistica/servico.py` | `abrir_solicitacao` (pedido), `atualizar_pedido` (fechamento ou cancelamento), `_juntar` e `_abrir` |
| `services/logistica-service/migracoes/005_pedido_aguardando.sql` | A tabela da espera (precisa de `docker compose down -v`) |
| `comum/comum/contratos/pedido_criado.schema.json`, `pedido_atualizado.schema.json` | `compradorId` e `destino` opcionais no pedido; campos do fechamento no `pedido_atualizado` |
| `comum/comum/ferramentas/pedidos_falso.py`, `frontend/assets/solicitacoes.js` | Opção "Pedido de leilão" e rota de fechamento |
| ESP-LOG-001 1.3 | RF-20, RN-35, CA-83 a CA-86, Q-13 |

## 6. Perguntas que o professor pode fazer

**Por que não cotar o frete já na abertura do leilão?**
Porque sem comprador não há destino, e sem destino não há distância nem preço. Além disso, o leilão pode não fechar, e as transportadoras teriam cotado e reservado atenção para um frete que não existe.

**E se o fechamento nunca chegar?**
O pedido fica esperando, sem custo para ninguém: não há solicitação, não há prazo correndo, não há aviso. Se o leilão for cancelado, o `pedido_atualizado` `CANCELADO` tira o pedido da espera.

**Por que aceitar qualquer status no fechamento?**
Porque o grupo de Pedidos ainda não definiu o nome. O que importa para nós é o conteúdo: comprador e destino. Quando eles definirem, podemos restringir ao status combinado.

**Como vocês garantem que não abrem duas solicitações?**
De três formas: o `pedido_id` é único na tabela de solicitações; a linha da espera é travada enquanto uma cópia trabalha; e cada evento é processado uma vez só (`processed_events`).
