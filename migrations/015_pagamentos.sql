-- Pagamentos, transferência de despesas entre hospedagens e eventos da conta (etapa 3B do Resumo da conta).
-- Tudo em centavos inteiros e em tabelas APPEND-ONLY (triggers): corrigir é estornar (nova linha negativa, com motivo).
-- NUNCA guarda número de cartão, CVV nem validade: só bandeira, modalidade, parcelas e um código curto de autorização/NSU.
-- Obs.: o SQLite deste projeto roda sem foreign_keys; a integridade está nos TRIGGERs abaixo.

-- Transferência de despesas entre duas reservas (cabeçalho). As linhas de despesa dos dois lados apontam para ela.
CREATE TABLE transferencia (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    origem_id     INTEGER NOT NULL,
    destino_id    INTEGER NOT NULL,
    apto_origem   TEXT NOT NULL,
    apto_destino  TEXT NOT NULL,
    total_centavos INTEGER NOT NULL CHECK (total_centavos > 0),
    itens         INTEGER NOT NULL CHECK (itens BETWEEN 1 AND 201),
    com_diaria    INTEGER NOT NULL DEFAULT 0 CHECK (com_diaria IN (0,1)),
    em            TEXT NOT NULL,
    usuario_id    INTEGER,
    usuario_login TEXT NOT NULL DEFAULT '',
    chave         TEXT CHECK (chave IS NULL OR length(chave) BETWEEN 8 AND 64),
    ip            TEXT NOT NULL DEFAULT '',
    CHECK (origem_id <> destino_id)
);
CREATE INDEX idx_transf_origem ON transferencia (origem_id, id);
CREATE INDEX idx_transf_destino ON transferencia (destino_id, id);
CREATE UNIQUE INDEX uq_transf_chave ON transferencia (origem_id, chave) WHERE chave IS NOT NULL;

CREATE TRIGGER transferencia_nao_altera BEFORE UPDATE ON transferencia
BEGIN SELECT RAISE(ABORT, 'O registro de transferências não pode ser alterado'); END;
CREATE TRIGGER transferencia_nao_apaga BEFORE DELETE ON transferencia
BEGIN SELECT RAISE(ABORT, 'O registro de transferências não pode ser apagado'); END;
CREATE TRIGGER transferencia_reservas_existem BEFORE INSERT ON transferencia
WHEN NOT EXISTS (SELECT 1 FROM reservas WHERE id = NEW.origem_id) OR NOT EXISTS (SELECT 1 FROM reservas WHERE id = NEW.destino_id)
BEGIN SELECT RAISE(ABORT, 'Reserva inexistente'); END;

-- As linhas de despesa criadas por uma transferência (estorno na origem, lançamento no destino) guardam o vínculo.
ALTER TABLE despesa_lancamento ADD COLUMN transferencia_id INTEGER;
CREATE INDEX idx_desp_transf ON despesa_lancamento (transferencia_id) WHERE transferencia_id IS NOT NULL;
CREATE TRIGGER despesa_transferencia_valida BEFORE INSERT ON despesa_lancamento
WHEN NEW.transferencia_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM transferencia WHERE id = NEW.transferencia_id AND (origem_id = NEW.reserva_id OR destino_id = NEW.reserva_id))
BEGIN SELECT RAISE(ABORT, 'Transferência inválida'); END;

-- Pagamentos recebidos (dinheiro, Pix ou cartão). Estorno = linha negativa que aponta o recebimento (um estorno por recebimento).
CREATE TABLE pagamento (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    reserva_id      INTEGER NOT NULL,
    tipo            TEXT NOT NULL CHECK (tipo IN ('recebimento','estorno')),
    forma           TEXT NOT NULL CHECK (forma IN ('dinheiro','pix','cartao')),
    valor_centavos  INTEGER NOT NULL,
    recebido_centavos INTEGER CHECK (recebido_centavos IS NULL OR recebido_centavos > 0),
    troco_centavos  INTEGER CHECK (troco_centavos IS NULL OR troco_centavos >= 0),
    bandeira        TEXT CHECK (bandeira IS NULL OR length(bandeira) BETWEEN 2 AND 20),
    modalidade      TEXT CHECK (modalidade IS NULL OR modalidade IN ('credito','debito')),
    parcelas        INTEGER CHECK (parcelas IS NULL OR parcelas BETWEEN 1 AND 24),
    autorizacao     TEXT CHECK (autorizacao IS NULL OR length(autorizacao) BETWEEN 1 AND 12),
    referencia      TEXT CHECK (referencia IS NULL OR length(referencia) BETWEEN 1 AND 32),
    itens           TEXT NOT NULL DEFAULT '' CHECK (length(itens) <= 1500),
    apto            TEXT NOT NULL,
    em              TEXT NOT NULL,
    usuario_id      INTEGER,
    usuario_login   TEXT NOT NULL DEFAULT '',
    chave           TEXT CHECK (chave IS NULL OR length(chave) BETWEEN 8 AND 64),
    estorno_de      INTEGER REFERENCES pagamento(id),
    motivo          TEXT NOT NULL DEFAULT '' CHECK (length(motivo) <= 140),
    ip              TEXT NOT NULL DEFAULT '',
    CHECK ((tipo = 'recebimento' AND valor_centavos > 0 AND estorno_de IS NULL)
        OR (tipo = 'estorno' AND valor_centavos < 0 AND estorno_de IS NOT NULL AND length(motivo) >= 5)),
    CHECK ((forma = 'cartao' AND bandeira IS NOT NULL AND modalidade IS NOT NULL AND parcelas IS NOT NULL
            AND (modalidade = 'credito' OR parcelas = 1) AND referencia IS NULL)
        OR (forma = 'pix' AND bandeira IS NULL AND modalidade IS NULL AND parcelas IS NULL AND autorizacao IS NULL)
        OR (forma = 'dinheiro' AND bandeira IS NULL AND modalidade IS NULL AND parcelas IS NULL AND autorizacao IS NULL
            AND referencia IS NULL)),
    CHECK (forma = 'dinheiro' OR (recebido_centavos IS NULL AND troco_centavos IS NULL))
);
CREATE INDEX idx_pag_reserva ON pagamento (reserva_id, id);
CREATE UNIQUE INDEX uq_pag_chave ON pagamento (reserva_id, chave) WHERE chave IS NOT NULL;
CREATE UNIQUE INDEX uq_pag_estorno ON pagamento (estorno_de) WHERE estorno_de IS NOT NULL;

