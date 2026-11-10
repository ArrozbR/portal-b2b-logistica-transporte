-- =============================================================================
-- logistica-service | 004: etapa 4 (ocorrências reportadas pelo comprador ou fornecedor)
-- =============================================================================

CREATE TABLE logistica.ocorrencia (
    id           VARCHAR(64)  PRIMARY KEY,
    entrega_id   VARCHAR(64)  NOT NULL REFERENCES logistica.entrega (id),
    pedido_id    VARCHAR(64)  NOT NULL,
    autor_id     VARCHAR(64)  NOT NULL,
    autor_papel  VARCHAR(20)  NOT NULL CHECK (autor_papel IN ('comprador', 'fornecedor')),
    descricao    VARCHAR(500) NOT NULL,
    ocorrida_em  TIMESTAMPTZ  NOT NULL,   -- hora do módulo
    criado_em    TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX ocorrencia_entrega ON logistica.ocorrencia (entrega_id, ocorrida_em);

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA logistica TO svc_logistica;
