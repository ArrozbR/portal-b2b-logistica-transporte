-- =============================================================================
-- logistica-service | 001: estrutura da etapa 1
-- Executado pelo usuário portal_ddl (dono do schema). O serviço conecta como
-- svc_logistica, que só tem SELECT/INSERT/UPDATE/DELETE neste schema.
--
-- Diferente do kit: os GRANTs ficam DEPOIS do CREATE TABLE (correção do K1;
-- no kit, o GRANT vinha antes e o serviço recebia "permission denied").
-- No ambiente do kit, as tabelas solicitacao_frete e cotacao já existem com
-- menos colunas; o grupo de Banco de Dados precisa substituí-las por estas.
-- =============================================================================

CREATE TABLE logistica.solicitacao_frete (
    id                    VARCHAR(64)   PRIMARY KEY,
    pedido_id             VARCHAR(64)   NOT NULL UNIQUE,
    produto_id            VARCHAR(64)   NOT NULL,
    produto_nome          VARCHAR(200)  NOT NULL,
    valor_carga           NUMERIC(14,2) NOT NULL CHECK (valor_carga >= 0),
    comprador_id          VARCHAR(64)   NOT NULL,
    fornecedor_id         VARCHAR(64)   NOT NULL,
    tipo_carga            VARCHAR(20)   NOT NULL
                          CHECK (tipo_carga IN ('GRANEL', 'REFRIGERADO', 'CARGA_SECA', 'PERIGOSO')),
    peso_kg               NUMERIC(12,2) NOT NULL CHECK (peso_kg > 0),
    origem_cidade         VARCHAR(100)  NOT NULL,
    origem_uf             CHAR(2)       NOT NULL,
    origem_lat            NUMERIC(9,6)  NOT NULL,
    origem_lon            NUMERIC(9,6)  NOT NULL,
    destino_cidade        VARCHAR(100)  NOT NULL,
    destino_uf            CHAR(2)       NOT NULL,
    destino_lat           NUMERIC(9,6)  NOT NULL,
    destino_lon           NUMERIC(9,6)  NOT NULL,
    distancia_km          NUMERIC(8,1)  NOT NULL,
    data_coleta_prevista  DATE          NOT NULL,
    data_entrega_desejada DATE,
    aberta_em             TIMESTAMPTZ   NOT NULL,  -- hora do módulo (D18)
    rodada_ate            TIMESTAMPTZ   NOT NULL,  -- fim da rodada automática (10 s)
    prazo_decisao_em      TIMESTAMPTZ   NOT NULL,  -- fim do prazo de decisão (12 h)
    cotacao_escolhida_id  VARCHAR(64),
    criterio              VARCHAR(30)
                          CHECK (criterio IN ('ESCOLHA_COMPRADOR', 'AUTOMATICO_MENOR_PRECO')),
    status                VARCHAR(20)   NOT NULL
                          CHECK (status IN ('ABERTA', 'COTADA', 'SEM_COTACAO', 'SELECIONADA',
                                            'INDISPONIVEL', 'CANCELADA')),
    correlation_id        VARCHAR(64),
    criado_em             TIMESTAMPTZ   NOT NULL DEFAULT now(),
    atualizado_em         TIMESTAMPTZ   NOT NULL DEFAULT now()
);

CREATE INDEX solicitacao_frete_prazos    ON logistica.solicitacao_frete (status, prazo_decisao_em);
CREATE INDEX solicitacao_frete_rodada    ON logistica.solicitacao_frete (status, rodada_ate);
CREATE INDEX solicitacao_frete_comprador ON logistica.solicitacao_frete (comprador_id);
CREATE INDEX solicitacao_frete_fornecedor ON logistica.solicitacao_frete (fornecedor_id);

CREATE TABLE logistica.cotacao (
    id                    VARCHAR(64)   PRIMARY KEY,
    solicitacao_id        VARCHAR(64)   NOT NULL REFERENCES logistica.solicitacao_frete (id),
    transportadora_id     VARCHAR(64)   NOT NULL,
    transportadora_nome   VARCHAR(200),
    preco                 NUMERIC(12,2) NOT NULL CHECK (preco > 0),
    prazo_dias            INT           NOT NULL CHECK (prazo_dias > 0),
    data_entrega_prevista DATE,
    valida_ate            TIMESTAMPTZ,
    origem_cotacao        VARCHAR(10)   NOT NULL DEFAULT 'SIMULADA'
                          CHECK (origem_cotacao IN ('SIMULADA', 'DIGITADA')),
    observacoes           VARCHAR(500),
    status                VARCHAR(20)   NOT NULL
                          CHECK (status IN ('VALIDA', 'RECUSADA_TARDE', 'VIAGEM_RECUSADA')),
    recebida_em           TIMESTAMPTZ   NOT NULL,  -- hora do módulo
    criado_em             TIMESTAMPTZ   NOT NULL DEFAULT now(),
    UNIQUE (solicitacao_id, transportadora_id)
);

