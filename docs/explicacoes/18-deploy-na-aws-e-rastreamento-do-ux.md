# 18. Deploy na AWS e tela de rastreamento do UX

Em 27/11/2026, duas novidades: a Infraestrutura publicou o ambiente de integração na AWS, e revisamos a tela de rastreamento contra os requisitos do grupo de UX.

## 1. Como o deploy na AWS funciona

A Infra montou tudo. O grupo não instala nada da AWS nem entra nos servidores.

1. Alguém dá `git push` na `main` do nosso repositório.
2. O **GitHub Actions** (um robô do GitHub que roda os passos de um arquivo `.yml`) faz o build da imagem Docker e a envia ao **ECR**, o "depósito de imagens" da AWS.
3. O robô pede às máquinas de aplicação que baixem a imagem nova e reiniciem o contêiner. No fim, mostra as últimas 40 linhas do log na aba **Actions**.
4. A API fica no endereço público do gateway da Infra, em `/api/v1/logistica` e `/api/v1/transportadoras`.

O robô usa duas chaves da AWS, cadastradas pela Infra como **Secrets** do repositório (ninguém vê o valor). Por isso o Pedro Cardoso, da Infra, entrou como colaborador.

| Fato do ambiente | O que significa para nós |
|---|---|
| Só a `app1` está ligada (a `app2` fica desligada para economizar créditos) | Rodamos com uma cópia de cada serviço lá. O código já funciona com uma ou duas |
| Desliga das 00:00 às 10:00 | Ver o cuidado com o relógio na seção 3 |
| Banco no RDS (Postgres da AWS), Kafka numa máquina de mensageria | Os endereços chegam por variáveis de ambiente; nada fica fixo no código |

## 2. O que fizemos no nosso repositório

**Dois workflows, um por serviço.** O modelo da Infra supõe um serviço por repositório, com o `Dockerfile` na raiz. O nosso repositório tem dois serviços que usam o mesmo pacote `comum/`. Então:

| Arquivo | Serviço | Roda quando muda |
|---|---|---|
| `.github/workflows/deploy-logistica.yml` | `logistica-service` | `services/logistica-service/`, `comum/` ou o próprio arquivo |
| `.github/workflows/deploy-transportadoras.yml` | `transportadoras-service` | `services/transportadoras-service/`, `comum/` ou o próprio arquivo |

Os dois são cópias do modelo da Infra com três mudanças, explicadas no topo de cada arquivo: o nome do serviço, o build com `-f services/<serviço>/Dockerfile` a partir da raiz, e o filtro de pastas. Um push só de documentação não faz deploy, o que economiza créditos. Pela aba Actions (botão **Run workflow**), o deploy roda sempre.

**Conferido aqui:** as duas imagens foram construídas com o mesmo comando do workflow e postas para rodar só com as variáveis que a AWS injeta. `/health` e `/health/ready` responderam 200 nos dois serviços.

## 3. O que ainda falta para o fluxo funcionar na AWS

Os serviços sobem, mas o fluxo de frete ainda não roda lá. Depende de outros grupos:

