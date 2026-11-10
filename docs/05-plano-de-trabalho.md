# 05. Plano de trabalho

Proposta de ordem de trabalho. As datas ficam em aberto até o grupo confirmar o prazo final com o professor (pergunta P5 da pauta).

## 1. Fases

| Fase | Objetivo | Entregáveis | Pronto quando |
|---|---|---|---|
| **F0. Alinhamento** | Fechar as decisões e abrir as conversas com os outros grupos | Pauta respondida; issues abertas no GitHub; pedidos enviados a Pedidos, Produtos, Autenticação, Infra, Banco e UX | Todas as decisões "Alta" da pauta têm resposta |
| **F1. Requisitos e contratos** | Escrever o que será construído de forma que o QA consiga testar | Documento de requisitos; ESP-LOG-001 e ESP-TRP-001 no modelo ERS-LLM do QA; contrato de eventos com JSON Schemas e exemplos; proposta de DDL | QA aprova o checklist de prontidão (seção 14 do modelo ERS-LLM) |
| **F2. Base técnica** | Os dois serviços sobem, conectam no banco e no Redpanda e passam nos requisitos transversais | Projeto a partir do boilerplate com as correções da [análise](04-analise-do-kit.md); migrações; produtor único; consumidor com idempotência, retry e DLT; outbox; JWT e RBAC; health e métricas reais | `/health/ready` testa banco e Redpanda; um evento de teste vai e volta |
| **F3. Fluxo de frete** | Do `pedido_criado` ao `frete_selecionado` sem intervenção humana | Solicitação, cadastro de transportadoras com seed, motor de cotação, janela, seleção, cancelamento | Um `pedido_criado` publicado à mão termina em `frete_selecionado` em ≤ 15 s |
| **F4. Comparação** | Comprador entende por que a vencedora venceu | API de comparação, ranking, cotação manual pela transportadora, tela de comparação | Tela mostra as cotações com selos e o gráfico preço × prazo |
| **F5. Rastreio visual** | Comprador vê o caminhão andar | Simulador de viagem, `rastreio_atualizado`, entrega e linha do tempo, `entrega_concluida`, tela com mapa | Viagem Sorriso → Santos roda inteira na tela em poucos minutos e o pedido termina `ENTREGUE` |
| **F6. Qualidade e entrega** | Provar que funciona e documentar | Testes (unitários, de contrato, idempotência, RBAC, concorrência na seleção, carga leve com k6); relatório técnico com ADRs; roteiro da demonstração; slides | QA roda a suíte; demonstração ensaiada |

F3, F4 e F5 dependem de F2, mas podem andar em paralelo entre si: o simulador só precisa de um `frete_selecionado`, que dá para publicar à mão.

## 2. Frentes de trabalho

Sugestão para 5 pessoas. Cada frente tem um dono, mas todos revisam os pull requests uns dos outros.

| Frente | Escopo | Fases | Responsável |
|---|---|---|---|
| **A. Base e integração** | Correções do kit, `common` (produtor, consumidor, outbox, idempotência, auth), Docker, migrações, contato com Infra e Banco | F0, F2 | a definir |
| **B. Logística: frete** | Solicitação, janela, seleção, cancelamento, API de solicitações | F3 | a definir |
| **C. Transportadoras e comparação** | Cadastro, motor de cotação, cotação manual, indicadores, ranking, API de comparação | F3, F4 | a definir |
| **D. Rastreio** | Simulador de viagem, entrega, linha do tempo, conclusão, API de rastreio | F5 | a definir |
| **E. Telas, requisitos e qualidade** | Telas de comparação e rastreio (Leaflet) ou integração com o UX; documento de requisitos e especificações ERS-LLM; testes; relatório | F1, F4, F5, F6 | a definir |

## 3. Primeiras tarefas (F0)

- [ ] Reunião do grupo com a [pauta](06-pauta-de-decisoes.md).
- [ ] Confirmar integrantes e dividir as frentes.
- [ ] Levar ao professor as perguntas da pauta (seção 3).
- [ ] Criar o repositório no GitHub e abrir uma issue por decisão e por pedido a outro grupo.
- [ ] Enviar ao grupo de Pedidos o pedido de campos no `pedido_criado` e de consumo de `frete_selecionado` e `entrega_concluida`.
- [ ] Responder ao grupo de Produtos as pendências P-06 (tipos de transporte) e P-27 (como recebemos o tipo).
- [ ] Propor à Infra os tópicos `rastreio_atualizado` e `entrega_concluida`.
- [ ] Conversar com o UX sobre as telas de fretes e rastreamento (D11).
- [ ] Subir o kit localmente e confirmar os itens K1 a K4 e L1 a L5 da análise.

## 4. Testes que precisamos ter

| Teste | O que prova |
|---|---|
| Seleção pela regra do kit | Menor preço vence; empate de preço vai para o menor prazo; empate total segue o desempate final |
| Idempotência no consumo | O mesmo `cotacao_recebida` 5 vezes gera 1 cotação; o mesmo `pedido_criado` 5 vezes gera 1 solicitação |
| Concorrência na seleção | Rotina de janela e comprador selecionando ao mesmo tempo resulta em um só `frete_selecionado` |
| Cotação atrasada | Cotação que chega depois da seleção não muda a vencedora |
| Duas instâncias | Com `app1` e `app2` rodando, cada janela fecha uma vez e cada passo da viagem é publicado uma vez |
| Rastreio fora de ordem | Evento com `sequencia` antiga não move o veículo para trás |
| Compatibilidade | Carga `REFRIGERADO` só recebe cotação de transportadora refrigerada |
| RBAC | Comprador tentando cotar → 403; transportadora cotando em nome de outra → 403 |
| Paginação | `size=101` → 422 |
| Falha permanente | Payload inválido vai para a DLT depois de 3 tentativas |
| Carga | p95 de leitura do rastreio ≤ 500 ms com polling de muitas telas |

## 5. Roteiro da demonstração

Proposta para a apresentação final, em cerca de 5 minutos:

1. Kafka UI aberto nos tópicos do grupo.
2. Publicar um `pedido_criado` de soja em grão, 24 t, Sorriso (MT) → Santos (SP), ou disparar pelo fluxo dos outros grupos se estiver integrado.
3. Mostrar `solicitacao_frete_criada` e as cotações chegando, uma por transportadora compatível; a refrigerada não cota.
4. Abrir a tela de comparação: tabela, selos e gráfico preço × prazo. Mostrar por que a vencedora venceu.
5. Após a janela, `frete_selecionado` aparece e o pedido vai a `FRETE_SELECIONADO`.
6. Abrir o rastreio: o caminhão sai de Sorriso, para em Campo Grande, a previsão é atualizada e ele chega a Santos.
7. `entrega_concluida` aparece e o pedido termina `ENTREGUE`.
8. Mostrar o ranking atualizado com a entrega feita.
9. Resiliência: derrubar `app1-logistica` no meio da viagem e mostrar que o rastreio continua pela `app2`.
