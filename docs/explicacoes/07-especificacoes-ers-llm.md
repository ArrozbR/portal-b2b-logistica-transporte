# 07. Especificações para o grupo de Teste e Qualidade (ERS-LLM)

Continua a [explicação 06](06-encaixe-com-outros-grupos.md). Esta parte escreve a especificação de cada serviço no modelo do grupo de Teste e Qualidade e corrige quatro defeitos que apareceram ao escrever.

## 1. O que foi feito

| Entrega | Onde |
|---|---|
| Especificação do `logistica-service`: 13 rotas, 4 tópicos consumidos, 6 publicados, 16 requisitos, 31 regras, 72 critérios de aceitação | [ESP-LOG-001](../especificacoes/ESP-LOG-001_Logistica.md) |
| Especificação do `transportadoras-service`: 17 rotas, 4 tópicos consumidos, 3 publicados, 13 requisitos, 23 regras, 42 critérios | [ESP-TRP-001](../especificacoes/ESP-TRP-001_Transportadoras.md) |
| Quatro defeitos corrigidos, cada um com teste | Seção 5 |

## 2. O que é o ERS-LLM

O grupo de Teste e Qualidade criou um modelo de documento de requisitos pensado para uma LLM implementar o serviço **sem poder fazer perguntas**. A ideia deles: "uma LLM não pergunta, ela supõe". Tudo o que o documento não decide, ela decide sozinha, e não necessariamente como a gente queria.

O processo deles tem estas etapas:

1. O grupo dono do serviço escreve o documento.
2. O QA revisa com um checklist (o **gate G1**). Só passa se não houver nada vago nem questão em aberto.
3. O QA transforma cada critério de aceitação num teste automático.
4. Uma LLM gera o código só a partir do documento.
5. Os testes medem a conformidade: a fração de critérios atendidos precisa ser pelo menos 0,85.

Para nós, a especificação serve para duas coisas: é a descrição oficial do serviço que o QA usa para testar, e é um documento a partir do qual daria para gerar o serviço de novo.

### Termos do modelo

| Termo | O que é | Exemplo |
|---|---|---|
| **RF** (requisito funcional) | Uma coisa que o serviço faz, escrita no padrão EARS ("Quando..., o serviço deve...") | RF-06: escolha do frete pelo comprador |
| **RN** (regra de negócio) | Uma regra com um exemplo concreto | RN-13: menor preço → menor prazo → pontualidade → ordem alfabética |
| **CA** (critério de aceitação) | Um exemplo com valores exatos, no formato Dado / Quando / Então (Gherkin). Vira um teste | CA-23: reenvio com a mesma chave devolve a mesma resposta |
| **Ordem de verificação** | Qual erro responder quando mais de um se aplica | Corpo inválido **e** usuário sem permissão → 403, não 422 |
| **Cenário base** | Os dados de partida de todos os CAs | Pedido P-1: 24 t de soja de Sorriso a Santos |
| **Matriz de rastreabilidade** | Tabela que liga cada RF às suas regras, rotas e CAs | RF-06 → RN-12 a RN-17 → API-06 → CA-21 a CA-33 |

## 3. Como a especificação foi escrita

### 3.1 O código como ele é, não o ideal

A especificação descreve o que o código faz hoje. Se ela dissesse outra coisa, os testes do QA falhariam contra o nosso serviço. Por isso:

- Os exemplos de resposta e de erro foram **capturados do ambiente**: um script fez mais de 90 chamadas e guardou as respostas.
- Os valores dos critérios (distância, preço, prazo, datas, ids das cotações, motorista sorteado, atraso) foram **calculados pelas mesmas funções do código**, não à mão.
- Os critérios mais difíceis foram **conferidos no ambiente** (seção 6).

### 3.2 Teste caixa-preta no ambiente real

