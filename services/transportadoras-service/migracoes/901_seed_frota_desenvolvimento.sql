-- =============================================================================
-- transportadoras-service | frota de exemplo para desenvolvimento e demonstração
-- Dois motoristas e dois veículos por transportadora. Nomes, telefones, CNHs e
-- placas são FICTÍCIOS. NÃO aplicar no ambiente do kit.
-- =============================================================================

INSERT INTO transportadoras.motorista (id, transportadora_id, nome, telefone, cnh_numero, cnh_categoria, cnh_validade)
VALUES
    ('mot-exp-1', 'transp-expressa',   'Carlos Mendes',      '(65) 99988-7766', '03345678910', 'E', '2029-05-10'),
    ('mot-exp-2', 'transp-expressa',   'Ana Paula Ribeiro',  '(65) 99911-2233', '04456789021', 'E', '2028-09-22'),
    ('mot-eco-1', 'transp-economica',  'José Almeida',       '(11) 98877-6655', '05567890132', 'E', '2027-12-01'),
    ('mot-eco-2', 'transp-economica',  'Marcos Vieira',      '(11) 97766-5544', '06678901243', 'E', '2030-03-15'),
    ('mot-gra-1', 'transp-graneleira', 'Luciana Prado',      '(65) 99655-4433', '07789012354', 'E', '2029-01-30'),
    ('mot-gra-2', 'transp-graneleira', 'Roberto Nunes',      '(66) 99544-3322', '08890123465', 'E', '2028-06-18'),
    ('mot-fri-1', 'transp-frio',       'Fernanda Costa',     '(41) 99433-2211', '09901234576', 'E', '2029-08-08'),
    ('mot-fri-2', 'transp-frio',       'Paulo Henrique Dias','(41) 99322-1100', '10012345687', 'E', '2027-11-11'),
    ('mot-per-1', 'transp-perigosos',  'Ricardo Gomes',      '(31) 99211-0099', '11123456798', 'E', '2030-02-02'),
    ('mot-per-2', 'transp-perigosos',  'Sandra Lima',        '(31) 99100-9988', '12234567809', 'E', '2028-10-10');

INSERT INTO transportadoras.veiculo (id, transportadora_id, placa, tipo, capacidade_kg, tipos_carga, categoria_cnh_exigida)
VALUES
    ('vei-exp-1', 'transp-expressa',   'ABC1D23', 'CARRETA_GRANELEIRA', 32000, ARRAY['GRANEL'], 'E'),
    ('vei-exp-2', 'transp-expressa',   'BRA2E34', 'CARRETA_SIDER',      28000, ARRAY['CARGA_SECA', 'GRANEL'], 'E'),
    ('vei-eco-1', 'transp-economica',  'QWE3F45', 'CARRETA_GRANELEIRA', 30000, ARRAY['GRANEL'], 'E'),
    ('vei-eco-2', 'transp-economica',  'RTY4G56', 'TRUCK_BAU',          14000, ARRAY['CARGA_SECA'], 'C'),
    ('vei-gra-1', 'transp-graneleira', 'UIO5H67', 'BITREM_GRANELEIRO',  37000, ARRAY['GRANEL'], 'E'),
    ('vei-gra-2', 'transp-graneleira', 'PAS6J78', 'CARRETA_GRANELEIRA', 30000, ARRAY['GRANEL'], 'E'),
    ('vei-fri-1', 'transp-frio',       'DFG7K89', 'CARRETA_FRIGORIFICA',26000, ARRAY['REFRIGERADO'], 'E'),
    ('vei-fri-2', 'transp-frio',       'HJK8L90', 'TRUCK_FRIGORIFICO',  12000, ARRAY['REFRIGERADO'], 'C'),
    ('vei-per-1', 'transp-perigosos',  'ZXC9M01', 'CARRETA_TANQUE',     30000, ARRAY['PERIGOSO'], 'E'),
    ('vei-per-2', 'transp-perigosos',  'VBN0N12', 'TRUCK_TANQUE',       15000, ARRAY['PERIGOSO'], 'C');
