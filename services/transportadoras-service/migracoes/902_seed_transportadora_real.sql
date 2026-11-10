-- =============================================================================
-- transportadoras-service | transportadora REAL de demonstração (D3)
-- Não é simulada: só cota quando alguém da empresa digita a cotação na tela
-- "Solicitações de frete". Dados fictícios. NÃO aplicar no ambiente do kit.
-- =============================================================================

INSERT INTO transportadoras.transportadora
    (id, empresa_id, nome, telefone_contato, simulada, tipos_carga, ufs_atendidas, prob_atraso)
VALUES
    ('transp-rodovia', 'emp-transp-rodovia', 'Rodovia Sul Transportes', '(41) 4000-1006', FALSE,
     ARRAY['GRANEL', 'CARGA_SECA'], NULL, 0.200);

-- A regra de cotação não é usada para cotar (a cotação é digitada); o km por
-- dia define a duração mínima da viagem simulada.
INSERT INTO transportadoras.regra_cotacao
    (transportadora_id, preco_minimo, tarifa_km, tarifa_ton, fator_tipo_carga, km_por_dia, prazo_base_dias)
VALUES
    ('transp-rodovia', 1000.00, 3.20, 40.00, '{}', 600, 1);

INSERT INTO transportadoras.motorista (id, transportadora_id, nome, telefone, cnh_numero, cnh_categoria, cnh_validade)
VALUES
    ('mot-rod-1', 'transp-rodovia', 'Eduardo Pereira', '(41) 99877-1122', '13345678901', 'E', '2029-04-20'),
    ('mot-rod-2', 'transp-rodovia', 'Juliana Martins', '(41) 99766-2233', '14456789012', 'E', '2028-12-05');

INSERT INTO transportadoras.veiculo (id, transportadora_id, placa, tipo, capacidade_kg, tipos_carga, categoria_cnh_exigida)
VALUES
    ('vei-rod-1', 'transp-rodovia', 'RSL1A23', 'CARRETA_GRANELEIRA', 30000, ARRAY['GRANEL'], 'E'),
    ('vei-rod-2', 'transp-rodovia', 'RSL2B34', 'CARRETA_SIDER',      28000, ARRAY['CARGA_SECA', 'GRANEL'], 'E');
