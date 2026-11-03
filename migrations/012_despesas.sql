-- Despesas: conta de consumo da reserva (uma por reserva) e o LOG IMUTÁVEL de lançamentos.
-- Nada se edita nem se apaga: o erro é corrigido por um ESTORNO (nova linha negativa, com motivo).
-- Valores em centavos inteiros. A data/hora e o autor vêm do servidor, nunca do navegador.
-- Obs.: o SQLite deste projeto roda sem foreign_keys; por isso as regras de integridade estão em TRIGGERs abaixo.
CREATE TABLE despesa_conta (
    reserva_id   INTEGER PRIMARY KEY REFERENCES reservas(id) ON DELETE RESTRICT,
    situacao     TEXT NOT NULL DEFAULT 'aberta' CHECK (situacao IN ('aberta','fechada')),
    quitacao     TEXT NOT NULL DEFAULT 'pendente' CHECK (quitacao IN ('pendente','quitada')),
    fechada_em   TEXT,
    fechada_por  INTEGER REFERENCES usuarios(id),
    quitada_em   TEXT,
    quitada_por  INTEGER REFERENCES usuarios(id),
    versao       INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE despesa_lancamento (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    reserva_id          INTEGER NOT NULL REFERENCES reservas(id) ON DELETE RESTRICT,
    tipo                TEXT NOT NULL CHECK (tipo IN ('lancamento','estorno')),
    categoria           TEXT NOT NULL CHECK (categoria IN ('restaurante','bar','lavanderia','outros')),
    descricao           TEXT NOT NULL CHECK (length(descricao) BETWEEN 2 AND 80),
    quantidade          INTEGER NOT NULL CHECK (quantidade BETWEEN 1 AND 99),
    valor_unit_centavos INTEGER NOT NULL CHECK (valor_unit_centavos BETWEEN 1 AND 1000000),
    total_centavos      INTEGER NOT NULL,
    apto                TEXT NOT NULL,
    em                  TEXT NOT NULL,
    usuario_id          INTEGER,
    usuario_login       TEXT NOT NULL DEFAULT '',
    chave               TEXT CHECK (chave IS NULL OR length(chave) BETWEEN 8 AND 64),
    estorno_de          INTEGER REFERENCES despesa_lancamento(id),
    motivo              TEXT NOT NULL DEFAULT '' CHECK (length(motivo) <= 140),
    ip                  TEXT NOT NULL DEFAULT '',
    CHECK ((tipo = 'lancamento' AND total_centavos = quantidade * valor_unit_centavos AND estorno_de IS NULL)
        OR (tipo = 'estorno' AND total_centavos = -quantidade * valor_unit_centavos AND estorno_de IS NOT NULL
            AND length(motivo) >= 5))
);
CREATE INDEX idx_desp_reserva ON despesa_lancamento (reserva_id, id);
-- Trava 1: o mesmo duplo clique (mesma chave) não cria dois lançamentos.
CREATE UNIQUE INDEX uq_desp_chave ON despesa_lancamento (reserva_id, chave) WHERE chave IS NOT NULL;
-- Trava 2: um lançamento só pode ser estornado uma vez.
CREATE UNIQUE INDEX uq_desp_estorno ON despesa_lancamento (estorno_de) WHERE estorno_de IS NOT NULL;

-- Log imutável (mesmo modelo do histórico e da governança).
CREATE TRIGGER despesa_nao_altera BEFORE UPDATE ON despesa_lancamento
BEGIN
    SELECT RAISE(ABORT, 'O registro de despesas não pode ser alterado');
END;

CREATE TRIGGER despesa_nao_apaga BEFORE DELETE ON despesa_lancamento
BEGIN
    SELECT RAISE(ABORT, 'O registro de despesas não pode ser apagado');
END;

-- A reserva precisa existir (o SQLite não confere chaves estrangeiras aqui).
CREATE TRIGGER despesa_reserva_existe BEFORE INSERT ON despesa_lancamento
WHEN NOT EXISTS (SELECT 1 FROM reservas WHERE id = NEW.reserva_id)
BEGIN
    SELECT RAISE(ABORT, 'Reserva inexistente');
END;

-- Trava 3: no máximo 200 LANÇAMENTOS por reserva (estornos não contam: sempre dá para corrigir uma conta cheia).
CREATE TRIGGER despesa_limite BEFORE INSERT ON despesa_lancamento
WHEN NEW.tipo = 'lancamento'
 AND (SELECT COUNT(*) FROM despesa_lancamento WHERE reserva_id = NEW.reserva_id AND tipo = 'lancamento') >= 200
BEGIN
    SELECT RAISE(ABORT, 'Limite de lançamentos da reserva atingido');
END;

-- Estorno só aponta um LANÇAMENTO da MESMA reserva (nunca outro estorno).
CREATE TRIGGER despesa_estorno_valido BEFORE INSERT ON despesa_lancamento
WHEN NEW.estorno_de IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM despesa_lancamento WHERE id = NEW.estorno_de AND tipo = 'lancamento' AND reserva_id = NEW.reserva_id)
BEGIN
    SELECT RAISE(ABORT, 'Estorno inválido');
END;

-- Reserva com lançamentos não pode ser apagada (nem pela exclusão definitiva, nem pelo desfazer da importação).
CREATE TRIGGER reserva_com_despesa_nao_apaga BEFORE DELETE ON reservas
WHEN EXISTS (SELECT 1 FROM despesa_lancamento WHERE reserva_id = OLD.id)
BEGIN
    SELECT RAISE(ABORT, 'Reserva com despesas lançadas não pode ser excluída');
END;
