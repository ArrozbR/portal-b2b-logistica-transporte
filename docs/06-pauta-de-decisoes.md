# 06. Pauta de decisões

Documento para a reunião do grupo. Cada decisão tem o contexto, as opções e uma recomendação para começar a conversa. A recomendação não é decisão: o grupo pode escolher outra opção. Depois da reunião, preencher a coluna "Decisão" e mover o que for aceito para o relatório técnico como ADR.

## 1. Resumo

| ID | Decisão | Recomendação | Prioridade | Decisão |
|---|---|---|:---:|---|
| D1 | Quantos serviços | Manter os 2 do kit | Alta | |
| D2 | De onde vêm origem, destino, tipo de carga e peso | Pedir que `pedido_criado` traga esses dados | Alta | |
| D3 | Cotação automática, manual ou as duas | As duas | Alta | |
| D4 | Janela de cotação e mínimo de cotações | Configurável, 10 s por padrão, mínimo 1 | Alta | |
| D5 | Comprador pode escolher outra cotação | Sim, só dentro da janela, se o professor aceitar | Média | |
| D6 | O que é "comparação entre empresas de entrega" | Comparação das cotações e ranking de desempenho | Alta | |
| D7 | Transportadoras reais ou simuladas | Simuladas | Alta | |
| D8 | De onde vem a posição do caminhão | Simulador no `transportadoras-service` | Alta | |
| D9 | Desenho da rota no mapa | Linha interpolada; estrada como extra | Média | |
| D10 | Como a tela recebe atualizações | Polling de 5 s; SSE como extra | Média | |
| D11 | Quem faz as telas | Conversar com o UX; garantir uma tela nossa para a demo | Alta | |
| D12 | Como avisar que a entrega terminou | Tópicos novos `rastreio_atualizado` e `entrega_concluida` | Alta | |
| D13 | Consistência entre banco e Kafka | Outbox transacional | Média | |
| D14 | Tarefas com tempo em duas instâncias | `FOR UPDATE SKIP LOCKED` no banco | Média | |
| D15 | Coordenadas das cidades | Tabela fixa com ~30 cidades | Baixa | |
| D16 | Stack | Python 3.12, FastAPI, aiokafka, psycopg2; tela em HTML + Leaflet | Média | |
| D17 | Divisão do grupo e datas | Frentes A a E do plano | Alta | |

## 2. Decisões

### D1. Quantos serviços

O kit define `logistica-service` e `transportadoras-service`, com porta, schema, usuário de banco e rota no gateway prontos.

- **A. Manter os 2.** Rastreio dentro da logística; simulação e cotação nas transportadoras.
- **B. Criar um terceiro, `rastreio-service`.** Separa melhor, mas exige porta, schema, role e rota novos da Infra e do Banco.

**Recomendação: A.** O rastreio é parte da entrega, que já é da logística, e a separação não traz ganho que pague a dependência de outros dois grupos.

### D2. De onde vêm origem, destino, tipo de carga e peso

O `pedido_criado` do kit não tem nenhum desses dados, e sem eles não há cotação nem mapa. O grupo de Produtos já nos perguntou isso (P-27 do documento deles).

- **A. Pedir que o `pedido_criado` traga tudo.** Um consumidor só, sem cópias locais. Depende do grupo de Pedidos aceitar.
- **B. Montar cópias locais** consumindo `produto_cadastrado` (tipo), `fornecimento_criado` (origem) e `empresa_cadastrada` (endereço do comprador). Não depende de Pedidos, mas são três consumidores a mais, e o endereço do comprador ainda não existe em evento nenhum.
- **C. Perguntar por HTTP** a cada pedido. Contraria o guia.

**Recomendação: A**, com B como plano reserva para o tipo de carga.

### D3. Cotação automática, manual ou as duas

O kit simula as cotações. O mockup do UX mostra a transportadora preenchendo a cotação à mão.

