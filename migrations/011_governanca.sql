-- Governança: situação de arrumação de cada unidade (registrada pela equipe) e o log imutável de eventos.
-- A situação "derivada" (hospedada, saída, chegada...) NUNCA é gravada: vem das reservas a cada consulta.
-- O texto de obs/motivo fica só na tabela da unidade (140 caracteres); nenhum log guarda esse texto.
CREATE TABLE governanca_unidade (
    unidade           TEXT PRIMARY KEY CHECK (length(unidade) BETWEEN 3 AND 10),
    situacao          TEXT NOT NULL DEFAULT 'pronta' CHECK (situacao IN ('suja','em_arrumacao','pronta')),
    situacao_em       TEXT NOT NULL,
    situacao_por      INTEGER REFERENCES usuarios(id),
    pronto_em         TEXT,
    iniciada_em       TEXT,
    saida_confirmada  TEXT CHECK (saida_confirmada IS NULL OR length(saida_confirmada) = 10),
    manutencao        INTEGER NOT NULL DEFAULT 0 CHECK (manutencao IN (0,1)),
    manutencao_motivo TEXT NOT NULL DEFAULT '' CHECK (length(manutencao_motivo) <= 140),
    obs               TEXT NOT NULL DEFAULT '' CHECK (length(obs) <= 140),
    versao            INTEGER NOT NULL DEFAULT 1
);

-- As 25 unidades nascem PRONTAS, com "pronto em" = agora: sem isso, toda unidade com reserva passada apareceria suja de uma vez.
INSERT INTO governanca_unidade (unidade, situacao, situacao_em, pronto_em) SELECT column1, 'pronta', datetime('now','localtime'), datetime('now','localtime') FROM (
    VALUES
    ('101'),
    ('102'),
    ('103'),
    ('104'),
    ('201'),
    ('202'),
    ('203'),
    ('204'),
    ('205'),
    ('206'),
    ('207'),
    ('208'),
    ('301'),
    ('302'),
    ('303'),
    ('304'),
    ('305'),
    ('306'),
    ('307'),
    ('308'),
    ('Chalé A'),
    ('Chalé B'),
    ('Chalé C'),
    ('Chalé D'),
    ('Chalé E')
);

CREATE TABLE governanca_evento (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    em            TEXT NOT NULL,
    unidade       TEXT NOT NULL,
    usuario_id    INTEGER,
    usuario_login TEXT NOT NULL DEFAULT '',
    acao          TEXT NOT NULL CHECK (acao IN ('iniciar','pronta','suja','observacao','manutencao_abrir','manutencao_fechar')),
    de            TEXT,
    para          TEXT,
    lote          TEXT,
    ip            TEXT NOT NULL DEFAULT ''
);
CREATE INDEX idx_gov_evento_unidade ON governanca_evento (unidade, id);
CREATE INDEX idx_gov_evento_em ON governanca_evento (em);

CREATE TRIGGER governanca_evento_nao_altera BEFORE UPDATE ON governanca_evento
BEGIN
    SELECT RAISE(ABORT, 'O registro da governança não pode ser alterado');
END;

CREATE TRIGGER governanca_evento_nao_apaga BEFORE DELETE ON governanca_evento
BEGIN
    SELECT RAISE(ABORT, 'O registro da governança não pode ser apagado');
END;
