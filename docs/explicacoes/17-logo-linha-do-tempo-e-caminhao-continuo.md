# 17. Logo, linha do tempo e caminhão andando sem pulos

Em 24/11/2026, quatro incômodos na tela de rastreio: o logo estava diferente do mockup; os ícones da linha do tempo estavam desalinhados; a espera do botão "Atualizar localização" era longa; e o tempo ainda parecia "bugado" com o relógio acelerado.

## 1. Logo do mockup

O mockup publicado do UX trocou a folha por um **anel verde-limão aberto** (`.brand-mark` no código deles: um círculo com borda grossa de `#9be800`, sem o lado direito, girado 30°). O portal agora usa o mesmo desenho, na barra lateral e no ícone da aba do navegador.

## 2. Ícones da linha do tempo

**A causa:** o logo e os ícones da linha do tempo usavam a mesma classe de estilo, `.marca`. O estilo do logo tinha um espaço de 22 px embaixo, pensado para separar o logo do menu, e ele valia também para cada círculo da linha do tempo. O ícone era empurrado para cima dentro do círculo.

**A correção:** o logo passou a usar a classe `.logo`. Os círculos da linha do tempo ficaram só com o estilo deles, sem espaço interno.

## 3. Botão "Atualizar localização"

A espera entre um clique e o próximo caiu de 15 s para **5 s**. O limite de uma consulta por vez continua: clicar várias vezes não abre várias consultas.

## 4. O tempo "bugado"

**O que se via:** com o relógio em 360×, o relógio do topo andava a cada segundo, mas o caminhão e o anel de progresso só mudavam quando chegava uma posição nova do serviço (a cada 30 min da hora do módulo, ou 5 s reais). Entre uma posição e outra, o caminhão ficava parado e depois pulava. A legenda "Atualizado há X min" subia e descia (30, 12, 24, 6...), porque misturava a hora da última posição com a hora da consulta. E a linha do tempo mostrava "Carga em trânsito" com a hora da **primeira** posição, que nunca mudava.

**A correção:**

| Parte | Antes | Agora |
|---|---|---|
| Caminhão e rota percorrida | Mudavam só a cada posição nova | Andam a cada segundo, junto com o relógio do topo |
| Anel de progresso e "Em N dias" | Mudavam só a cada consulta | A cada segundo |
| Legenda do caminhão | "Atualizado há X min" (subia e descia) | "Posição às HH:MM (hora do módulo)" |
| "Carga em trânsito" na linha do tempo | Hora da primeira posição | Hora da última posição |
| Relógio do topo | Podia voltar alguns minutos a cada acerto com o serviço | Nunca volta, a não ser quando o administrador muda a velocidade |

**Como o caminhão anda sem o serviço:** a tela faz a mesma conta que o serviço de transportadoras (`simulacao.progresso`). O caminhão vai da última posição conhecida até o destino em linha reta no tempo, chegando na previsão de chegada. Com a hora do módulo e essa conta, a tela sabe onde ele está a cada segundo.

**O serviço continua mandando:** cada posição nova que chega corrige a da tela. A tela nunca chega ao destino sozinha (para em 99,5%): quem confirma a entrega é o serviço.

**Por que o caminhão nunca volta:** quando o atraso aparece (aos 60% do caminho), a previsão de chegada aumenta e o caminhão passa a andar mais devagar. A tela, que ainda usava a previsão antiga, pode ter andado um pouco à frente do serviço. Nesse caso o caminhão espera o serviço alcançá-lo, em vez de recuar no mapa.

Conferido no navegador: em 360×, o caminhão anda a cada segundo e a legenda acompanha o relógio. Em 3600×, o anel subiu de 55% para 64% em 12 s, sem voltar. Depois de clicar no botão, a contagem foi de 4 s até 1 s e o botão voltou.

## 5. Onde está cada coisa

| Arquivo | O que mudou |
|---|---|
| `frontend/assets/portal.js` | Logo; relógio que nunca volta; evento `portal:segundo` a cada segundo |
| `frontend/assets/portal.css` | Estilo do logo (`.logo`, `.logo-anel`); círculo da linha do tempo sem o espaço do logo |
| `frontend/assets/rastreio.js` | Caminhão, anel e previsão a cada segundo; última posição na linha do tempo; espera de 5 s no botão |
| `frontend/*.html` | Ícone da aba com o anel |
| `docs/06-pauta-de-decisoes.md` | D10: o caminhão anda na tela entre um passo e outro |

## 6. Perguntas que o professor pode fazer

**A tela inventa a posição do caminhão?**
Ela calcula a posição com a mesma regra do serviço, e o serviço corrige a cada leitura. Como a viagem é simulada, não há GPS. A posição do serviço também é uma conta, e a tela só faz essa conta com mais frequência.

**Isso não aumenta as consultas à API?**
Não. A tela continua consultando a cada 5 s (2 s acelerado). O movimento de cada segundo é calculado no navegador, sem rede.

**E se duas pessoas abrirem a mesma entrega?**
As duas veem o mesmo caminhão: a conta depende só da hora do módulo e da última leitura, que são iguais para todos.
