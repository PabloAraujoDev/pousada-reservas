-- Impressão digital (SHA-256) do arquivo importado: serve só para AVISAR se o mesmo arquivo for enviado de novo.
ALTER TABLE importacoes ADD COLUMN sha256 TEXT;
CREATE INDEX idx_importacoes_sha256 ON importacoes (sha256);
