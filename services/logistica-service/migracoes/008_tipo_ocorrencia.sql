-- =============================================================================
-- logistica-service | 008: tipo da ocorrência
-- =============================================================================
-- A versão publicada do mockup do grupo de UX pede o tipo da ocorrência no
-- formulário (Atraso, Avaria na carga, Desvio de rota, Outro). As ocorrências
-- antigas, e as enviadas sem tipo, ficam como OUTRO.

ALTER TABLE logistica.ocorrencia
    ADD COLUMN tipo VARCHAR(20) NOT NULL DEFAULT 'OUTRO'
        CHECK (tipo IN ('ATRASO', 'AVARIA', 'DESVIO_ROTA', 'OUTRO'));

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA logistica TO svc_logistica;
