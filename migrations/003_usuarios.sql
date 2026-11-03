-- Usuários do sistema e controle de tentativas de login.
-- A senha NUNCA é guardada: só o hash (senha_hash). login é único sem diferenciar maiúsculas.
CREATE TABLE usuarios (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    login        TEXT NOT NULL UNIQUE COLLATE NOCASE,
    nome         TEXT NOT NULL,
    senha_hash   TEXT NOT NULL,
    papel        TEXT NOT NULL CHECK (papel IN ('admin','atendente','recepcao','camareira','diretoria')),
    ativo        INTEGER NOT NULL DEFAULT 1 CHECK (ativo IN (0,1)),
    trocar_senha INTEGER NOT NULL DEFAULT 0 CHECK (trocar_senha IN (0,1)),
    criado       TEXT NOT NULL,
    ultimo_login TEXT
);

-- Cada login que FALHA vira uma linha (login digitado, IP, quando). Login certo apaga as do par login+IP.
CREATE TABLE tentativas_login (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    login TEXT NOT NULL,
    ip    TEXT NOT NULL,
    em    TEXT NOT NULL
);
CREATE INDEX idx_tentativas_login_ip ON tentativas_login (login, ip, em);
