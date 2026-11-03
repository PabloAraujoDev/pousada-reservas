-- Hospedagem (etapa 3A do Resumo da conta): estado explícito de check-in, "apartamento liberado e conta aberta",
-- placa do veículo, lista estruturada de hóspedes (titular + acompanhantes) e o LOG IMUTÁVEL dessas ações.
-- Tudo é opcional/NULL: reservas antigas e importadas ficam como estão (check-in "pendente", sem placa, sem hóspedes cadastrados).
-- Obs.: o SQLite deste projeto roda sem foreign_keys; a integridade está nos TRIGGERs abaixo.

-- Estado da hospedagem (a reserva é a hospedagem). Datas/horas locais do servidor; o autor é o login (texto).
ALTER TABLE reservas ADD COLUMN checkin_em TEXT;
ALTER TABLE reservas ADD COLUMN checkin_por TEXT;
ALTER TABLE reservas ADD COLUMN conta_aberta_em TEXT;      -- apartamento liberado, conta (despesas) continua aberta
ALTER TABLE reservas ADD COLUMN conta_aberta_por TEXT;
-- Placa do veículo: DADO PESSOAL. Normalizada (maiúsculas, sem hífen) e validada pelo servidor: 7 caracteres.
ALTER TABLE reservas ADD COLUMN placa TEXT CHECK (placa IS NULL OR length(placa) = 7);

-- Hóspedes da hospedagem. O TITULAR é a linha com titular = 1 (guarda só os dados extras: o nome vem de reservas.nome).
-- Documento e demais campos pessoais só existem se informados. A linha é apagada de verdade ao remover o hóspede
-- (minimização de dados); o que ficou registrado é só o log abaixo, sem nenhum dado pessoal.
CREATE TABLE hospedagem_hospede (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    reserva_id    INTEGER NOT NULL REFERENCES reservas(id) ON DELETE RESTRICT,
    titular       INTEGER NOT NULL DEFAULT 0 CHECK (titular IN (0,1)),
    ordem         INTEGER NOT NULL DEFAULT 0 CHECK (ordem BETWEEN 0 AND 100),
    nome          TEXT CHECK (nome IS NULL OR length(nome) BETWEEN 1 AND 120),
    tipo          TEXT NOT NULL DEFAULT 'adulto' CHECK (tipo IN ('adulto','crianca')),
    documento     TEXT CHECK (documento IS NULL OR length(documento) BETWEEN 3 AND 20),
    nascimento    TEXT CHECK (nascimento IS NULL OR length(nascimento) = 10),
    nacionalidade TEXT CHECK (nacionalidade IS NULL OR length(nacionalidade) BETWEEN 2 AND 40),
    profissao     TEXT CHECK (profissao IS NULL OR length(profissao) BETWEEN 2 AND 60),
    procedencia   TEXT CHECK (procedencia IS NULL OR length(procedencia) BETWEEN 2 AND 60),
    destino       TEXT CHECK (destino IS NULL OR length(destino) BETWEEN 2 AND 60),
    CHECK (titular = 1 OR nome IS NOT NULL)
);
CREATE INDEX idx_hospede_reserva ON hospedagem_hospede (reserva_id, ordem, id);
-- No máximo um titular por reserva.
CREATE UNIQUE INDEX uq_hospede_titular ON hospedagem_hospede (reserva_id) WHERE titular = 1;

-- A reserva precisa existir (o SQLite não confere chaves estrangeiras aqui).
CREATE TRIGGER hospede_reserva_existe BEFORE INSERT ON hospedagem_hospede
WHEN NOT EXISTS (SELECT 1 FROM reservas WHERE id = NEW.reserva_id)
BEGIN
    SELECT RAISE(ABORT, 'Reserva inexistente');
END;

-- A reserva excluída definitivamente (ou desfeita na importação) leva junto os dados pessoais dos hóspedes.
CREATE TRIGGER hospede_some_com_reserva AFTER DELETE ON reservas
BEGIN
    DELETE FROM hospedagem_hospede WHERE reserva_id = OLD.id;
END;

-- Log imutável de ações da hospedagem. 'detalhe' é texto CURTO e SEM dado pessoal (nomes de campos, contagens), nunca valores.
CREATE TABLE hospedagem_evento (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    reserva_id    INTEGER NOT NULL,
    acao          TEXT NOT NULL CHECK (acao IN ('checkin','checkin_reverter','liberar','liberar_reverter',
                                               'hospedes','placa','ficha')),
    detalhe       TEXT NOT NULL DEFAULT '' CHECK (length(detalhe) <= 140),
    em            TEXT NOT NULL,
    usuario_id    INTEGER,
    usuario_login TEXT NOT NULL DEFAULT '',
    ip            TEXT NOT NULL DEFAULT ''
);
CREATE INDEX idx_hosp_evento_reserva ON hospedagem_evento (reserva_id, id);

CREATE TRIGGER hospedagem_evento_nao_altera BEFORE UPDATE ON hospedagem_evento
BEGIN
    SELECT RAISE(ABORT, 'O registro da hospedagem não pode ser alterado');
END;

CREATE TRIGGER hospedagem_evento_nao_apaga BEFORE DELETE ON hospedagem_evento
BEGIN
    SELECT RAISE(ABORT, 'O registro da hospedagem não pode ser apagado');
END;

CREATE TRIGGER hospedagem_evento_reserva_existe BEFORE INSERT ON hospedagem_evento
WHEN NOT EXISTS (SELECT 1 FROM reservas WHERE id = NEW.reserva_id)
BEGIN
    SELECT RAISE(ABORT, 'Reserva inexistente');
END;
