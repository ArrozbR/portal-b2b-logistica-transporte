# 06. Encaixe com as definições dos outros grupos

Continua a [explicação 05](05-testes-distribuidos-e-carga.md). Em 10/11/2026 o grupo de Fornecimento e Produtos terminou os serviços dele e publicou o que já tinha combinado com o grupo de Autenticação. Esta parte ajusta o nosso código para encaixar nessas definições e corrige um defeito que apareceu ao testar.

## 1. O que mudou

| Mudança | Antes | Agora | Por quê |
|---|---|---|---|
| **Token** (D25, ADR-026) | HS256 com chave compartilhada; claims `empresaId` e `perfil` (formato do kit) | RS256 do grupo de Autenticação, validado pela chave pública do JWKS; claims `tenant_id` e `active_scope` | É o formato do serviço que faz o login de verdade. O formato do kit continua disponível por configuração |
| **DLT** | `eventoOriginal`, `erro`, `tentativas` | `originalEvent`, `error`, `stackTrace`, `failedAtAttempt` (mais `originalTopic`) | É o formato da biblioteca comum do kit, que os outros grupos usam |
| **`pedido_criado`** | Sem `fornecimentoId` | `fornecimentoId` opcional no contrato e no pedido falso | O grupo de Produtos pediu esse campo ao grupo de Pedidos; o nosso teste passa a usar o mesmo formato |
| **Escala** (defeito) | Agendava a viagem mesmo se o pedido já tivesse sido cancelado | Não agenda | Ver seção 3.3 |
| **Testes de integração** | Um teste podia atrapalhar o seguinte | Cada teste começa e termina sem pedidos de teste em aberto | Ver seção 3.4 |

## 2. Onde está cada coisa

| Arquivo | O que tem |
|---|---|
| `comum/comum/auth.py` | Validação do token (RS256 ou HS256) e a tradução para os perfis do módulo |
| `comum/comum/ferramentas/usuarios_falso.py` | O login de demonstração, agora emitindo tokens RS256 e publicando o JWKS |
| `comum/comum/ferramentas/gerar_token.py` | Pede o token ao `usuarios-falso` (só ele tem a chave privada) |
| `comum/comum/consumidor.py` | `montar_payload_dlt`: o payload da DLT no formato do kit |
| `services/transportadoras-service/transportadoras/servico.py` | `escalar`: não agenda viagem de pedido cancelado |
| `comum/tests/test_auth.py`, `comum/tests/test_consumidor.py` | 19 testes unitários novos |
| `testes_integracao/` | Limpeza entre testes e o cenário 4 (cancelamento fora de ordem) |
| `docker-compose.yml`, `.env.example`, `infra/portal/nginx.conf` | `JWT_ALGORITHM`, `AUTH_JWKS_URL` e o caminho `/.well-known/jwks.json` no portal |

## 3. As ideias principais

### 3.1 HS256 × RS256

| | HS256 (kit) | RS256 (Autenticação) |
|---|---|---|
| Chave | Uma só, a mesma para assinar e para conferir | Um par: a privada assina, a pública confere |
| Quem tem a chave | Todos os serviços | A privada só a Autenticação; a pública qualquer um |
| Risco | Qualquer serviço consegue criar um token falso de qualquer usuário | Só a Autenticação cria tokens |

A chave pública fica num endereço padrão, o **JWKS** (`/.well-known/jwks.json`). Cada token diz no cabeçalho qual chave o assinou (`kid`). O serviço busca o JWKS uma vez e guarda por 1 hora. Se aparecer um `kid` novo (a Autenticação trocou a chave), ele busca de novo, no máximo a cada 5 s.

Dois cuidados:

- O algoritmo vem da **configuração**, nunca do token. Um ataque conhecido é mandar um token dizendo "algoritmo: nenhum" ou trocar RS256 por HS256 para enganar a validação.
- Se o JWKS estiver fora do ar, a resposta é 503 (tente de novo), não 401. Um 401 faria a tela deslogar o usuário sem ele ter feito nada de errado.

### 3.2 Tradução dos perfis

| Token da Autenticação | Perfil no módulo |
|---|---|
| `active_scope` BUYER | comprador |
| `active_scope` SUPPLIER | fornecedor |
| `active_scope` CARRIER | transportadora |
| permissão `logistica:admin` | admin |
| `active_scope` TENANT_ADMIN, sem a permissão | 403 |

O `TENANT_ADMIN` é o administrador **de uma empresa**. O nosso admin vê as entregas de todas as empresas e mexe no relógio do módulo. Se os dois fossem a mesma coisa, o administrador de qualquer empresa veria as entregas dos concorrentes. Por isso o admin do módulo é quem tem a permissão `logistica:admin`, no padrão `recurso:ação` que a Autenticação já usa (`produtos:criar`).

> **Atualizado depois:** o código do Identity-Service tem o administrador global da plataforma (`platform_role` `PLATFORM_ADMIN`), e é ele o admin do módulo agora; `logistica:admin` ficou como alternativa. O token deles também traz `iss` e `aud`, que passamos a conferir. Ver a [explicação 08](08-token-do-identity-service.md).

### 3.3 O defeito: cancelamento chegando antes da escolha

O cancelamento (`pedido_atualizado`) e a escolha do frete (`frete_selecionado`) são **tópicos diferentes**. O Kafka só garante a ordem dentro de um tópico (e de uma partição), então eles podem chegar em qualquer ordem.

