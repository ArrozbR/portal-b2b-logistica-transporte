-- =============================================================================
-- logistica-service | 005: pedido que nasce sem comprador (D26, proposta)
-- =============================================================================
-- O pedido de leilão chega no pedido_criado sem comprador nem destino; o
-- fechamento chega depois, num pedido_atualizado. Os dois tópicos não têm
-- ordem garantida entre si, então cada parte é guardada na sua coluna e a
-- solicitação de frete só abre quando as duas se completam.

CREATE TABLE logistica.pedido_aguardando (
    pedido_id       VARCHAR(64)  PRIMARY KEY,
    pedido          JSONB,                  -- payload do pedido_criado (NULL até ele chegar)
    fechamento      JSONB,                  -- campos do pedido_atualizado de fechamento (NULL até ele chegar)
    correlation_id  VARCHAR(64),            -- o do pedido_criado, quando ele chega
    recebido_em     TIMESTAMPTZ  NOT NULL DEFAULT now(),
    atualizado_em   TIMESTAMPTZ  NOT NULL DEFAULT now()
);

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA logistica TO svc_logistica;