- **A. Só automática.** Simples e cabe nos 10 s, mas a tela do UX fica sem uso.
- **B. Só manual.** Mais realista, mas a demonstração depende de alguém digitando e não cabe na janela.
- **C. As duas.** Automáticas garantem o fluxo; manuais usam a tela do UX e entram se a janela estiver aberta.

**Recomendação: C.**

### D4. Janela de cotação e mínimo de cotações

O guia diz "até 10 s". O boilerplate exige pelo menos 2 cotações. Não está definido o que fazer com 1 ou 0.

- Duração: **A.** 10 s fixos; **B.** configurável por variável de ambiente, 10 s por padrão; **C.** maior quando houver transportadoras com cotação manual.
- Mínimo: **1** (carga refrigerada ou perigosa pode ter uma transportadora só) ou **2** (comparação sempre possível).
- Sem nenhuma cotação: reabrir uma vez com janela maior; se falhar de novo, `SEM_COTACAO` e o pedido fica em `AGUARDANDO_FRETE`.

**Recomendação: B, mínimo 1**, com a reabertura descrita. A comparação com 1 cotação mostra só ela, com aviso.

### D5. Comprador pode escolher outra cotação

O kit chama a regra de inegociável, mas o boilerplate já aceita `cotacaoId` no corpo da seleção.

- **A. Não.** Seleção sempre automática.
- **B. Sim, só enquanto a janela estiver aberta.** Depois a regra automática decide.
- **C. Sim, sem limite de tempo.** A seleção espera o comprador.

**Recomendação: B, se o professor aceitar (P2).** Senão, A. O `frete_selecionado` traz o `criterio` usado.

### D6. O que é "comparação entre empresas de entrega"

- **A. Comparar as cotações de uma solicitação** lado a lado, com selos e gráfico preço × prazo.
- **B. Ranking histórico** das transportadoras: % no prazo, atraso médio, preço médio por t·km.
- **C. As duas.** A comparação de cotações mostra também o histórico de cada transportadora.

**Recomendação: C.** Sem o histórico, a comparação mostra só preço e prazo, que a regra do kit já resolve sozinha.

### D7. Transportadoras reais ou simuladas

Agregadores como o Melhor Envio têm ambiente de testes com cotação em várias transportadoras, mas são feitos para encomendas, não para 24 t de grãos.

- **A. Simuladas**, com perfis diferentes (arquitetura, seção 5.3).
- **B. Reais** por agregador.
- **C. Simuladas, com um adaptador para uma API real** como extra, se sobrar tempo.

**Recomendação: A**, deixando o motor de cotação atrás de uma interface para C ser possível depois.

### D8. De onde vem a posição do caminhão

- **A. Simulador no `transportadoras-service`.** Quem cota é quem informa a posição, como no mundo real.
- **B. Simulador como serviço ou script separado** que publica no Kafka.
- **C. Só eventos manuais** da transportadora.

**Recomendação: A**, com C como complemento opcional.

### D9. Desenho da rota no mapa

- **A. Linha interpolada** entre origem e destino (uns 50 pontos). Sem dependência externa.
- **B. Rota por estrada** calculada uma vez pelo servidor público do OSRM e guardada na viagem. Fica bonito, mas depende de um serviço externo com limite de uso.

**Recomendação: A no MVP, B como extra.**

### D10. Como a tela recebe atualizações

Detalhe na [arquitetura](02-arquitetura-proposta.md), seção 6.3. Com duas instâncias, a tela sempre lê do banco.

- **A. Polling a cada 5 s.** Nada muda no gateway.
- **B. SSE.** Mais "tempo real", precisa de ajuste no Nginx.
- **C. WebSocket.** Bidirecional, que não precisamos.

**Recomendação: A, com B como extra.**

### D11. Quem faz as telas

O guia dá as telas ao grupo de UX, mas o rastreio visual e a comparação foram pedidos a nós. O UX já tem os mockups.

