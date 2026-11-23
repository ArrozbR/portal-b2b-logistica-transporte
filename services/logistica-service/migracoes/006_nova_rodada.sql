-- =============================================================================
-- logistica-service | 006: nova rodada de cotação depois do frete indisponível (D27)
-- =============================================================================
-- O grupo de Pedidos não cancela o pedido quando o frete fica indisponível: a
-- venda já foi concluída e o estoque já teve baixa (ESP-PED-001, RN-22 e D-05).
-- A logística abre uma nova solicitação para o mesmo pedido. Cada solicitação
-- é uma "rodada" (1, 2, 3...), e a contagem de tentativas da entrega recomeça
-- em 1 em cada rodada.

ALTER TABLE logistica.solicitacao_frete
    ADD COLUMN rodada INT NOT NULL DEFAULT 1 CHECK (rodada >= 1);

-- Antes: uma solicitação por pedido. Agora: uma por (pedido, rodada).
ALTER TABLE logistica.solicitacao_frete DROP CONSTRAINT solicitacao_frete_pedido_id_key;
ALTER TABLE logistica.solicitacao_frete
    ADD CONSTRAINT solicitacao_frete_pedido_rodada_key UNIQUE (pedido_id, rodada);

-- Antes: tentativa única por pedido. Agora: por solicitação (a tentativa recomeça em 1).
ALTER TABLE logistica.entrega DROP CONSTRAINT entrega_pedido_id_tentativa_key;
ALTER TABLE logistica.entrega
    ADD CONSTRAINT entrega_solicitacao_tentativa_key UNIQUE (solicitacao_id, tentativa);

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA logistica TO svc_logistica;