1. O comprador escolhe o frete: a logística publica `frete_selecionado`.
2. Logo em seguida, o pedido é cancelado: o grupo de Pedidos publica `pedido_atualizado` com `CANCELADO`.
3. As transportadoras recebem o cancelamento **primeiro**: não há viagem para cancelar; elas só marcam a solicitação como cancelada.
4. Depois chega o `frete_selecionado`, e a escala agendava a viagem mesmo assim. Caminhão e motorista ficavam presos num pedido que não existe mais.

A correção: antes de escalar, a escala confere se a solicitação foi cancelada. A logística já tinha essa proteção para o caso parecido do `pedido_criado` (ADR-013); faltava nas transportadoras.

O teste de integração 4 reproduz exatamente essa ordem: publica o cancelamento, espera as transportadoras registrarem e só então publica o `frete_selecionado`. Rodado antes da correção, ele **falhou** (a viagem foi agendada). Depois da correção, passa.

### 3.4 Testes que não se atrapalham

Cada teste deixava pedidos em aberto. No teste seguinte, o relógio acelerado fazia vencer o prazo de 12 h dessas sobras, a regra automática escolhia a mais barata (a Econômica) e o caminhão compatível dela ficava ocupado. O teste seguinte esperava 3 cotações e recebia 2. Nas rodadas anteriores tinha passado por sorte na ordem.

Agora, antes e depois de cada teste, os pedidos de teste em aberto são cancelados pelo mesmo caminho que o grupo de Pedidos usaria (`pedido_atualizado` com `CANCELADO`), e o teste espera até a frota toda estar livre.

## 4. Como ver funcionando

```bash
docker compose up -d --build
curl http://localhost:8088/.well-known/jwks.json          # a chave pública
docker compose exec logistica-1 python -m comum.ferramentas.gerar_token --perfil admin
.venv/Scripts/python -m pytest                            # unitários
.venv/Scripts/python -m pytest testes_integracao -v       # integração
```

Para rodar com o kit atual (HS256), ponha `JWT_ALGORITHM=HS256` e a `JWT_SECRET_KEY` do kit no `.env`.

O `usuarios-falso` gera uma chave nova toda vez que sobe. Se ele reiniciar, os tokens antigos deixam de valer quando os serviços buscarem o JWKS de novo, e é só entrar de novo na tela.

## 5. O que foi testado

| Verificação | Resultado |
|---|---|
| Unitários do token: os 3 escopos, admin pela permissão, `TENANT_ADMIN` sozinho, escopo desconhecido ou em minúsculas, sem empresa, outra chave, `kid` desconhecido, sem `kid`, HS256 no lugar de RS256, malformado, expirado, JWKS fora do ar, formato do kit, algoritmo inválido na configuração | 16 testes passando |
| Unitários do consumidor: falha temporária (4 chamadas, DLT com `failedAtAttempt` 4), evento inválido (direto para a DLT), mensagem que nem é JSON | 3 testes passando (as 3 tentativas tinham ficado sem teste na etapa 5) |
| Ambiente: login RS256, comprador lista entregas (200) e é barrado no relógio (403), admin ajusta o relógio (200), transportadora vê a própria frota, token HS256 recusado (401), `gerar_token` | Tudo como esperado |
| Ambiente: `usuarios-falso` reiniciado com chave nova | As 4 cópias aceitam o token novo sem reiniciar |
| Ambiente: pedido com cidade inexistente | A DLT recebe `originalEvent`, `error`, `stackTrace`, `failedAtAttempt` e `originalTopic` |
| Integração: o cenário 4 com a imagem antiga | Falhou: a viagem do pedido cancelado foi agendada |
| Integração: os 5 testes, com a correção e o token RS256 | 5 passaram em duas rodadas seguidas (163 s cada) |

## 6. Perguntas que o professor pode fazer

**Por que trocar HS256 por RS256?**
Com HS256, todos os serviços têm a mesma chave, e qualquer um deles consegue criar um token falso, até de administrador. Com RS256, só a Autenticação tem a chave que assina; os outros só conferem.

**Como o serviço consegue a chave pública sem chamar a Autenticação a cada requisição?**
Busca o JWKS uma vez e guarda por 1 hora. Só busca de novo se aparecer um token assinado por uma chave que ele não conhece.

**E se alguém mandar tokens com `kid` inventado para fazer o serviço buscar o JWKS sem parar?**
A nova busca acontece no máximo a cada 5 s, então isso não sobrecarrega nada.

**Por que o administrador de uma empresa não é administrador do módulo?**
Porque o admin do módulo vê as entregas de todas as empresas e mexe no relógio. O administrador de uma empresa veria as entregas dos concorrentes.

**Por que manter o HS256?**
Porque o kit da Infraestrutura ainda usa HS256. Enquanto ele não for atualizado, quem rodar os nossos serviços no kit precisa desse formato. É uma variável de ambiente; o padrão é RS256.

**Como vocês acharam o defeito do cancelamento?**
Ao investigar um teste que falhava. A causa do teste era outra (sobras de um teste atrapalhando o seguinte), mas, ao ler o caminho do cancelamento, vimos que a escala não conferia se o pedido tinha sido cancelado. Escrevemos um teste que força a ordem ruim; ele falhou antes da correção e passou depois.

**Esse tipo de defeito é comum em sistemas distribuídos?**
Sim. É a suposição errada de que as mensagens chegam na ordem em que foram enviadas. Entre tópicos diferentes, não há essa garantia. A defesa é cada serviço registrar o que já sabe (o pedido foi cancelado) e conferir antes de agir.
