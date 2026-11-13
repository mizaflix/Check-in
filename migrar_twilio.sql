-- Execute no PostgreSQL do Render uma única vez se preferir fazer a migração manualmente.
-- O app.py desta versão também verifica/cria a coluna automaticamente na inicialização.

ALTER TABLE responsavel
ADD COLUMN IF NOT EXISTS whatsapp_opt_in BOOLEAN NOT NULL DEFAULT FALSE;

-- Conferência:
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_name = 'responsavel'
  AND column_name = 'whatsapp_opt_in';
