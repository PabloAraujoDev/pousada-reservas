-- Notas (anotações com autor e data) da reserva e do apartamento: LOG IMUTÁVEL, só se acrescenta.
--   tipo 'nota'     = anotação nova;  'correcao' = novo texto da mesma nota (o texto anterior continua guardado);
--   tipo 'ocultar'  = a nota some das telas, mas NUNCA é apagada (só o administrador vê as ocultas).
-- O texto da nota nunca vai para o histórico (que só registra "nota adicionada/corrigida/ocultada"), nem para logs, CSV ou folha.
-- A data/hora e o autor vêm do servidor. O campo "o" da reserva continua existindo, intacto, como "Observação padrão".
-- Obs.: o SQLite deste projeto roda sem foreign_keys; a integridade está nos TRIGGERs abaixo.
CREATE TABLE nota (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    escopo        TEXT NOT NULL CHECK (escopo IN ('reserva','unidade')),
    reserva_id    INTEGER REFERENCES reservas(id) ON DELETE RESTRICT,
    unidade       TEXT CHECK (unidade IS NULL OR length(unidade) BETWEEN 3 AND 10),
    tipo          TEXT NOT NULL CHECK (tipo IN ('nota','correcao','ocultar')),
    nota_ref      INTEGER REFERENCES nota(id),
    texto         TEXT NOT NULL DEFAULT '' CHECK (length(texto) <= 300),
    motivo        TEXT NOT NULL DEFAULT '' CHECK (length(motivo) <= 140),
    em            TEXT NOT NULL,
    usuario_id    INTEGER,
    usuario_login TEXT NOT NULL DEFAULT '',
    chave         TEXT CHECK (chave IS NULL OR length(chave) BETWEEN 8 AND 64),
    ip            TEXT NOT NULL DEFAULT '',
    CHECK ((escopo = 'reserva' AND reserva_id IS NOT NULL AND unidade IS NULL)
        OR (escopo = 'unidade' AND unidade IS NOT NULL AND reserva_id IS NULL)),
    CHECK ((tipo = 'nota' AND length(texto) >= 1 AND nota_ref IS NULL)
        OR (tipo = 'correcao' AND length(texto) >= 1 AND nota_ref IS NOT NULL)
        OR (tipo = 'ocultar' AND texto = '' AND length(motivo) >= 3 AND nota_ref IS NOT NULL))
);
CREATE INDEX idx_nota_reserva ON nota (escopo, reserva_id, id);
CREATE INDEX idx_nota_unidade ON nota (escopo, unidade, id);
CREATE INDEX idx_nota_ref ON nota (nota_ref);
-- Trava 1: o mesmo duplo clique (mesma chave) não cria duas notas.
CREATE UNIQUE INDEX uq_nota_chave_reserva ON nota (reserva_id, chave) WHERE chave IS NOT NULL AND reserva_id IS NOT NULL;
CREATE UNIQUE INDEX uq_nota_chave_unidade ON nota (unidade, chave) WHERE chave IS NOT NULL AND unidade IS NOT NULL;
-- Trava 2: uma nota só é ocultada uma vez.
CREATE UNIQUE INDEX uq_nota_ocultar ON nota (nota_ref) WHERE tipo = 'ocultar';

-- Log imutável (mesmo modelo do histórico, da governança e das despesas).
CREATE TRIGGER nota_nao_altera BEFORE UPDATE ON nota
BEGIN
    SELECT RAISE(ABORT, 'O registro de notas não pode ser alterado');
END;

CREATE TRIGGER nota_nao_apaga BEFORE DELETE ON nota
BEGIN
    SELECT RAISE(ABORT, 'O registro de notas não pode ser apagado');
END;

-- A reserva precisa existir (o SQLite não confere chaves estrangeiras aqui).
CREATE TRIGGER nota_reserva_existe BEFORE INSERT ON nota
WHEN NEW.reserva_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM reservas WHERE id = NEW.reserva_id)
BEGIN
    SELECT RAISE(ABORT, 'Reserva inexistente');
END;

-- Correção e ocultar só apontam uma NOTA (nunca outra correção) do mesmo escopo, da mesma reserva ou unidade.
CREATE TRIGGER nota_ref_valida BEFORE INSERT ON nota
WHEN NEW.nota_ref IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM nota WHERE id = NEW.nota_ref AND tipo = 'nota' AND escopo = NEW.escopo
       AND IFNULL(reserva_id, 0) = IFNULL(NEW.reserva_id, 0) AND IFNULL(unidade, '') = IFNULL(NEW.unidade, ''))
BEGIN
    SELECT RAISE(ABORT, 'Nota de referência inválida');
END;

-- Nota oculta não recebe correção nem nova ocultação.
CREATE TRIGGER nota_oculta_nao_muda BEFORE INSERT ON nota
WHEN NEW.nota_ref IS NOT NULL AND EXISTS (SELECT 1 FROM nota WHERE nota_ref = NEW.nota_ref AND tipo = 'ocultar')
BEGIN
    SELECT RAISE(ABORT, 'Nota oculta não pode mais ser alterada');
END;

-- No máximo 100 notas (não ocultas contam também: o log só cresce) por reserva e por unidade.
CREATE TRIGGER nota_limite_reserva BEFORE INSERT ON nota
WHEN NEW.tipo = 'nota' AND NEW.reserva_id IS NOT NULL
 AND (SELECT COUNT(*) FROM nota WHERE reserva_id = NEW.reserva_id AND tipo = 'nota') >= 100
BEGIN
    SELECT RAISE(ABORT, 'Limite de notas da reserva atingido');
END;

CREATE TRIGGER nota_limite_unidade BEFORE INSERT ON nota
WHEN NEW.tipo = 'nota' AND NEW.unidade IS NOT NULL
 AND (SELECT COUNT(*) FROM nota WHERE unidade = NEW.unidade AND tipo = 'nota') >= 100
BEGIN
    SELECT RAISE(ABORT, 'Limite de notas da unidade atingido');
END;

-- Reserva com notas não pode ser apagada (exclusão definitiva nem desfazer da importação): cancele-a.
CREATE TRIGGER reserva_com_nota_nao_apaga BEFORE DELETE ON reservas
WHEN EXISTS (SELECT 1 FROM nota WHERE reserva_id = OLD.id)
BEGIN
    SELECT RAISE(ABORT, 'Reserva com notas não pode ser excluída');
END;
