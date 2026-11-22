-- Importação que também CANCELA e ATUALIZA reservas já existentes (planilha nova = fonte da verdade).
-- Guarda, por lote, o estado anterior das reservas alteradas, para "Desfazer importação" poder reverter.
-- Migração ADITIVA: não altera nenhuma linha existente. 'antes' é JSON só com os campos que a importação mexe.
-- 'versao_depois' é a versão da reserva logo após a importação: se mudou depois, o desfazer NÃO reverte (respeita o trabalho posterior).
CREATE TABLE importacao_alteracao (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    lote_id       INTEGER NOT NULL,
    reserva_id    INTEGER NOT NULL,
    tipo          TEXT NOT NULL CHECK (tipo IN ('cancelamento','atualizacao')),
    antes         TEXT NOT NULL,
    versao_depois INTEGER NOT NULL
);
CREATE INDEX idx_imp_alteracao_lote ON importacao_alteracao (lote_id);
