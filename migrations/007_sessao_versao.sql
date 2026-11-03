-- Versão da sessão de cada usuário: o "sair" a aumenta, e então qualquer cookie de sessão copiado
-- antes do logout deixa de valer (o cookie é assinado, mas o servidor não guardava nada sobre ele).
ALTER TABLE usuarios ADD COLUMN sessao_ver INTEGER NOT NULL DEFAULT 0;
