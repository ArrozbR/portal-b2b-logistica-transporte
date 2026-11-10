# 09. Pedido de teste pela tela, carga de escrita e especificação completa

Esta parte fecha três pendências do nosso lado:

1. **Botão "Novo pedido de teste"**: o administrador cria um pedido pela tela, sem terminal.
2. **Teste de carga de escrita**: 10 pedidos novos por segundo, do pedido à escolha do frete.
3. **ESP-LOG-001 versão 1.2**: a especificação agora cobre notificações, ocorrências e documentos em PDF.

No caminho, apareceram um defeito no código e um problema no ambiente de testes (seção 4).

## 1. O botão "Novo pedido de teste"

### O que faz

Na tela **Solicitações de frete**, o administrador vê o botão **+ Novo pedido de teste**. Ele abre um formulário com origem, destino (as 35 cidades da simulação), tipo de carga, peso, produto e valor. Ao confirmar, a solicitação aparece na lista em menos de um segundo, e as transportadoras cotam em seguida.

### Como funciona

O pedido não é criado pela logística. Quem cria pedidos é o grupo de Pedidos. Enquanto ele não está integrado, o contêiner `pedidos-falso` faz esse papel (D23). Ele ganhou duas rotas, só para o administrador:

| Rota | O que faz |
|---|---|
| `POST /api/v1/pedidos-falso/pedidos` | Publica um `pedido_criado` no Kafka |
| `POST /api/v1/pedidos-falso/pedidos/{id}/cancelamento` | Publica um `pedido_atualizado` com status `CANCELADO` |
| `GET /api/v1/pedidos-falso/cidades` | Lista as cidades que a simulação conhece (para o formulário) |

```text
Tela (admin) ──HTTP──► pedidos-falso ──[pedido_criado]──► Kafka ──► logística ──► transportadoras
```

A logística recebe o pedido **pelo evento**, igual receberia do grupo de Pedidos. Nenhum serviço nosso é chamado por HTTP, então a regra do kit ("nunca avançar o fluxo chamando outro serviço por HTTP") continua valendo. O evento sai no mesmo formato do script `publicar_pedido_falso`, conferido pelo mesmo JSON Schema.

A rota também confere o que o usuário digitou: cidade fora da lista e origem igual ao destino recebem 422 na hora. Sem isso, o pedido iria para a DLT da logística e o usuário não veria nada.

### Onde está

| Arquivo | O que tem |
|---|---|
| `comum/comum/ferramentas/pedidos_falso.py` | O `pedidos-falso`, agora um serviço web (FastAPI) que também consome os nossos eventos |
| `comum/comum/ferramentas/publicar_pedido_falso.py` | `montar_pedido`, usado pelo script e pela rota |
| `frontend/assets/solicitacoes.js` | O botão e o formulário (só aparecem para o admin) |
| `infra/portal/nginx.conf`, `docker-compose.yml` | O caminho `/api/v1/pedidos-falso/` no portal e o token conferido como nos nossos serviços |
| `comum/tests/test_pedidos_falso.py` | 11 testes: só o admin cria, cidade desconhecida, origem igual ao destino, Kafka fora do ar (503), `correlationId` da tela no evento |

## 2. O teste de carga de escrita

### O que faz

O `testes_carga/escrita.js` (k6) repete, 10 vezes por segundo durante 60 s, o que acontece na demonstração:

1. o admin cria um pedido de teste;
2. o teste espera a solicitação ficar `COTADA`;
3. o comprador escolhe a cotação mais barata;
4. o teste espera a transportadora escalar o caminhão;
5. o teste cancela o pedido, o que libera o caminhão para os próximos.

Para achar a solicitação de cada pedido, a lista de solicitações ganhou o filtro `?pedido_id=`. Ele também serve para conferir que cada pedido abriu **uma** solicitação só.

### Resultado (ambiente recém-criado)

| Métrica | Resultado |
|---|---|
| Pedidos | 601, 0% de erros |
| Escolha do frete (p95) | 9,7 ms (o kit pede até 1000 ms) |
| Do pedido às cotações (p95) | 511 ms |
| Solicitações duplicadas | 0 |
| Caminhão ou motorista em duas viagens ao mesmo tempo | 0, em 233 consultas ao banco durante o teste |
| Viagens com caminhão | 491 |
| Sem caminhão livre ou sem cotação | 110 |

Os 110 sem caminhão **não são erro**. A frota do seed tem só 7 caminhões de granel, e com vários pedidos ao mesmo tempo eles acabam. Aí entram as regras: a transportadora sem frota livre não cota (D20), e quando a escolhida recusa a viagem, a logística passa para a próxima cotação ou declara o frete indisponível.