CREATE TRIGGER pagamento_nao_altera BEFORE UPDATE ON pagamento
BEGIN SELECT RAISE(ABORT, 'O registro de pagamentos não pode ser alterado'); END;
CREATE TRIGGER pagamento_nao_apaga BEFORE DELETE ON pagamento
BEGIN SELECT RAISE(ABORT, 'O registro de pagamentos não pode ser apagado'); END;
CREATE TRIGGER pagamento_reserva_existe BEFORE INSERT ON pagamento
WHEN NOT EXISTS (SELECT 1 FROM reservas WHERE id = NEW.reserva_id)
BEGIN SELECT RAISE(ABORT, 'Reserva inexistente'); END;
-- No máximo 100 recebimentos por reserva (estornos não contam).
CREATE TRIGGER pagamento_limite BEFORE INSERT ON pagamento
WHEN NEW.tipo = 'recebimento' AND (SELECT COUNT(*) FROM pagamento WHERE reserva_id = NEW.reserva_id AND tipo = 'recebimento') >= 100
BEGIN SELECT RAISE(ABORT, 'Limite de pagamentos da reserva atingido'); END;
-- O estorno aponta um RECEBIMENTO da mesma reserva e devolve exatamente o valor recebido.
CREATE TRIGGER pagamento_estorno_valido BEFORE INSERT ON pagamento
WHEN NEW.estorno_de IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM pagamento WHERE id = NEW.estorno_de AND tipo = 'recebimento' AND reserva_id = NEW.reserva_id
        AND valor_centavos = -NEW.valor_centavos AND forma = NEW.forma)
BEGIN SELECT RAISE(ABORT, 'Estorno de pagamento inválido'); END;
CREATE TRIGGER reserva_com_pagamento_nao_apaga BEFORE DELETE ON reservas
WHEN EXISTS (SELECT 1 FROM pagamento WHERE reserva_id = OLD.id)
BEGIN SELECT RAISE(ABORT, 'Reserva com pagamentos registrados não pode ser excluída'); END;

-- Eventos da conta que não são lançamentos nem pagamentos: fechar, reabrir (com motivo) e zerar a diária informada (com motivo).
CREATE TABLE conta_evento (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    reserva_id      INTEGER NOT NULL,
    acao            TEXT NOT NULL CHECK (acao IN ('fechar','reabrir','diaria_zerar')),
    motivo          TEXT NOT NULL DEFAULT '' CHECK (length(motivo) <= 140),
    valor_centavos  INTEGER CHECK (valor_centavos IS NULL OR valor_centavos > 0),   -- diária zerada: total das diárias (diária x noites)
    noites          INTEGER,
    transferencia_id INTEGER,
    em              TEXT NOT NULL,
    usuario_id      INTEGER,
    usuario_login   TEXT NOT NULL DEFAULT '',
    chave           TEXT CHECK (chave IS NULL OR length(chave) BETWEEN 8 AND 64),
    ip              TEXT NOT NULL DEFAULT '',
    CHECK (acao = 'fechar' OR length(motivo) >= 5),
    CHECK ((acao = 'diaria_zerar') = (valor_centavos IS NOT NULL))
);
CREATE INDEX idx_conta_ev_reserva ON conta_evento (reserva_id, id);
CREATE UNIQUE INDEX uq_conta_ev_chave ON conta_evento (reserva_id, chave) WHERE chave IS NOT NULL;
CREATE TRIGGER conta_evento_nao_altera BEFORE UPDATE ON conta_evento
BEGIN SELECT RAISE(ABORT, 'O registro da conta não pode ser alterado'); END;
CREATE TRIGGER conta_evento_nao_apaga BEFORE DELETE ON conta_evento
BEGIN SELECT RAISE(ABORT, 'O registro da conta não pode ser apagado'); END;
CREATE TRIGGER conta_evento_reserva_existe BEFORE INSERT ON conta_evento
WHEN NOT EXISTS (SELECT 1 FROM reservas WHERE id = NEW.reserva_id)
BEGIN SELECT RAISE(ABORT, 'Reserva inexistente'); END;