O modelo do QA supõe que o serviço recebe o Kafka e o relógio como "portas" trocáveis, para o teste injetar versões falsas. O nosso serviço já existe e usa o Kafka e o PostgreSQL de verdade. Então os critérios são conferidos como caixa-preta: o teste chama a API pelo portal, publica e lê eventos no Kafka e, só para conferir, consulta o banco, como os nossos testes de `testes_integracao/`.

O relógio do módulo faz o papel do relógio controlável: o teste acelera ou adianta pela rota do administrador. Ele não volta e não pode ser posto num instante exato. Por isso os critérios usam uma hora de referência (T0, 10/11/2026 12:00 UTC) e, em outro horário, o teste confere as mesmas relações (o prazo é a abertura + 12 h, a coleta é o próximo dia útil).

### 3.3 O que ficou de fora da versão 1.0

Notificações, ocorrências e documentos em PDF existem no serviço, mas ficaram para a versão 1.1 da ESP-LOG-001. A versão 1.0 cobre o núcleo do fluxo do frete, que é o que os outros grupos e o QA precisam primeiro.

### 3.4 Um critério com dois resultados aceitos

Quando o prazo de 12 h vence, o comprador recebe `PRAZO_DE_ESCOLHA_ENCERRADO` só até a rotina de prazos rodar (ela roda a cada 1 s). Depois disso, a regra automática já escolheu e a resposta é `FRETE_JA_ESCOLHIDO`. O CA-31 aceita os dois códigos e confere o resultado final: a escolha automática da mais barata. Está registrado como decisão (Q-07).

## 4. Onde está cada coisa

| Arquivo | O que tem |
|---|---|
| `docs/especificacoes/ESP-LOG-001_Logistica.md` | Especificação da logística, com a tabela das 35 cidades (Apêndice A) |
| `docs/especificacoes/ESP-TRP-001_Transportadoras.md` | Especificação das transportadoras, com os seeds de transportadoras, motoristas e veículos (Apêndice A) |
| `services/transportadoras-service/transportadoras/api.py` | Correções 1 e 4 |
| `comum/comum/contratos/rastreio_atualizado.schema.json` | Correção 2 |
| `services/logistica-service/logistica/api.py` | Correção 3 |
| `testes_integracao/test_cadastro_da_frota.py` | Teste da correção 1 |
| `comum/tests/test_eventos.py`, `services/logistica-service/tests/test_escolha_e_notificacoes.py`, `services/transportadoras-service/tests/test_cargas_disponiveis.py` | Testes das correções 2, 3 e 4 |

## 5. Os quatro defeitos

Cada linha da tabela de erros obriga a perguntar "e se...?". Quatro perguntas tiveram resposta errada.

| # | Onde | O que acontecia | Agora | Teste |
|---|---|---|---|---|
| 1 | Alterar motorista ou veículo | Com a CNH de outro motorista ou a placa de outro veículo, a restrição do banco estourava e a resposta era **500** | **409** `MOTORISTA_DUPLICADO` ou `PLACA_DUPLICADA`, como no cadastro. A própria CNH e a própria placa não contam | Integração: falhou com a imagem antiga, passa com a nova |
| 2 | Contrato do `rastreio_atualizado` | `VIAGEM_ALOCADA` sem `posicao` passava no contrato. A logística quebrava ao gravar a posição e tentava de novo 3 vezes (7 s) antes da DLT | O contrato exige `posicao`: a mensagem vai **direto** para a DLT | Unitário |
| 3 | Fator do relógio | O banco guarda o fator com 2 casas. `0.001` virava `0.00` e dava **500**; `1.234` era publicado para as transportadoras como 1,234, mas lido do banco como 1,23 (os dois serviços com relógios diferentes) | Fator com mais de 2 casas → **422** | Unitário e ambiente |
| 4 | Cargas da transportadora | Um pedido cancelado depois da escolha aparecia como **"Você venceu"** para a transportadora escolhida | Aparece como "Pedido cancelado" | Unitário |

O defeito 3 é o mais interessante para sistemas distribuídos: o mesmo dado (o fator) tinha dois valores, um na mensagem e outro no banco, e cada serviço calcularia uma hora diferente.

