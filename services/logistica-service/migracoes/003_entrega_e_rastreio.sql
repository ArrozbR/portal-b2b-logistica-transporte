-- =============================================================================
-- logistica-service | 003: etapa 3 (entrega e rastreio)
-- =============================================================================

ALTER TABLE logistica.entrega
    ADD COLUMN transportadora_nome     VARCHAR(200),
    ADD COLUMN transportadora_telefone VARCHAR(30),
    ADD COLUMN motorista_nome          VARCHAR(200),
    ADD COLUMN motorista_telefone      VARCHAR(30),   -- dado pessoal: só para comprador/fornecedor da entrega
    ADD COLUMN motorista_cnh_mascarada VARCHAR(20),   -- a CNH completa fica só com a transportadora (LGPD)
    ADD COLUMN veiculo_placa           VARCHAR(8),
    ADD COLUMN veiculo_tipo            VARCHAR(30),
    ADD COLUMN rota                    JSONB,         -- [[lat, lon], ...]
    ADD COLUMN coleta_prevista         TIMESTAMPTZ,
    ADD COLUMN coletada_em             TIMESTAMPTZ,
    ADD COLUMN previsao_chegada        TIMESTAMPTZ,
    ADD COLUMN progresso               NUMERIC(5,4)  NOT NULL DEFAULT 0,
    ADD COLUMN posicao_lat             NUMERIC(9,6),
    ADD COLUMN posicao_lon             NUMERIC(9,6),
    ADD COLUMN posicao_em              TIMESTAMPTZ,
    ADD COLUMN ultima_sequencia        INT           NOT NULL DEFAULT 0,
    ADD COLUMN com_ocorrencia          BOOLEAN       NOT NULL DEFAULT FALSE,
    ADD COLUMN entregue_em             TIMESTAMPTZ,
    ADD COLUMN no_prazo                BOOLEAN,
    ADD COLUMN atraso_horas            NUMERIC(6,1);

-- Linha do tempo da entrega: um registro por rastreio_atualizado aplicado.
CREATE TABLE logistica.evento_rastreio (
    entrega_id   VARCHAR(64)  NOT NULL REFERENCES logistica.entrega (id),
    sequencia    INT          NOT NULL,
    tipo         VARCHAR(30)  NOT NULL,
    descricao    VARCHAR(300) NOT NULL,
    lat          NUMERIC(9,6),
    lon          NUMERIC(9,6),
    progresso    NUMERIC(5,4),
    ocorrido_em  TIMESTAMPTZ  NOT NULL,   -- hora do módulo
    event_id     VARCHAR(64)  NOT NULL UNIQUE,
    recebido_em  TIMESTAMPTZ  NOT NULL DEFAULT now(),
    PRIMARY KEY (entrega_id, sequencia)
);

CREATE INDEX entrega_pedido ON logistica.entrega (pedido_id, tentativa DESC);

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA logistica TO svc_logistica;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA logistica TO svc_logistica;