### Como rodar

Com o relógio em 1× (o teste confere e para se não estiver):

```bash
docker run --rm -i --network logistica-grupo5_default -e TAXA=10 grafana/k6:0.54.0 run - < testes_carga/escrita.js
```

## 3. ESP-LOG-001 versão 1.2

A versão 1.0 deixou de fora notificações, ocorrências e PDFs. A 1.2 acrescenta:

| O que | IDs novos |
|---|---|
| Rotas | API-14 a API-18 (ocorrências, documento, notificações) |
| Requisitos | RF-17 (notificações), RF-18 (ocorrências), RF-19 (documentos) |
| Regras | RN-32 (quem recebe cada notificação), RN-33 (ocorrência), RN-34 (conteúdo e número do PDF) |
| Erros | `ENTREGA_ENCERRADA`, `DOCUMENTO_INDISPONIVEL`, `NOTIFICACAO_NAO_ENCONTRADA` |
| Critérios de aceitação | CA-73 (filtro por pedido), CA-74 a CA-81, CA-82 (carga de escrita) |

Os exemplos de resposta vieram de chamadas reais no ambiente, e os números dos documentos foram calculados pela mesma função do código. Agora todas as 18 rotas do serviço estão na especificação.

## 4. O que apareceu no caminho

### Defeito: ocorrência só com espaços

A descrição da ocorrência precisa ter de 5 a 500 caracteres. A conferência contava o texto **antes** de tirar os espaços das pontas. Então `"     "` (5 espaços) passava e era gravada como texto vazio, e o fornecedor recebia uma notificação de ocorrência sem conteúdo. Agora os espaços saem antes de contar: `"     "` e `"  abc  "` recebem 422. Há teste unitário para os dois casos (`test_escolha_e_notificacoes.py`).

### Problema no ambiente: CNHs vencidas

A primeira rodada dos testes de integração falhou em 5 de 6 testes, todos com "a solicitação não ficou COTADA". A causa não estava no código: o relógio do módulo estava em **abril de 2029**. Cada rodada da suíte acelera o relógio (até 100.000×), e ele nunca volta (D18). Depois de muitas rodadas no mesmo ambiente, a hora do módulo passou da validade das CNHs dos dois motoristas da Graneleira. A regra está certa (motorista com CNH vencida não é escalado), então a Graneleira parou de cotar, e os testes, que esperam 3 cotações, receberam 2.

Correções:

- o ambiente foi recriado (`docker compose down -v`), e os 6 testes passaram;
- a suíte agora confere isso no começo e para com uma mensagem clara, em vez de falhar 5 testes sem explicação (`testes_integracao/conftest.py`).

### Problema no k6: travamento

A primeira versão do teste de carga travou o k6 com "index out of range". É um defeito do próprio k6 0.54 quando um `return` sai de dentro de um `try/finally` com várias execuções ao mesmo tempo. O script foi reescrito sem o `try/finally`. Os pedidos da rodada que travou nunca foram cancelados e prenderam a frota; foram cancelados com o mesmo código de limpeza dos testes de integração.

## 5. Perguntas que o professor pode fazer

**O botão não quebra a regra de não chamar outro serviço por HTTP?**
Não. A tela chama o `pedidos-falso`, que faz o papel do grupo de Pedidos. Ele só publica um evento no Kafka. A logística recebe o pedido pelo evento, como no sistema real. Nenhuma etapa do fluxo do frete é disparada por HTTP entre serviços.

**Por que o `pedidos-falso` confere a cidade, se a logística já confere?**
A logística confere ao consumir o evento e, se a cidade não existir, manda o evento para a DLT. O usuário da tela nunca ficaria sabendo. Conferindo antes de publicar, a tela mostra o erro na hora.

**O que o teste de carga de escrita prova, além do tempo de resposta?**
Que, com muitos pedidos ao mesmo tempo, cada pedido abre uma solicitação só (consumo idempotente) e que nenhum caminhão ou motorista vai para duas viagens (reserva condicional no banco). As duas coisas foram conferidas durante o teste, não só no fim.

**Por que tantos pedidos ficaram sem caminhão?**
Porque a frota do seed é pequena (7 caminhões de granel) e o teste cria 10 pedidos por segundo. É o comportamento esperado: quem não tem frota livre não cota, e a recusa leva à próxima cotação. O teste conta esses casos à parte e não os trata como erro.

**Por que o relógio não pode voltar, se isso causou o problema das CNHs?**
Porque prazos, viagens e atrasos já calculados ficariam inconsistentes: uma viagem entregue "no futuro" voltaria a estar em trânsito. A saída foi recriar o ambiente de teste e fazer a suíte avisar quando isso é preciso.