## 6. O que foi conferido no ambiente

| Verificação | Resultado |
|---|---|
| Todas as rotas e erros dos exemplos (mais de 90 chamadas) | Iguais ao especificado |
| Ordem dos erros | JSON ilegível → 422 antes do token; sem token → 401 antes do `size=101`; corpo inválido → 422 antes da falta do `Idempotency-Key` |
| Idempotência da escolha | Mesma chave e mesmo usuário → mesma resposta com `X-Idempotent-Replay: true`; mesma chave, outro usuário → não é replay |
| Data ilegível num evento (`"31/11/2026"`) | DLT em 7 s, com `failedAtAttempt` 4 (as 3 retentativas) |
| Redpanda parado durante a escolha | Escolha respondeu 200 em 0,5 s; o `frete_selecionado` esperou na outbox e foi publicado uma vez, 4 s depois de o Redpanda voltar |
| Simulação de uma viagem com `entregaId` fixo | 3 cotações com os valores, ids e datas previstos; motorista Marcos Vieira e veículo QWE3F45; coleta 2 h depois da escala; parada em Jataí - GO; atraso de 26,6 h revelado; entrega com 16,6 h de atraso; sequências 1 a 6 sem buraco; frota liberada no fim |
| Testes | 104 unitários e 6 de integração passando |

## 7. Como usar

- **Para o QA:** enviar os dois arquivos. O checklist do §14 é preenchido por eles no gate G1.
- **Para o grupo:** ao mudar uma rota, um campo, um erro, a ordem das verificações, um evento ou uma regra, atualizar a ESP do serviço e registrar a versão no §15 dela (regra no `CLAUDE.md`).
- **Para ler:** comece pelo §2 (contexto), depois o §8.0 (cenário base) e a matriz do §12. As tabelas de rotas do §7.2 resumem o que cada rota faz e quais erros responde, na ordem.

## 8. Perguntas que o professor pode fazer

**O que é o ERS-LLM?**
Um modelo de documento de requisitos do grupo de Teste e Qualidade, feito para uma LLM implementar sem perguntar nada. Cada regra tem um exemplo, cada erro tem um código e uma ordem, e cada requisito tem critérios de aceitação com valores exatos, que viram testes.

**Por que escrever a especificação depois do código?**
O modelo do QA ficou pronto depois que os serviços já estavam em andamento. Então a especificação descreve o que foi implementado e conferido, para o QA testar o serviço real. A partir dela, também daria para gerar o serviço de novo.

**Como vocês sabem que a especificação está certa?**
Os exemplos foram capturados do ambiente, os valores foram calculados pelas funções do código, e os critérios mais difíceis foram rodados no ambiente. Onde o código estava errado, o código foi corrigido, não a especificação.

**O modelo do QA usa versões falsas do Kafka e do relógio. Por que vocês não?**
Porque o serviço já existe com o Kafka e o banco de verdade. O teste é caixa-preta: chama a API e lê os eventos. O relógio do módulo já é controlável pela rota do administrador.

**O que é a "ordem de verificação" e por que importa?**
Quando uma requisição tem dois problemas ao mesmo tempo (por exemplo, corpo inválido e usuário sem permissão), o serviço precisa responder sempre o mesmo erro. Sem a ordem escrita, cada implementação responde um, e o teste fica instável.

**Por que um comprador de outra empresa recebe 404, e não 403?**
Para não revelar que a solicitação existe. Um 403 diria "existe, mas não é sua".

**Que defeitos a especificação revelou?**
Quatro (seção 5). O mais importante é o do fator do relógio: a mensagem levava um valor e o banco guardava outro, e os dois serviços calculariam horas diferentes.

**Por que um critério aceita dois códigos de erro?**
Porque o prazo vencido só aparece como erro próprio até a rotina de prazos rodar, no máximo 1 s depois. Depois, o frete já foi escolhido automaticamente. O critério confere o que importa: a escolha automática da mais barata.
