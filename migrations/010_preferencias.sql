-- Preferências de tela de cada usuário (menus visíveis, aba ao abrir, período do mapa), em JSON.
-- É só estética: não concede nem retira permissão. '{}' = tudo como sempre foi (usuários antigos não mudam).
ALTER TABLE usuarios ADD COLUMN preferencias TEXT NOT NULL DEFAULT '{}' CHECK (length(preferencias) <= 2000);
