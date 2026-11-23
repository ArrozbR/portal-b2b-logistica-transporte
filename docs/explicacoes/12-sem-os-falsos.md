# 12. Funcionar sem os falsos

Até aqui, dois contêineres falsos faziam o papel de outros grupos no nosso ambiente:

| Falso | Faz o papel de |
|---|---|
| `usuarios-falso` | Grupo de Autenticação (login e token) |
| `pedidos-falso` | Grupo de Pedidos (cria pedidos e reage aos nossos eventos) |

O back-end já aceitava o token e os eventos reais. Mas três coisas só funcionavam com os falsos. Esta parte resolve as três (decisão D28).

## 1. Login real nas telas

### Antes

A tela de login mostrava uma lista de usuários de demonstração. Clicar num deles pedia um token pronto ao `usuarios-falso`. O Identity-Service real não tem essa rota, então, sem o falso, ninguém entrava.

### Agora

As telas usam o mesmo fluxo do Identity-Service:

```text
1. POST /api/v1/auth/login            e-mail + senha
   ← token SEM empresa, refresh_token e a lista de empresas e perfis da pessoa

2. POST /api/v1/auth/switch-context   empresa + perfil escolhidos
   ← token COM empresa (tenant_id) e perfil (active_scope)

3. POST /api/v1/auth/refresh          quando o token vence (15 min)
   ← token novo, sem pedir a senha de novo
```

- Quem tem uma só empresa e um só perfil entra direto. Quem tem mais vê uma lista e escolhe.
- O administrador da plataforma (`platform_role` `PLATFORM_ADMIN`) entra sem escolher empresa.
- Quando uma chamada recebe 401 porque o token venceu, a tela renova o token e repete a chamada. A pessoa não percebe.

O `usuarios-falso` passou a imitar essas rotas, **no mesmo formato** (conferido no código do Identity-Service). Por isso as telas não sabem se estão falando com o falso ou com o real. A senha dos usuários de demonstração é `demo`.

Quem decide para onde vai o login é o portal (Nginx), pela variável `AUTH_URL`:

| `AUTH_URL` | Login com |
|---|---|
| `http://usuarios-falso:8101` (padrão) | O falso, para desenvolver e demonstrar |
| `https://identity.matheus-alves.dev` | O Identity-Service real |

## 2. Transportadora real a partir do cadastro da Autenticação

### O problema

As transportadoras existiam só nos dados de exemplo (seeds), ligadas a empresas inventadas, como `emp-transp-rodovia`. Uma transportadora de verdade, cadastrada no Identity-Service, entra com um token cujo `tenant_id` é um UUID. A tela "Minha frota" procurava uma transportadora com essa empresa e não achava.

### A solução

Quando o Identity-Service cadastra uma empresa, ele publica o evento `empresa_cadastrada`, com a lista de escopos da empresa. Se a lista tem `CARRIER`, o nosso `transportadoras-service` cria uma transportadora:

| Campo | Valor |
|---|---|
| `id` e `empresa_id` | O `tenantId` da empresa, o mesmo que vem no token |
| `nome` | O `legalName` |
| `simulada` | `false`: ela cota digitando, como a Rodovia Sul |
| Tipos de carga | Os 4. O evento não diz o que ela transporta; na prática, ela só cota o que a frota dela comporta |

Depois disso, a pessoa da transportadora entra pelo login real, cadastra motoristas e caminhões em "Minha frota" e cota pela tela "Cargas disponíveis".

Empresa sem `CARRIER` (só compradora ou fornecedora) é ignorada. Evento sem os campos necessários vai para a DLT.

## 3. Botão de pedido de teste

O botão "Novo pedido de teste" chama o `pedidos-falso`. Agora ele só aparece se o `pedidos-falso` responde. Com o grupo de Pedidos real, o botão some.

O portal também sobe sem os falsos: antes, o Nginx não iniciava se um deles faltasse. Agora ele procura cada falso na hora da requisição; se não existir, aquela rota responde 502 e o resto funciona.

## 4. O que ainda depende de outros grupos

Está anotado nas [issues do nosso repositório](https://github.com/ArrozbR/portal-b2b-logistica-transporte/issues):

| Grupo | O que falta |
|---|---|
| Infraestrutura | Criar os 4 tópicos novos; rotas no gateway (`/api/v1/logistica`, `/api/v1/transportadoras`, `/api/v1/auth` e as telas); usar o nosso build |
| Banco de Dados | Aplicar as nossas migrações (001 a 006) no lugar das tabelas do kit |
| Autenticação | Dizer no `empresa_cadastrada` que cargas a transportadora leva; confirmar que o refresh mantém a empresa escolhida |

## 5. Onde está cada coisa

| Arquivo | O que tem |
|---|---|
| `frontend/assets/portal.js` | Tela de login, escolha da empresa e do perfil, renovação do token |
| `comum/comum/ferramentas/usuarios_falso.py` | Rotas `/api/v1/auth/*` no formato do Identity-Service |
| `services/transportadoras-service/transportadoras/empresas.py` | Regra pura: empresa → transportadora |
| `services/transportadoras-service/transportadoras/servico.py` | `registrar_empresa` (consome `empresa_cadastrada`) |
| `infra/portal/nginx.conf`, `infra/portal/Dockerfile` | `AUTH_URL`; falsos opcionais |
| `comum/tests/test_usuarios_falso.py`, `services/transportadoras-service/tests/test_empresas.py` | Testes unitários |
| `testes_integracao/test_empresa_cadastrada.py` | Evento no formato real do Identity-Service → transportadora → "Minha transportadora" com o token dela |
| ESP-TRP-001 1.2 | RF-14, RN-24, CA-43, CA-44 |

## 6. Perguntas que o professor pode fazer

**Por que o falso imita as rotas do serviço real, em vez de as telas terem dois modos?**
Assim existe um caminho só. O código que a gente testa todo dia com o falso é o mesmo que vai rodar com o serviço real. Se o falso tivesse rotas próprias, o login real nunca seria testado.

**Por que renovar o token sozinho?**
O token do Identity-Service vale 15 minutos. Sem renovação, a pessoa seria jogada para fora no meio do uso. O `refresh_token` troca o token vencido por um novo sem pedir a senha.

**Por que a transportadora é criada por evento, e não por uma tela nossa?**
O cadastro de empresas é da Autenticação. Se tivéssemos uma tela, a mesma empresa seria cadastrada em dois lugares, e os dois poderiam divergir. Pelo evento, a nossa cópia acompanha o cadastro deles, como manda o kit: dados de outro domínio chegam por evento.

**E se o mesmo evento chegar duas vezes?**
O consumidor ignora o `eventId` repetido. Se a empresa for publicada de novo, com outro `eventId`, a transportadora não é duplicada: só o nome é atualizado.
