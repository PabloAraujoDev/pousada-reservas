-- Catálogo de itens de consumo (Despesas) + LOG IMUTÁVEL das alterações do catálogo + vínculo do lançamento com o item.
-- Migração ADITIVA: não altera nenhuma linha existente de despesa_lancamento (lançamentos antigos ficam sem item, como estão).
-- O lançamento COPIA descrição e preço do item (congelados); mudar o preço depois não mexe no histórico.
-- Itens nunca são apagados (trigger): só desativados. A hora exata do lançamento é despesa_lancamento.em (servidor, America/Sao_Paulo).
CREATE TABLE catalogo_item (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    categoria        TEXT NOT NULL CHECK (categoria IN ('bebidas','porcoes','lavanderia','outros')),
    grupo            TEXT NOT NULL DEFAULT '' CHECK (length(grupo) <= 40),
    descricao        TEXT NOT NULL CHECK (length(descricao) BETWEEN 2 AND 80),
    preco_centavos   INTEGER NOT NULL CHECK (preco_centavos BETWEEN 1 AND 1000000),
    ativo            INTEGER NOT NULL DEFAULT 1 CHECK (ativo IN (0,1)),
    versao           INTEGER NOT NULL DEFAULT 1,
    grupo_ordem      TEXT NOT NULL,
    descricao_ordem  TEXT NOT NULL,
    criado_em        TEXT NOT NULL
);
-- Sem duplicar o mesmo item na mesma categoria/grupo (ignora acento e maiúscula).
CREATE UNIQUE INDEX uq_catalogo_item ON catalogo_item (categoria, grupo_ordem, descricao_ordem);

CREATE TABLE catalogo_log (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id        INTEGER NOT NULL REFERENCES catalogo_item(id),
    acao           TEXT NOT NULL CHECK (acao IN ('criado','editado','desativado','reativado')),
    antes          TEXT,
    depois         TEXT NOT NULL,
    em             TEXT NOT NULL,
    usuario_id     INTEGER,
    usuario_login  TEXT NOT NULL DEFAULT '',
    ip             TEXT NOT NULL DEFAULT ''
);
CREATE INDEX idx_catalogo_log_item ON catalogo_log (item_id, id);
CREATE TRIGGER catalogo_log_nao_altera BEFORE UPDATE ON catalogo_log BEGIN SELECT RAISE(ABORT, 'O registro do catálogo não pode ser alterado'); END;
CREATE TRIGGER catalogo_log_nao_apaga BEFORE DELETE ON catalogo_log BEGIN SELECT RAISE(ABORT, 'O registro do catálogo não pode ser apagado'); END;
CREATE TRIGGER catalogo_item_nao_apaga BEFORE DELETE ON catalogo_item BEGIN SELECT RAISE(ABORT, 'Item do catálogo não pode ser apagado: desative'); END;

-- Vínculo (opcional) do lançamento com o item de origem. NULL = lançamento antigo ou avulso (só administrador).
ALTER TABLE despesa_lancamento ADD COLUMN item_id INTEGER REFERENCES catalogo_item(id);
CREATE TRIGGER despesa_item_existe BEFORE INSERT ON despesa_lancamento
WHEN NEW.item_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM catalogo_item WHERE id = NEW.item_id)
BEGIN SELECT RAISE(ABORT, 'Item do catálogo inexistente'); END;
-- A hora do lançamento vem SEMPRE do servidor: AAAA-MM-DD HH:MM:SS (nunca vazia nem em outro formato).
CREATE TRIGGER despesa_hora_valida BEFORE INSERT ON despesa_lancamento
WHEN length(NEW.em) <> 19 OR NEW.em NOT GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9] [0-9][0-9]:[0-9][0-9]:[0-9][0-9]'
BEGIN SELECT RAISE(ABORT, 'Hora do lançamento inválida'); END;

