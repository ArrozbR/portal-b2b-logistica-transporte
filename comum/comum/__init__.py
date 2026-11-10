"""Código compartilhado pelos serviços de Logística e Transportadoras.

Cada módulo resolve uma regra transversal do kit de infraestrutura:

- logs:       logs em JSON com o X-Correlation-Id
- erros:      respostas de erro no padrão RFC 7807
- web:        middleware de correlação, métricas e rotas de saúde
- eventos:    envelope canônico dos eventos e validação por JSON Schema
- db:         pool de conexões com o PostgreSQL (no máximo 5)
- outbox:     gravação e publicação de eventos sem perder nenhum
- consumidor: consumo idempotente, com retentativas e DLT
- relogio:    relógio do módulo, que pode ser acelerado (D18)
- auth:       validação do JWT e controle de acesso por perfil
- geo:        cidades, distâncias e dias úteis
"""