ALTER TABLE logistica.solicitacao_frete
    ADD CONSTRAINT solicitacao_frete_cotacao_escolhida
    FOREIGN KEY (cotacao_escolhida_id) REFERENCES logistica.cotacao (id);

-- Na etapa 1 a entrega só existe para dar o entregaId ao frete_selecionado.
-- Motorista, posição e linha do tempo entram na etapa 3.
CREATE TABLE logistica.entrega (
    id                VARCHAR(64) PRIMARY KEY,
    pedido_id         VARCHAR(64) NOT NULL,
    tentativa         INT         NOT NULL CHECK (tentativa >= 1),
    solicitacao_id    VARCHAR(64) NOT NULL REFERENCES logistica.solicitacao_frete (id),
    cotacao_id        VARCHAR(64) NOT NULL REFERENCES logistica.cotacao (id),
    transportadora_id VARCHAR(64) NOT NULL,
    status            VARCHAR(24) NOT NULL
                      CHECK (status IN ('AGUARDANDO_ALOCACAO', 'AGUARDANDO_COLETA', 'EM_TRANSITO',
                                        'ENTREGUE', 'RECUSADA', 'CANCELADA')),
    prazo_prometido   DATE,
    criado_em         TIMESTAMPTZ NOT NULL DEFAULT now(),
    atualizado_em     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (pedido_id, tentativa)
);

-- Cópia local da pontualidade das transportadoras (arquitetura, seção 9.3).
CREATE TABLE logistica.desempenho_transportadora (
    transportadora_id  VARCHAR(64)   PRIMARY KEY,
    nome               VARCHAR(200),
    entregas           INT           NOT NULL DEFAULT 0,
    entregas_no_prazo  INT           NOT NULL DEFAULT 0,
    atraso_total_horas NUMERIC(12,2) NOT NULL DEFAULT 0,
    atualizado_em      TIMESTAMPTZ   NOT NULL DEFAULT now()
);

-- Relógio do módulo (D18). Linha única; sem linha = hora real.
CREATE TABLE logistica.relogio (
    id           SMALLINT      PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    base_real    TIMESTAMPTZ   NOT NULL,
    base_virtual TIMESTAMPTZ   NOT NULL,
    fator        NUMERIC(10,2) NOT NULL CHECK (fator > 0),
    versao       INT           NOT NULL
);

-- Outbox transacional (D13).
CREATE TABLE logistica.outbox (
    seq          BIGSERIAL    PRIMARY KEY,
    event_id     VARCHAR(64)  NOT NULL UNIQUE,
    topico       VARCHAR(100) NOT NULL,
    chave        VARCHAR(100) NOT NULL,
    envelope     JSONB        NOT NULL,
    criado_em    TIMESTAMPTZ  NOT NULL DEFAULT now(),
    publicado_em TIMESTAMPTZ
);
CREATE INDEX outbox_pendentes ON logistica.outbox (seq) WHERE publicado_em IS NULL;

-- Eventos já consumidos (idempotência).
CREATE TABLE logistica.processed_events (
    event_id     VARCHAR(64)  PRIMARY KEY,
    topico       VARCHAR(100),
    processed_at TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- Respostas guardadas por Idempotency-Key (rotas POST, a partir da etapa 2).
CREATE TABLE logistica.idempotency_keys (
    key              VARCHAR(128) PRIMARY KEY,
    response_payload JSONB        NOT NULL,
    criado_em        TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- Permissões do serviço: só DML, só neste schema.
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA logistica TO svc_logistica;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA logistica TO svc_logistica;
ALTER DEFAULT PRIVILEGES FOR ROLE portal_ddl IN SCHEMA logistica
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO svc_logistica;
ALTER DEFAULT PRIVILEGES FOR ROLE portal_ddl IN SCHEMA logistica
    GRANT USAGE, SELECT ON SEQUENCES TO svc_logistica;