-- Carga inicial (ordem alfabética dentro de cada categoria/grupo; preços em centavos).
INSERT INTO catalogo_item (categoria,grupo,descricao,preco_centavos,grupo_ordem,descricao_ordem,criado_em) VALUES ('bebidas','Águas','Água com gás',500,'aguas','agua com gas',datetime('now','localtime'));
INSERT INTO catalogo_item (categoria,grupo,descricao,preco_centavos,grupo_ordem,descricao_ordem,criado_em) VALUES ('bebidas','Águas','Água sem gás',400,'aguas','agua sem gas',datetime('now','localtime'));
INSERT INTO catalogo_item (categoria,grupo,descricao,preco_centavos,grupo_ordem,descricao_ordem,criado_em) VALUES ('bebidas','Cervejas (600ml)','Amstel 600ml',1200,'cervejas (600ml)','amstel 600ml',datetime('now','localtime'));
INSERT INTO catalogo_item (categoria,grupo,descricao,preco_centavos,grupo_ordem,descricao_ordem,criado_em) VALUES ('bebidas','Cervejas (600ml)','Antarctica 600ml',1200,'cervejas (600ml)','antarctica 600ml',datetime('now','localtime'));
INSERT INTO catalogo_item (categoria,grupo,descricao,preco_centavos,grupo_ordem,descricao_ordem,criado_em) VALUES ('bebidas','Cervejas (600ml)','Heineken 600ml',1500,'cervejas (600ml)','heineken 600ml',datetime('now','localtime'));
INSERT INTO catalogo_item (categoria,grupo,descricao,preco_centavos,grupo_ordem,descricao_ordem,criado_em) VALUES ('bebidas','Cervejas (600ml)','Original 600ml',1400,'cervejas (600ml)','original 600ml',datetime('now','localtime'));
INSERT INTO catalogo_item (categoria,grupo,descricao,preco_centavos,grupo_ordem,descricao_ordem,criado_em) VALUES ('bebidas','Cervejas Long Neck','Corona Long Neck',900,'cervejas long neck','corona long neck',datetime('now','localtime'));
INSERT INTO catalogo_item (categoria,grupo,descricao,preco_centavos,grupo_ordem,descricao_ordem,criado_em) VALUES ('bebidas','Cervejas Long Neck','Heineken Long Neck',900,'cervejas long neck','heineken long neck',datetime('now','localtime'));
INSERT INTO catalogo_item (categoria,grupo,descricao,preco_centavos,grupo_ordem,descricao_ordem,criado_em) VALUES ('bebidas','Refrigerantes','Refrigerante',600,'refrigerantes','refrigerante',datetime('now','localtime'));
INSERT INTO catalogo_item (categoria,grupo,descricao,preco_centavos,grupo_ordem,descricao_ordem,criado_em) VALUES ('bebidas','Sucos','Suco Del Valle (lata)',600,'sucos','suco del valle (lata)',datetime('now','localtime'));
INSERT INTO catalogo_item (categoria,grupo,descricao,preco_centavos,grupo_ordem,descricao_ordem,criado_em) VALUES ('bebidas','Sucos','Suco Tial (caixa 1L)',1200,'sucos','suco tial (caixa 1l)',datetime('now','localtime'));
INSERT INTO catalogo_item (categoria,grupo,descricao,preco_centavos,grupo_ordem,descricao_ordem,criado_em) VALUES ('bebidas','Vinhos','Vinho Tinto Seco Casa São Geraldo',3000,'vinhos','vinho tinto seco casa sao geraldo',datetime('now','localtime'));
INSERT INTO catalogo_item (categoria,grupo,descricao,preco_centavos,grupo_ordem,descricao_ordem,criado_em) VALUES ('bebidas','Vinhos','Vinho Tinto Suave Casa São Geraldo',3000,'vinhos','vinho tinto suave casa sao geraldo',datetime('now','localtime'));
INSERT INTO catalogo_item (categoria,grupo,descricao,preco_centavos,grupo_ordem,descricao_ordem,criado_em) VALUES ('bebidas','Vinhos','Vinho Tinto Seco Pêssego Casa São Geraldo',3500,'vinhos','vinho tinto seco pessego casa sao geraldo',datetime('now','localtime'));
INSERT INTO catalogo_item (categoria,grupo,descricao,preco_centavos,grupo_ordem,descricao_ordem,criado_em) VALUES ('bebidas','Vinhos','Vinho Tinto Suave Pêssego Casa São Geraldo',3500,'vinhos','vinho tinto suave pessego casa sao geraldo',datetime('now','localtime'));
INSERT INTO catalogo_item (categoria,grupo,descricao,preco_centavos,grupo_ordem,descricao_ordem,criado_em) VALUES ('bebidas','Vinhos','Vinho Tinto Suave Marcon/Bordô',3500,'vinhos','vinho tinto suave marcon/bordo',datetime('now','localtime'));
INSERT INTO catalogo_item (categoria,grupo,descricao,preco_centavos,grupo_ordem,descricao_ordem,criado_em) VALUES ('porcoes','','Batata Frita ou Mandioca Frita',3200,'','batata frita ou mandioca frita',datetime('now','localtime'));
INSERT INTO catalogo_item (categoria,grupo,descricao,preco_centavos,grupo_ordem,descricao_ordem,criado_em) VALUES ('porcoes','','Batata Frita c/ queijo',4000,'','batata frita c/ queijo',datetime('now','localtime'));
INSERT INTO catalogo_item (categoria,grupo,descricao,preco_centavos,grupo_ordem,descricao_ordem,criado_em) VALUES ('porcoes','','Batata Frita c/ queijo e bacon',4500,'','batata frita c/ queijo e bacon',datetime('now','localtime'));
INSERT INTO catalogo_item (categoria,grupo,descricao,preco_centavos,grupo_ordem,descricao_ordem,criado_em) VALUES ('porcoes','','Bife Acebolado (Alcatra)',5000,'','bife acebolado (alcatra)',datetime('now','localtime'));
INSERT INTO catalogo_item (categoria,grupo,descricao,preco_centavos,grupo_ordem,descricao_ordem,criado_em) VALUES ('porcoes','','Bife Acebolado (Contra-Filé)',5400,'','bife acebolado (contra-file)',datetime('now','localtime'));
INSERT INTO catalogo_item (categoria,grupo,descricao,preco_centavos,grupo_ordem,descricao_ordem,criado_em) VALUES ('porcoes','','Calabresa Acebolada',4500,'','calabresa acebolada',datetime('now','localtime'));
INSERT INTO catalogo_item (categoria,grupo,descricao,preco_centavos,grupo_ordem,descricao_ordem,criado_em) VALUES ('porcoes','','Frango a Passarinho',5000,'','frango a passarinho',datetime('now','localtime'));
INSERT INTO catalogo_item (categoria,grupo,descricao,preco_centavos,grupo_ordem,descricao_ordem,criado_em) VALUES ('porcoes','','Hot Pocket Sadia',2000,'','hot pocket sadia',datetime('now','localtime'));
INSERT INTO catalogo_item (categoria,grupo,descricao,preco_centavos,grupo_ordem,descricao_ordem,criado_em) VALUES ('porcoes','','Lasanha congelada',2000,'','lasanha congelada',datetime('now','localtime'));
INSERT INTO catalogo_item (categoria,grupo,descricao,preco_centavos,grupo_ordem,descricao_ordem,criado_em) VALUES ('porcoes','','Omelete',1500,'','omelete',datetime('now','localtime'));
INSERT INTO catalogo_item (categoria,grupo,descricao,preco_centavos,grupo_ordem,descricao_ordem,criado_em) VALUES ('porcoes','','Ovo frito',200,'','ovo frito',datetime('now','localtime'));
INSERT INTO catalogo_item (categoria,grupo,descricao,preco_centavos,grupo_ordem,descricao_ordem,criado_em) VALUES ('porcoes','','Tiras de Peixe (Tilápia)',6000,'','tiras de peixe (tilapia)',datetime('now','localtime'));
INSERT INTO catalogo_log (item_id,acao,antes,depois,em,usuario_login) SELECT id,'criado',NULL,json_object('categoria',categoria,'grupo',grupo,'descricao',descricao,'preco_centavos',preco_centavos,'ativo',ativo),criado_em,'migração 016' FROM catalogo_item;
