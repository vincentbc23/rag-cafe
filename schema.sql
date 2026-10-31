-- Schema do banco de fornecedores (serviços e produtos) da cadeia do café
-- Tabela única: prestadores de serviço e vendedores de produtos rurais

DROP TABLE IF EXISTS fornecedores;

CREATE TABLE fornecedores (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Classificação
    tipo_cadastro       TEXT    NOT NULL CHECK (tipo_cadastro IN ('servico', 'produto')),
    categoria           TEXT    NOT NULL,              -- etapa da cadeia (ex.: 'Colheita', 'Insumos agrícolas')
    tipo                TEXT    NOT NULL,              -- tipo de serviço/produto (ex.: 'Engenheiro agrônomo')

    -- Identificação
    nome                TEXT    NOT NULL,              -- nome do prestador ou da empresa
    natureza            TEXT    NOT NULL CHECK (natureza IN ('pessoa_fisica', 'empresa')),

    -- Texto rico para o RAG (base dos embeddings)
    descricao           TEXT    NOT NULL,
    especialidades      TEXT,                          -- lista separada por vírgula

    -- Avaliação
    avaliacao           REAL    CHECK (avaliacao BETWEEN 0 AND 5),
    total_avaliacoes    INTEGER NOT NULL DEFAULT 0,

    -- Preço
    preco_medio         REAL    NOT NULL,              -- em R$
    unidade_preco       TEXT    NOT NULL,              -- ex.: 'hectare', 'diária', 'visita técnica', 'unidade'

    -- Localização / atendimento
    cidade_sede         TEXT    NOT NULL,
    uf                  TEXT    NOT NULL,
    regiao              TEXT    NOT NULL,              -- região cafeeira (ex.: 'Sul de Minas')
    abrangencia         TEXT    NOT NULL CHECK (abrangencia IN ('local', 'regional', 'nacional')),
    cidades_atendidas   TEXT,                          -- lista separada por vírgula (ou 'Todo o Brasil')
    raio_atendimento_km INTEGER,                       -- NULL quando abrangência é nacional

    -- Extras
    anos_experiencia    INTEGER,
    certificacoes       TEXT,                          -- registros/certificações (CREA, NR-31, Q-Grader...)
    disponibilidade     TEXT,
    telefone            TEXT,
    ativo               INTEGER NOT NULL DEFAULT 1,
    criado_em           TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_fornecedores_tipo      ON fornecedores (tipo);
CREATE INDEX idx_fornecedores_categoria ON fornecedores (categoria);
CREATE INDEX idx_fornecedores_regiao    ON fornecedores (regiao);
CREATE INDEX idx_fornecedores_uf_cidade ON fornecedores (uf, cidade_sede);
CREATE INDEX idx_fornecedores_avaliacao ON fornecedores (avaliacao);
