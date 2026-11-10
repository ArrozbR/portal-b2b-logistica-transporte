-- =============================================================================
-- transportadoras-service | 002: etapa 3 (motoristas, veículos e viagens)
-- =============================================================================

-- Motoristas (D19). Telefone e CNH são dados pessoais (LGPD): saem deste
-- serviço só para a entrega em andamento, com a CNH mascarada.
CREATE TABLE transportadoras.motorista (
    id                VARCHAR(64)  PRIMARY KEY,
    transportadora_id VARCHAR(64)  NOT NULL REFERENCES transportadoras.transportadora (id),
    nome              VARCHAR(200) NOT NULL,
    telefone          VARCHAR(30),
    cnh_numero        VARCHAR(20)  NOT NULL,
    cnh_categoria     CHAR(1)      NOT NULL CHECK (cnh_categoria IN ('A', 'B', 'C', 'D', 'E')),
    cnh_validade      DATE         NOT NULL,
    ativo             BOOLEAN      NOT NULL DEFAULT TRUE,
    viagem_atual_id   VARCHAR(64),             -- NULL = livre
    criado_em         TIMESTAMPTZ  NOT NULL DEFAULT now(),
    UNIQUE (transportadora_id, cnh_numero)
);

CREATE TABLE transportadoras.veiculo (
    id                     VARCHAR(64)   PRIMARY KEY,
    transportadora_id      VARCHAR(64)   NOT NULL REFERENCES transportadoras.transportadora (id),
    placa                  VARCHAR(8)    NOT NULL UNIQUE,
    tipo                   VARCHAR(30)   NOT NULL,
    capacidade_kg          NUMERIC(12,2) NOT NULL CHECK (capacidade_kg > 0),
    tipos_carga            VARCHAR(20)[] NOT NULL,
    categoria_cnh_exigida  CHAR(1)       NOT NULL DEFAULT 'E' CHECK (categoria_cnh_exigida IN ('B', 'C', 'D', 'E')),
    ativo                  BOOLEAN       NOT NULL DEFAULT TRUE,
    viagem_atual_id        VARCHAR(64),            -- NULL = livre
    criado_em              TIMESTAMPTZ   NOT NULL DEFAULT now()
);

CREATE INDEX motorista_livre ON transportadoras.motorista (transportadora_id) WHERE ativo AND viagem_atual_id IS NULL;
CREATE INDEX veiculo_livre   ON transportadoras.veiculo (transportadora_id)   WHERE ativo AND viagem_atual_id IS NULL;

-- Viagem simulada (D8). Uma por entrega.
CREATE TABLE transportadoras.viagem (
    id                  VARCHAR(64)   PRIMARY KEY,
    entrega_id          VARCHAR(64)   NOT NULL UNIQUE,
    pedido_id           VARCHAR(64)   NOT NULL,
    solicitacao_id      VARCHAR(64)   NOT NULL REFERENCES transportadoras.solicitacao_recebida (id),
    transportadora_id   VARCHAR(64)   NOT NULL REFERENCES transportadoras.transportadora (id),
    motorista_id        VARCHAR(64)   NOT NULL REFERENCES transportadoras.motorista (id),
    veiculo_id          VARCHAR(64)   NOT NULL REFERENCES transportadoras.veiculo (id),
    rota                JSONB         NOT NULL,          -- [[lat, lon], ...]
    data_prometida      DATE,
    coleta_em           TIMESTAMPTZ   NOT NULL,          -- hora do módulo
    chegada_prevista    TIMESTAMPTZ   NOT NULL,          -- hora do módulo; muda se houver atraso
    atraso_horas        NUMERIC(6,1)  NOT NULL DEFAULT 0, -- sorteado no início
    atraso_revelado     BOOLEAN       NOT NULL DEFAULT FALSE,
    parada_publicada    BOOLEAN       NOT NULL DEFAULT FALSE,
    marco_tempo         TIMESTAMPTZ   NOT NULL,          -- ponto de partida do cálculo do progresso
    marco_progresso     NUMERIC(5,4)  NOT NULL DEFAULT 0,
    progresso           NUMERIC(5,4)  NOT NULL DEFAULT 0,
    sequencia           INT           NOT NULL DEFAULT 0, -- último número de rastreio_atualizado
    status              VARCHAR(20)   NOT NULL CHECK (status IN ('AGENDADA', 'EM_TRANSITO', 'ENTREGUE', 'CANCELADA')),
    proximo_passo_em    TIMESTAMPTZ   NOT NULL,          -- HORA REAL do próximo passo (a cada 30 s)
    entregue_em         TIMESTAMPTZ,
    no_prazo            BOOLEAN,
    correlation_id      VARCHAR(64),
    criado_em           TIMESTAMPTZ   NOT NULL DEFAULT now()
);
CREATE INDEX viagem_proximo_passo ON transportadoras.viagem (proximo_passo_em)
    WHERE status IN ('AGENDADA', 'EM_TRANSITO');

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA transportadoras TO svc_transportadoras;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA transportadoras TO svc_transportadoras;