- **A. UX faz**, nós entregamos a API.
- **B. Nós fazemos** uma tela própria em `/logistica/`.
- **C. Nós fazemos uma versão funcional** (mapa, linha do tempo, comparação) e o UX aplica o design system ou reaproveita.

**Recomendação: conversar com o UX e o professor (P4).** Em qualquer caso, ter uma tela nossa funcionando para a demonstração, para não depender de outro grupo.

### D12. Como avisar que a entrega terminou

Hoje o pedido só chega a `ENTREGUE` por `PATCH` HTTP.

- **A. Tópicos novos** `rastreio_atualizado` (transportadoras → logística) e `entrega_concluida` (logística → pedidos).
- **B. Publicar em `pedido_atualizado`.** O tópico é do `pedidos-service`; não somos donos.
- **C. Chamar o `PATCH` do `pedidos-service`.** Contraria o guia.

**Recomendação: A.** Payloads na seção 3 de [eventos](03-eventos-e-integracoes.md).

### D13. Consistência entre banco e Kafka

Se o serviço grava no banco e cai antes de publicar, o evento se perde; se publica e o commit falha, o evento sai sem o dado.

- **A. Outbox transacional.** Grava o evento numa tabela na mesma transação; uma rotina publica e marca. Entrega pelo menos uma vez; os consumidores já são idempotentes.
- **B. Publicar depois do commit** e aceitar o risco.

**Recomendação: A.** É o ponto mais "sistemas distribuídos" do trabalho e cabe bem no relatório.

### D14. Tarefas com tempo em duas instâncias

Fechar a janela e avançar a viagem são tarefas com hora marcada, e `app1` e `app2` rodam ao mesmo tempo.

- **A. Cada instância roda a rotina e pega o trabalho vencido com `SELECT ... FOR UPDATE SKIP LOCKED`.** Sem coordenador; se uma cai, a outra continua.
- **B. Só uma instância roda as rotinas** (variável `RUN_JOBS=true`). Simples, mas se ela cair as rotinas param.
- **C. Lease com expiração** gravado no banco.

**Recomendação: A.**

### D15. Coordenadas das cidades

- **A. Tabela fixa** com ~30 cidades do cenário (polos do agro e portos).
- **B. Base completa** de municípios do IBGE com coordenadas (~5.570 linhas).
- **C. Geocodificação por CEP** numa API externa.

**Recomendação: A**, trocável por B se os outros grupos usarem cidades fora da lista.

### D16. Stack

O kit e o grupo de Produtos usam Python 3.12 e FastAPI.

- Serviços: **Python 3.12, FastAPI, `aiokafka`, `psycopg2`** com pool de até 5 conexões, como o kit.
- Tela: **HTML + JavaScript + Leaflet** (simples, entra no contêiner de front do kit) ou React + Vite (se o UX usar).
- Testes: `pytest` com `httpx`; k6 para carga.

**Recomendação: igual ao kit**, e a tela no que o UX usar.

### D17. Divisão do grupo e datas

Ver as frentes A a E no [plano de trabalho](05-plano-de-trabalho.md), seção 2. Falta o prazo final (P5).

## 3. Perguntas para o professor

| ID | Pergunta | Afeta |
|---|---|---|
| P1 | O rastreio visual pode usar posição simulada? Que nível de tela é esperado? | D8, D9, D11 |
| P2 | A regra "menor preço, desempate por menor prazo" é obrigatória, ou o comprador pode escolher outra cotação? | D5, D6 |
| P3 | Podemos propor tópicos novos ao kit, ou o catálogo de 15 tópicos é fechado? | D12 |
| P4 | As telas de comparação e rastreio são nossas ou do grupo de UX? | D11 |
| P5 | Qual o prazo final, o que é entregue (código, relatório, apresentação) e a integração com os outros grupos é cobrada ou podemos demonstrar com eventos simulados? | D17, plano |
