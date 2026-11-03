-- Cancelamento lógico (a reserva deixa de ocupar a unidade, mas continua guardada) e restrições CHECK.
-- O SQLite não permite acrescentar CHECK a uma tabela pronta; por isso a tabela é recriada,
-- COPIANDO todas as reservas (mesmos ids, versões e datas). Se algum dado antigo violar uma
-- restrição, a migração inteira é desfeita e nada muda (e há backup feito antes).
CREATE TABLE reservas_nova (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    a        TEXT NOT NULL,
    nome     TEXT NOT NULL,
    extras   TEXT NOT NULL DEFAULT '',
    n        INTEGER NOT NULL DEFAULT 1 CHECK (n BETWEEN 1 AND 50),
    i        TEXT NOT NULL CHECK (i GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
    f        TEXT NOT NULL CHECK (f GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
    p        TEXT NOT NULL DEFAULT 'pendente' CHECK (p IN ('pago','parcial','pousada','gratis','pendente')),
    o        TEXT NOT NULL DEFAULT '',
    criado   TEXT NOT NULL,
    alterado TEXT NOT NULL,
    versao   INTEGER NOT NULL DEFAULT 1,
    grupo    TEXT NOT NULL DEFAULT '',
    lote_id  INTEGER,
    chave_import TEXT,
    status   TEXT NOT NULL DEFAULT 'ativa' CHECK (status IN ('ativa','cancelada')),
    motivo_cancelamento TEXT,
    cancelado_por TEXT,
    cancelado_em  TEXT,
    CHECK (f > i)
);

INSERT INTO reservas_nova (id, a, nome, extras, n, i, f, p, o, criado, alterado, versao, grupo, lote_id, chave_import)
SELECT id, a, nome, extras, n, i, f, p, o, criado, alterado, versao, grupo, lote_id, chave_import FROM reservas;

-- mantém o contador de ids (para nunca reaproveitar o número de uma reserva já apagada)
UPDATE sqlite_sequence
   SET seq = (SELECT seq FROM sqlite_sequence WHERE name = 'reservas')
 WHERE name = 'reservas_nova'
   AND seq < (SELECT seq FROM sqlite_sequence WHERE name = 'reservas');
INSERT INTO sqlite_sequence (name, seq)
SELECT 'reservas_nova', seq FROM sqlite_sequence
 WHERE name = 'reservas' AND NOT EXISTS (SELECT 1 FROM sqlite_sequence WHERE name = 'reservas_nova');

DROP TABLE reservas;
ALTER TABLE reservas_nova RENAME TO reservas;

CREATE INDEX idx_reservas_apto_status_datas ON reservas (a, status, i, f);
CREATE INDEX idx_reservas_lote ON reservas (lote_id);
CREATE INDEX idx_reservas_chave ON reservas (chave_import);
