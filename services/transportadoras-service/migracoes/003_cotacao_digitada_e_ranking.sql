-- =============================================================================
-- transportadoras-service | 003: etapa 4 (cotação digitada e ranking)
-- =============================================================================

-- Situação da solicitação vista pelas transportadoras: deixa de aceitar
-- cotação quando o frete é escolhido (frete_selecionado) ou o pedido é cancelado.
ALTER TABLE transportadoras.solicitacao_recebida
    ADD COLUMN status                      VARCHAR(12) NOT NULL DEFAULT 'ABERTA'
                                           CHECK (status IN ('ABERTA', 'ENCERRADA')),
    ADD COLUMN transportadora_vencedora_id VARCHAR(64),
    ADD COLUMN cancelada                   BOOLEAN     NOT NULL DEFAULT FALSE,
    ADD COLUMN correlation_id              VARCHAR(64);

-- Quem digitou a cotação (cotação manual de uma transportadora real).
ALTER TABLE transportadoras.cotacao_emitida
    ADD COLUMN usuario_id VARCHAR(64);

-- Atraso real da entrega, para o ranking (atraso médio).
ALTER TABLE transportadoras.viagem
    ADD COLUMN atraso_real_horas NUMERIC(6,1);

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA transportadoras TO svc_transportadoras;
