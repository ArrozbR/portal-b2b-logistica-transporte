-- =============================================================================
-- transportadoras-service | 004: correlationId de até 128 caracteres
-- =============================================================================
-- Mesmo limite do grupo de Pedidos (ESP-PED-001): o correlationId do pedido
-- passa por todos os eventos do frete e é guardado aqui na solicitação e na viagem.

ALTER TABLE transportadoras.solicitacao_recebida ALTER COLUMN correlation_id TYPE VARCHAR(128);
ALTER TABLE transportadoras.viagem ALTER COLUMN correlation_id TYPE VARCHAR(128);

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA transportadoras TO svc_transportadoras;
