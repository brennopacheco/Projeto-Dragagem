-- =====================================================================
-- Migração 0001 — Postgres (Supabase)
--
-- Por quê: o app cria o schema com db.create_all(), que só CRIA tabelas
-- novas — nunca ALTERA tabelas já existentes. As mudanças de modelo abaixo,
-- portanto, NÃO chegam sozinhas a um banco de produção já existente. Rode
-- este script UMA vez no banco de produção (psql ou Supabase > SQL Editor).
--
-- Sem ele, num banco antigo:
--   * re-importar uma tábua que já teve cancelamentos -> IntegrityError
--     (NOT NULL em realocacoes.trecho_cancelado_id);
--   * QUALQUER nova importação -> NOT NULL em trechos.inicio_real/fim_real/
--     fim_dia_seguinte (o app não preenche mais essas colunas).
--
-- É idempotente (pode rodar mais de uma vez) e atômico (tudo ou nada).
-- Em banco novo/recriado já é inócuo (não há o que alterar/remover).
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- Migração 1 — realocacoes.trecho_cancelado_id: NULLABLE + ON DELETE SET NULL
-- (corrige o crash de cascade ao apagar/recriar trechos)
-- ---------------------------------------------------------------------

-- 1a) Permitir NULL (no-op se já for nullable)
ALTER TABLE realocacoes ALTER COLUMN trecho_cancelado_id DROP NOT NULL;

-- 1b) Recriar a FK com ON DELETE SET NULL.
--     Descobre o nome real da constraint atual (pode variar) e a remove.
DO $$
DECLARE
    fk_name text;
BEGIN
    SELECT conname INTO fk_name
    FROM pg_constraint
    WHERE conrelid = 'realocacoes'::regclass
      AND contype = 'f'
      AND conkey = ARRAY[(
          SELECT attnum FROM pg_attribute
          WHERE attrelid = 'realocacoes'::regclass
            AND attname = 'trecho_cancelado_id'
      )];
    IF fk_name IS NOT NULL THEN
        EXECUTE format('ALTER TABLE realocacoes DROP CONSTRAINT %I', fk_name);
    END IF;
END $$;

ALTER TABLE realocacoes
    ADD CONSTRAINT realocacoes_trecho_cancelado_id_fkey
    FOREIGN KEY (trecho_cancelado_id) REFERENCES trechos (id) ON DELETE SET NULL;

-- ---------------------------------------------------------------------
-- Migração 2 — remover colunas mortas de trechos
-- (limpeza; o app não lê nem grava mais nenhuma delas)
-- ---------------------------------------------------------------------
ALTER TABLE trechos DROP COLUMN IF EXISTS inicio_real;
ALTER TABLE trechos DROP COLUMN IF EXISTS fim_real;
ALTER TABLE trechos DROP COLUMN IF EXISTS fim_dia_seguinte;
ALTER TABLE trechos DROP COLUMN IF EXISTS e1_hora;
ALTER TABLE trechos DROP COLUMN IF EXISTS e1_mare;
ALTER TABLE trechos DROP COLUMN IF EXISTS e2_hora;
ALTER TABLE trechos DROP COLUMN IF EXISTS e2_mare;
ALTER TABLE trechos DROP COLUMN IF EXISTS mes;

COMMIT;

-- ---------------------------------------------------------------------
-- Verificação (opcional) — rode após o COMMIT para conferir:
--
--   SELECT conname, confdeltype  -- confdeltype = 'n' significa SET NULL
--   FROM pg_constraint
--   WHERE conrelid = 'realocacoes'::regclass AND contype = 'f';
--
--   SELECT column_name FROM information_schema.columns
--   WHERE table_name = 'trechos' ORDER BY ordinal_position;
-- ---------------------------------------------------------------------
