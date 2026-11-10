# 08. Token conforme o código do Identity-Service

Continua a [explicação 06](06-encaixe-com-outros-grupos.md). Em 10/11/2026, o grupo clonou o repositório do serviço de Autenticação ([Identity-Service](https://github.com/Matheus-Allvz/Identity-Service), em C#). Até então, o nosso token seguia o que eles tinham escrito numa issue. Lendo o código, apareceram três diferenças, uma delas grave.

## 1. O que mudou

| Ponto | Antes | Agora | Por quê |
|---|---|---|---|
| `iss` e `aud` | Não conferidos | Conferidos: `iss` = `identity-service` e `aud` = `b2b-platform` (configuráveis por `JWT_ISSUER` e `JWT_AUDIENCE`) | **Defeito grave:** o token deles traz `aud`, e o PyJWT recusa um token com `aud` quando o serviço não informa qual audiência espera. Todo token real seria recusado com 401 |
| Admin do módulo | Permissão `logistica:admin`, proposta nossa | `platform_role` `PLATFORM_ADMIN`, que o Identity-Service já tem (o usuário `platform-admin@agrobrasil.com.br` do seed deles). `logistica:admin` continua aceita | É a resposta oficial deles para "quem é o administrador da plataforma" |
| Token sem empresa ou sem escopo | 401 `TOKEN_INVALIDO` | 403 `CONTEXTO_NAO_SELECIONADO` | O token do login (`view_mode` NONE) não tem empresa: a pessoa ainda precisa escolher a empresa e o escopo (switch-context). Um 401 faria a tela deslogar |

O defeito não apareceu nos nossos testes porque os tokens de demonstração (`usuarios-falso`) não tinham `aud`. Agora eles têm os mesmos claims do Identity-Service, então o mesmo erro apareceria aqui.

## 2. Como é o token deles

O token é emitido em `src/IdentityService/Modules/M07Chaves/TokenIssuer.cs`. Ele vale 15 minutos e tem estes claims:

| Claim | Exemplo | Uso no módulo |
|---|---|---|
| `sub` | UUID do usuário | Quem fez a ação |
| `iss`, `aud` | `identity-service`, `b2b-platform` | Conferidos |
| `exp` | — | Validade |
| `platform_role` | `NONE`, `SUPPORT_AGENT` ou `PLATFORM_ADMIN` | `PLATFORM_ADMIN` = admin do módulo |
| `view_mode` | `NONE` (logo após o login), `SINGLE` (uma empresa) ou `MACRO_GROUP` (grupo econômico) | O módulo trabalha com uma empresa: só `SINGLE` serve, exceto para o admin |
| `tenant_id` | UUID da empresa | A empresa do usuário |
| `active_scope` | `BUYER`, `SUPPLIER`, `CARRIER` ou `TENANT_ADMIN` | Vira comprador, fornecedor ou transportadora |
| `permissions` | `produtos:criar` | Só lemos `logistica:admin` |

O fluxo real tem dois passos: `POST /api/v1/auth/login` devolve um token sem empresa (`view_mode` NONE), e `POST /api/v1/auth/switch-context` devolve o token da empresa e do escopo escolhidos. O nosso portal ainda usa o login de demonstração, que já entrega o token do segundo passo.

## 3. Onde está cada coisa

| Arquivo | O que mudou |
|---|---|
| `comum/comum/auth.py` | Confere `iss` e `aud`; admin pelo `platform_role`; 403 `CONTEXTO_NAO_SELECIONADO` |
| `comum/comum/ferramentas/usuarios_falso.py` | Emite os mesmos claims do Identity-Service; o admin tem `platform_role` `PLATFORM_ADMIN` |
| `comum/tests/test_auth.py` | 25 testes (9 novos): emissor e audiência, administrador da plataforma sem empresa, agente de suporte, token do login e de grupo |
| `docker-compose.yml`, `.env.example` | `JWT_ISSUER` e `JWT_AUDIENCE` |
| ESP-LOG-001 e ESP-TRP-001 (versão 1.1) | §7.1, catálogo de erros, CA-20 e Q-05 |

## 4. O que foi testado

| Verificação | Resultado |
|---|---|
| Token com `aud` na versão anterior | Recusado (`InvalidAudienceError`): confirmou o defeito |
| Testes unitários | 113 passando |
| Ambiente: login de demonstração | Token com `iss`, `aud`, `platform_role` e `view_mode`; o admin ajusta o relógio (200) |
| Testes de integração | Os 3 primeiros passaram; a rodada foi interrompida por falta de memória no computador, antes dos outros 3 |

## 5. Perguntas que o professor pode fazer

**Por que conferir `iss` e `aud`?**
`iss` diz quem emitiu o token, e `aud` diz para quem ele foi emitido. Sem conferir, um token emitido por outro sistema com a mesma chave, ou para outro sistema, seria aceito.

**Como vocês acharam o defeito?**
Lendo o código de quem emite o token, não só a descrição. A issue não falava de `aud`, mas o `TokenIssuer.cs` põe `aud` em todo token. Um teste com um token igual ao deles mostrou a recusa.

**Por que o administrador de uma empresa não é admin do módulo?**
O admin do módulo vê as entregas de todas as empresas e mexe no relógio. Isso é papel do administrador da plataforma, que o Identity-Service separa do administrador da empresa: `platform_role` × `TENANT_ADMIN`.

**Por que 403 e não 401 para o token sem empresa?**
O token é válido: a pessoa só não escolheu a empresa. 401 significa "não sei quem você é", e a tela mandaria para o login de novo. 403 diz o que falta fazer.
