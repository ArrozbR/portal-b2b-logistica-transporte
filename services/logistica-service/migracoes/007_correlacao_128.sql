-- =============================================================================
-- logistica-service | 007: correlationId de até 128 caracteres
-- =============================================================================
-- O grupo de Pedidos aceita correlationId de até 128 caracteres (ESP-PED-001,
-- schemas de pedido_criado e pedido_atualizado). Com 64, um pedido real com
-- correlationId maior ia para a DLT e o frete nunca abria.

ALTER TABLE logistica.solicitacao_frete ALTER COLUMN correlation_id TYPE VARCHAR(128);
ALTER TABLE logistica.pedido_aguardando ALTER COLUMN correlation_id TYPE VARCHAR(128);

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA logistica TO svc_logistica;