| Falta | Por quê | Quem |
|---|---|---|
| Os 4 tópicos novos (`rastreio_atualizado`, `entrega_concluida`, `frete_indisponivel`, `relogio_ajustado`) | Não estão entre os 18 tópicos oficiais. Sem eles não há viagem nem rastreio | Infra (issue #5 do kit) |
| As nossas tabelas no RDS | Ninguém aplica as nossas migrações lá ainda. E o `01-init.sql` do kit cria as tabelas antigas do kit nos nossos schemas, com menos colunas | Infra / Banco (issue #3 nossa) |
| `RS256` no segredo do token | A AWS injeta `JWT_ALGORITHM=HS256`. Com ele, o nosso serviço espera o token antigo do kit e recusa o do Identity-Service | Infra e Autenticação (issue #7 do kit) |
| As nossas telas em `/logistica/` | O gateway da AWS já manda `/logistica/` para uma pasta da Infra, que hoje tem uma página genérica | Infra (copiar a nossa `frontend/`) |

**Cuidado com o relógio do módulo:** a hora do módulo é calculada pelo tempo real que passou desde o último ajuste, vezes o fator. Se o relógio ficar em 360× quando o ambiente desliga à meia-noite, as 10 horas desligado viram 150 dias de módulo: todas as entregas chegam de uma vez e as CNHs do seed vencem. **Antes da meia-noite, volte o relógio para 1×.**

## 4. A tela de rastreamento do UX

O grupo de UX descreveu a tela em 8 requisitos (UX-RAS-01 a UX-RAS-08). A tela deles é uma demonstração fixa (uma entrega fictícia de Sorriso a Santos, mapa desenhado à mão, sem serviço por trás). A nossa é a versão real, alimentada pelos serviços.

| Requisito do UX | O que pede | Nossa tela |
|---|---|---|
| UX-RAS-01 Identificação | % da rota e etapas como indicadores separados | Anel de % e "4 de 5 etapas" |
| UX-RAS-02 Resumo | Data da previsão fixa; o "Em N dias" muda com o relógio | Igual |
| UX-RAS-03 Mapa | Origem, destino, trajeto e veículo, com aviso "Dados simulados"; texto no lugar do mapa se ele falhar | Igual, com a rota pelas estradas |
| UX-RAS-04 Linha do tempo | Eventos em ordem, com horário; confirmação da entrega pendente | Igual |
| UX-RAS-05 Dados da carga | Produto, t/kg, valor, origem, destino e coleta | Igual |
| UX-RAS-06 Motorista | Sem dados pessoais reais; aviso de dado fictício | **Ajustado agora:** aviso "Dados fictícios, só para demonstração" no cartão |
| UX-RAS-07 Documentos | Só um aviso, sem baixar nada | Geramos um PDF com a marca "sem valor fiscal" (vamos além) |
| UX-RAS-08 Ocorrência | Tipo obrigatório, descrição de 1 a 500 caracteres, número de protocolo | **Ajustado agora:** de 1 a 500 caracteres (antes, de 5 a 500) e protocolo no aviso e na linha do tempo |

**O protocolo** é `OC-` mais os 8 primeiros caracteres do número da ocorrência (por exemplo `OC-78E31D9B`). Ele aparece no aviso depois de enviar e na linha do tempo, para a pessoa citar depois.

**Por que mudar o mínimo de caracteres também na API, e não só na tela?** A regra mora na API (ESP-LOG-001, RN-33). Se só a tela mudasse, uma ocorrência de 3 letras passaria na tela e voltaria com erro. Os espaços das pontas continuam saindo antes de contar: uma ocorrência só com espaços ainda é recusada. A ESP-LOG-001 foi para a versão 1.8.

## 5. Perguntas que o professor pode fazer

**Por que dois workflows e não um?**
Cada serviço tem a sua imagem e o seu contêiner na AWS. Com dois arquivos, mudar só o serviço de transportadoras não refaz o deploy da logística. O pacote `comum/` é dos dois, então mudá-lo refaz os dois.

**As senhas do banco estão no repositório?**
Não. A AWS guarda as senhas no Secrets Manager e as entrega ao contêiner como variáveis de ambiente quando ele sobe. O código só lê `DB_PASSWORD`, `JWT_SECRET_KEY` e as outras pelo nome.

**Se o deploy quebrar, como saber?**
Na aba Actions do GitHub. O workflow fica vermelho quando o contêiner não continua rodando depois de subir, e mostra as últimas 40 linhas do log.

**Por que a tela de vocês é diferente da do UX em alguns pontos (documentos em PDF, telefone para o fornecedor)?**
A tela do UX é uma demonstração sem serviço por trás, e por isso só mostra avisos. A nossa usa dados do serviço, que também são fictícios. O telefone e a CNH seguem o perfil (RN-37): o comprador não vê nenhum dos dois.
