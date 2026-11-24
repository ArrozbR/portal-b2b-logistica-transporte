-- =============================================================================
-- transportadoras-service | 005: data de entrega desejada pelo comprador
-- =============================================================================
-- A versão publicada do mockup do grupo de UX mostra à transportadora o prazo de
-- entrega da carga. Ele chega no solicitacao_frete_criada (dataEntregaDesejada,
-- opcional); as solicitações antigas ficam sem ele.

ALTER TABLE transportadoras.solicitacao_recebida ADD COLUMN data_entrega_desejada DATE;

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA transportadoras TO svc_transportadoras;
