-- =============================================================================
-- logistica-service | 002: etapa 2 (escolha pelo comprador, notificações,
-- cancelamento)
-- =============================================================================

-- Quem escolheu o frete (L15: o kit gravava sempre "system").
-- NULL = escolha automática por prazo vencido.
ALTER TABLE logistica.solicitacao_frete
    ADD COLUMN escolhida_por VARCHAR(64),
    ADD COLUMN escolhida_em  TIMESTAMPTZ;   -- hora do módulo

COMMENT ON COLUMN logistica.solicitacao_frete.rodada_ate IS
    'Fim da rodada automática, em HORA REAL (tempo técnico, não acelera com o relógio do módulo)';

-- Notificações no portal (D22). Endereçadas à empresa (comprador ou fornecedor).
CREATE TABLE logistica.notificacao (
    id              VARCHAR(64)  PRIMARY KEY,
    empresa_id      VARCHAR(64)  NOT NULL,
    papel           VARCHAR(20)  NOT NULL CHECK (papel IN ('comprador', 'fornecedor')),
    tipo            VARCHAR(40)  NOT NULL,
    titulo          VARCHAR(200) NOT NULL,
    mensagem        VARCHAR(1000) NOT NULL,
    pedido_id       VARCHAR(64),
    solicitacao_id  VARCHAR(64),
    lida            BOOLEAN      NOT NULL DEFAULT FALSE,
    criada_em       TIMESTAMPTZ  NOT NULL,      -- hora do módulo
    criado_em_real  TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX notificacao_caixa ON logistica.notificacao (empresa_id, papel, lida, criada_em DESC);

-- Cancelamentos recebidos antes do pedido_criado. Os dois eventos vêm de
-- tópicos diferentes, e o Kafka só garante ordem dentro de uma partição de
-- um mesmo tópico: o cancelamento pode chegar primeiro.
CREATE TABLE logistica.pedido_cancelado (
    pedido_id    VARCHAR(64) PRIMARY KEY,
    cancelado_em TIMESTAMPTZ NOT NULL DEFAULT now()
);

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA logistica TO svc_logistica;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA logistica TO svc_logistica;
