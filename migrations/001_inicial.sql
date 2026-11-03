-- Tabela principal de reservas.
-- a=apartamento, n=numero de pessoas, i=entrada, f=saida, p=pagamento, o=observacoes
CREATE TABLE IF NOT EXISTS reservas (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    a        TEXT NOT NULL,
    nome     TEXT NOT NULL,
    extras   TEXT NOT NULL DEFAULT '',
    n        INTEGER NOT NULL DEFAULT 1,
    i        TEXT NOT NULL,
    f        TEXT NOT NULL,
    p        TEXT NOT NULL DEFAULT 'pendente',
    o        TEXT NOT NULL DEFAULT '',
    criado   TEXT NOT NULL,
    alterado TEXT NOT NULL,
    versao   INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_reservas_apto_datas ON reservas (a, i, f);
