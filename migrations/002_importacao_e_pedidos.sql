-- Importação de planilha Excel e lista de espera. Não apaga nem altera dados existentes.
-- grupo = nome da turma/grupo, lote_id = qual importação criou a reserva, chave_import = identificação para não duplicar
ALTER TABLE reservas ADD COLUMN grupo TEXT NOT NULL DEFAULT '';
ALTER TABLE reservas ADD COLUMN lote_id INTEGER;
ALTER TABLE reservas ADD COLUMN chave_import TEXT;
CREATE INDEX IF NOT EXISTS idx_reservas_lote ON reservas (lote_id);
CREATE INDEX IF NOT EXISTS idx_reservas_chave ON reservas (chave_import);
-- Histórico de importações (cada importação é um lote que pode ser desfeito)
CREATE TABLE IF NOT EXISTS importacoes (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    arquivo TEXT NOT NULL DEFAULT '',
    criado  TEXT NOT NULL,
    usuario TEXT NOT NULL DEFAULT '',
    total   INTEGER NOT NULL DEFAULT 0,
    criadas INTEGER NOT NULL DEFAULT 0
);
-- Lista de espera (pedidos que ainda não viraram reserva)
CREATE TABLE IF NOT EXISTS pedidos (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    nome       TEXT NOT NULL,
    pessoas    INTEGER,
    entrada    TEXT,
    saida      TEXT,
    contato    TEXT NOT NULL DEFAULT '',
    observacao TEXT NOT NULL DEFAULT '',
    criado     TEXT NOT NULL,
    situacao   TEXT NOT NULL DEFAULT 'aberto' CHECK (situacao IN ('aberto','alocado','cancelado')),
    lote_id    INTEGER
);
CREATE INDEX IF NOT EXISTS idx_pedidos_lote ON pedidos (lote_id);
