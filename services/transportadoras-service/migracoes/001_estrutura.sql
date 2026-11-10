-- =============================================================================
-- transportadoras-service | 001: estrutura da etapa 1
-- Executado pelo usuário portal_ddl. O serviço conecta como svc_transportadoras.
-- GRANTs depois do CREATE TABLE (correção do K1 do kit).
-- Motoristas, veículos e viagens entram na etapa 3.
-- =============================================================================

CREATE TABLE transportadoras.transportadora (
    id               VARCHAR(64)   PRIMARY KEY,
    empresa_id       VARCHAR(64)   NOT NULL,
    nome             VARCHAR(200)  NOT NULL,
    telefone_contato VARCHAR(30),
    ativa            BOOLEAN       NOT NULL DEFAULT TRUE,
    -- simulada = TRUE: o sistema cota sozinho por ela (D3).
    -- simulada = FALSE: transportadora real, que cota digitando na tela.
    simulada         BOOLEAN       NOT NULL DEFAULT TRUE,
    tipos_carga      VARCHAR(20)[] NOT NULL,
    ufs_atendidas    CHAR(2)[],    -- NULL = atende todo o país
    prob_atraso      NUMERIC(4,3)  NOT NULL DEFAULT 0.100 CHECK (prob_atraso BETWEEN 0 AND 1),
    criado_em        TIMESTAMPTZ   NOT NULL DEFAULT now()
);

-- Parâmetros do motor de cotação (arquitetura, seção 5.4). No kit esta tabela
-- só tinha preco_base e prazo_dias fixos.
CREATE TABLE transportadoras.regra_cotacao (
    transportadora_id VARCHAR(64)   PRIMARY KEY REFERENCES transportadoras.transportadora (id),
    preco_minimo      NUMERIC(12,2) NOT NULL CHECK (preco_minimo >= 0),
    tarifa_km         NUMERIC(10,4) NOT NULL CHECK (tarifa_km >= 0),
    tarifa_ton        NUMERIC(10,4) NOT NULL CHECK (tarifa_ton >= 0),
    fator_tipo_carga  JSONB         NOT NULL DEFAULT '{}'::jsonb,
    km_por_dia        INT           NOT NULL CHECK (km_por_dia > 0),
    prazo_base_dias   INT           NOT NULL CHECK (prazo_base_dias >= 0)
);

-- Cópia local de solicitacao_frete_criada (para cotar e, na etapa 4, para a
-- tela "Solicitações de frete").
CREATE TABLE transportadoras.solicitacao_recebida (
    id                   VARCHAR(64)   PRIMARY KEY,
    pedido_id            VARCHAR(64)   NOT NULL,
    produto_nome         VARCHAR(200),
    tipo_carga           VARCHAR(20)   NOT NULL,
    peso_kg              NUMERIC(12,2) NOT NULL,
    origem_cidade        VARCHAR(100)  NOT NULL,
    origem_uf            CHAR(2)       NOT NULL,
    origem_lat           NUMERIC(9,6)  NOT NULL,
    origem_lon           NUMERIC(9,6)  NOT NULL,
    destino_cidade       VARCHAR(100)  NOT NULL,
    destino_uf           CHAR(2)       NOT NULL,
    destino_lat          NUMERIC(9,6)  NOT NULL,
    destino_lon          NUMERIC(9,6)  NOT NULL,
    distancia_km         NUMERIC(8,1)  NOT NULL,
    data_coleta_prevista DATE          NOT NULL,
    prazo_decisao_em     TIMESTAMPTZ   NOT NULL,
    recebida_em          TIMESTAMPTZ   NOT NULL DEFAULT now()
);

-- Cotações que as transportadoras deste serviço emitiram.
CREATE TABLE transportadoras.cotacao_emitida (
    id                    VARCHAR(64)   PRIMARY KEY,
    solicitacao_id        VARCHAR(64)   NOT NULL REFERENCES transportadoras.solicitacao_recebida (id),
    transportadora_id     VARCHAR(64)   NOT NULL REFERENCES transportadoras.transportadora (id),
    preco                 NUMERIC(12,2) NOT NULL,
    prazo_dias            INT           NOT NULL,
    data_entrega_prevista DATE          NOT NULL,
    valida_ate            TIMESTAMPTZ   NOT NULL,
    origem_cotacao        VARCHAR(10)   NOT NULL CHECK (origem_cotacao IN ('SIMULADA', 'DIGITADA')),
    observacoes           VARCHAR(500),
    emitida_em            TIMESTAMPTZ   NOT NULL,  -- hora do módulo
    UNIQUE (solicitacao_id, transportadora_id)
);

CREATE TABLE transportadoras.relogio (
    id           SMALLINT      PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    base_real    TIMESTAMPTZ   NOT NULL,
    base_virtual TIMESTAMPTZ   NOT NULL,
    fator        NUMERIC(10,2) NOT NULL CHECK (fator > 0),
    versao       INT           NOT NULL
);

CREATE TABLE transportadoras.outbox (
    seq          BIGSERIAL    PRIMARY KEY,
    event_id     VARCHAR(64)  NOT NULL UNIQUE,
    topico       VARCHAR(100) NOT NULL,
    chave        VARCHAR(100) NOT NULL,
    envelope     JSONB        NOT NULL,
    criado_em    TIMESTAMPTZ  NOT NULL DEFAULT now(),
    publicado_em TIMESTAMPTZ
);
CREATE INDEX outbox_pendentes ON transportadoras.outbox (seq) WHERE publicado_em IS NULL;

CREATE TABLE transportadoras.processed_events (
    event_id     VARCHAR(64)  PRIMARY KEY,
    topico       VARCHAR(100),
    processed_at TIMESTAMPTZ  NOT NULL DEFAULT now()
);

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA transportadoras TO svc_transportadoras;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA transportadoras TO svc_transportadoras;
ALTER DEFAULT PRIVILEGES FOR ROLE portal_ddl IN SCHEMA transportadoras
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO svc_transportadoras;
ALTER DEFAULT PRIVILEGES FOR ROLE portal_ddl IN SCHEMA transportadoras
    GRANT USAGE, SELECT ON SEQUENCES TO svc_transportadoras;
