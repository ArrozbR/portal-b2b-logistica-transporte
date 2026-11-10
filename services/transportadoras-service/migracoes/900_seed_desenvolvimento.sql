-- =============================================================================
-- transportadoras-service | dados de exemplo para desenvolvimento e demonstração
-- Cinco transportadoras simuladas com perfis diferentes (arquitetura, seção 5.4).
-- Os nomes são fictícios. NÃO aplicar no ambiente do kit sem combinar com o
-- grupo de Banco de Dados.
-- =============================================================================

INSERT INTO transportadoras.transportadora
    (id, empresa_id, nome, telefone_contato, simulada, tipos_carga, ufs_atendidas, prob_atraso)
VALUES
    ('transp-expressa',   'emp-transp-expressa',   'Expressa Cargas Rápidas', '(11) 4000-1001', TRUE,
        ARRAY['CARGA_SECA', 'GRANEL'], NULL, 0.050),
    ('transp-economica',  'emp-transp-economica',  'Econômica Transportes',   '(11) 4000-1002', TRUE,
        ARRAY['CARGA_SECA', 'GRANEL'], NULL, 0.350),
    ('transp-graneleira', 'emp-transp-graneleira', 'Graneleira Centro-Oeste', '(65) 4000-1003', TRUE,
        ARRAY['GRANEL'], ARRAY['MT', 'GO', 'MS', 'SP', 'PR'], 0.150),
    ('transp-frio',       'emp-transp-frio',       'Frio Sul Refrigerados',   '(41) 4000-1004', TRUE,
        ARRAY['REFRIGERADO'], NULL, 0.100),
    ('transp-perigosos',  'emp-transp-perigosos',  'Segura Cargas Especiais', '(31) 4000-1005', TRUE,
        ARRAY['PERIGOSO'], NULL, 0.100);

-- fator_tipo_carga: multiplica o preço conforme a dificuldade da carga.
INSERT INTO transportadoras.regra_cotacao
    (transportadora_id, preco_minimo, tarifa_km, tarifa_ton, fator_tipo_carga, km_por_dia, prazo_base_dias)
VALUES
    ('transp-expressa',   1500.00, 3.80, 45.00, '{"GRANEL": 1.00, "CARGA_SECA": 1.10}', 750, 1),
    ('transp-economica',   900.00, 2.60, 30.00, '{"GRANEL": 1.00, "CARGA_SECA": 1.10}', 400, 2),
    ('transp-graneleira', 1100.00, 3.00, 35.00, '{"GRANEL": 1.00}',                     550, 1),
    ('transp-frio',       2000.00, 4.50, 60.00, '{"REFRIGERADO": 1.35}',                600, 1),
    ('transp-perigosos',  2500.00, 5.20, 80.00, '{"PERIGOSO": 1.60}',                   500, 2);
