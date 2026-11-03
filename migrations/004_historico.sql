-- Histórico de auditoria: quem fez o quê e quando. Só se acrescenta; nunca se altera nem se apaga.
-- antes/depois guardam só a diferença dos campos a, i, f, n, p (JSON). Nunca extras, observações, senhas ou tokens.
CREATE TABLE historico (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    em            TEXT NOT NULL,
    usuario_id    INTEGER,
    usuario_login TEXT NOT NULL DEFAULT '',
    acao          TEXT NOT NULL,
    entidade      TEXT NOT NULL,
    entidade_id   INTEGER,
    antes         TEXT,
    depois        TEXT,
    ip            TEXT NOT NULL DEFAULT ''
);
CREATE INDEX idx_historico_entidade ON historico (entidade, entidade_id, id);
CREATE INDEX idx_historico_em ON historico (em);

CREATE TRIGGER historico_nao_altera BEFORE UPDATE ON historico
BEGIN
    SELECT RAISE(ABORT, 'O histórico não pode ser alterado');
END;

CREATE TRIGGER historico_nao_apaga BEFORE DELETE ON historico
BEGIN
    SELECT RAISE(ABORT, 'O histórico não pode ser apagado');
END;
