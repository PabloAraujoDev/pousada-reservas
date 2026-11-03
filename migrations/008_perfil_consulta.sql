-- Novo perfil "consulta" (só visualizar e imprimir). O SQLite não altera um CHECK existente:
-- recria a tabela de usuários com o CHECK novo e copia tudo (nenhuma outra tabela aponta para ela).
CREATE TABLE usuarios_nova (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    login        TEXT NOT NULL UNIQUE COLLATE NOCASE,
    nome         TEXT NOT NULL,
    senha_hash   TEXT NOT NULL,
    papel        TEXT NOT NULL CHECK (papel IN ('admin','atendente','recepcao','camareira','diretoria','consulta')),
    ativo        INTEGER NOT NULL DEFAULT 1 CHECK (ativo IN (0,1)),
    trocar_senha INTEGER NOT NULL DEFAULT 0 CHECK (trocar_senha IN (0,1)),
    criado       TEXT NOT NULL,
    ultimo_login TEXT,
    sessao_ver   INTEGER NOT NULL DEFAULT 0
);
INSERT INTO usuarios_nova (id, login, nome, senha_hash, papel, ativo, trocar_senha, criado, ultimo_login, sessao_ver)
    SELECT id, login, nome, senha_hash, papel, ativo, trocar_senha, criado, ultimo_login, sessao_ver FROM usuarios;
DROP TABLE usuarios;
ALTER TABLE usuarios_nova RENAME TO usuarios;
