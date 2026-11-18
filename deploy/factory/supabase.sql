-- Target: radars-n8n / uobeshcvmtawjxibciuy
BEGIN;
-- ============================================================================
-- FÁBRICA AUTÓNOMA — MIGRACIÓN FINAL (SUPABASE: radars-n8n)
-- ============================================================================
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ----------------------------------------------------------------------------
-- 1. TABLA CENTRAL DE CONTROL DE PIPELINE (Escritor exclusivo: n8n)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS opportunity_pipelines (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id TEXT NOT NULL UNIQUE,
    radar_table TEXT NOT NULL CHECK (
        radar_table IN (
            'radar_gobierno_nl',
            'radar_compras_publicas',
            'radar_regulacion_federal'
        )
    ),
    title TEXT NOT NULL,
    base_folder TEXT NOT NULL, -- Ruta relativa bajo /mnt/c/_mcp/muse-packages/ (ej: gobierno-nl-20261118-01)

    -- Estado global de la fábrica
    stage TEXT NOT NULL DEFAULT 'RESEARCH' CHECK (
        stage IN (
            'RESEARCH',      -- Brio investigando
            'EVALUATING',    -- Bacha decidiendo GO / NO-GO
            'BUILDING',      -- Ramas paralelas activas (Codex / Instinct / Landing)
            'FINAL_REVIEW',  -- Todas las ramas listas; Bacha consolidando cierre
            'DONE',          -- Entregado al usuario
            'REJECTED'       -- Cerrado por NO-GO
        )
    ),

    -- Fase 1: Investigación (Brio)
    brio_task_id TEXT,
    input_zip_path TEXT,
    research_zip_path TEXT,

    -- Fase 2: Decisión (Bacha)
    decision TEXT CHECK (decision IN ('GO', 'NO_GO')),
    decision_notes TEXT,
    specs_payload JSONB NOT NULL DEFAULT '{}'::jsonb,

    -- Banderas definidas por Bacha al dar GO (determinan qué espera n8n)
    run_mvp BOOLEAN NOT NULL DEFAULT FALSE,
    run_prospection BOOLEAN NOT NULL DEFAULT FALSE,
    run_landing BOOLEAN NOT NULL DEFAULT FALSE,

    -- Fase 3: Control de ramas paralelas
    mvp_task_id TEXT,
    mvp_status TEXT NOT NULL DEFAULT 'SKIPPED' CHECK (mvp_status IN ('SKIPPED', 'PENDING', 'DONE', 'FAILED')),
    mvp_zip_path TEXT,

    prospection_task_id TEXT,
    prospection_status TEXT NOT NULL DEFAULT 'SKIPPED' CHECK (prospection_status IN ('SKIPPED', 'PENDING', 'DONE', 'FAILED')),
    prospection_zip_path TEXT,

    landing_task_id TEXT,
    landing_status TEXT NOT NULL DEFAULT 'SKIPPED' CHECK (landing_status IN ('SKIPPED', 'PENDING', 'DONE', 'FAILED')),
    landing_zip_path TEXT,

    -- Fase 4: Cierre final
    final_summary TEXT,
    final_bundle_path TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_pipelines_stage ON opportunity_pipelines(stage);
CREATE INDEX IF NOT EXISTS idx_pipelines_event ON opportunity_pipelines(event_id);

-- Trigger automático de updated_at
CREATE OR REPLACE FUNCTION set_pipeline_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_pipelines_updated_at ON opportunity_pipelines;
CREATE TRIGGER trg_pipelines_updated_at
BEFORE UPDATE ON opportunity_pipelines
FOR EACH ROW EXECUTE FUNCTION set_pipeline_updated_at();

-- ----------------------------------------------------------------------------
-- 2. ALTER TABLE EN TUS TABLAS DE RADAR EXISTENTES
-- (Agrega trazabilidad directa hacia el pipeline y el ticket inicial de Kanban)
-- ----------------------------------------------------------------------------
ALTER TABLE radar_gobierno_nl
    ADD COLUMN IF NOT EXISTS pipeline_id UUID REFERENCES opportunity_pipelines(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS kanban_task_id TEXT;

ALTER TABLE radar_compras_publicas
    ADD COLUMN IF NOT EXISTS pipeline_id UUID REFERENCES opportunity_pipelines(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS kanban_task_id TEXT;

ALTER TABLE radar_regulacion_federal
    ADD COLUMN IF NOT EXISTS pipeline_id UUID REFERENCES opportunity_pipelines(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS kanban_task_id TEXT;

CREATE INDEX IF NOT EXISTS idx_gobierno_pipeline ON radar_gobierno_nl(pipeline_id);
CREATE INDEX IF NOT EXISTS idx_compras_pipeline ON radar_compras_publicas(pipeline_id);
CREATE INDEX IF NOT EXISTS idx_regulacion_pipeline ON radar_regulacion_federal(pipeline_id);

-- ----------------------------------------------------------------------------
-- 3. FUNCIÓN DE APOYO PARA N8N (Evaluar si todas las ramas activas terminaron)
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION check_pipeline_ready_for_final_review(p_event_id TEXT)
RETURNS TABLE (
    is_ready BOOLEAN,
    pipeline_id UUID,
    base_folder TEXT,
    mvp_zip_path TEXT,
    prospection_zip_path TEXT,
    landing_zip_path TEXT
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        (
            p.stage = 'BUILDING'
            AND (NOT p.run_mvp OR p.mvp_status = 'DONE')
            AND (NOT p.run_prospection OR p.prospection_status = 'DONE')
            AND (NOT p.run_landing OR p.landing_status = 'DONE')
            AND (p.run_mvp OR p.run_prospection OR p.run_landing)
        ) AS is_ready,
        p.id,
        p.base_folder,
        p.mvp_zip_path,
        p.prospection_zip_path,
        p.landing_zip_path
    FROM opportunity_pipelines p
    WHERE p.event_id = p_event_id;
END;
$$ LANGUAGE plpgsql;

ALTER TABLE public.opportunity_pipelines ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.opportunity_pipelines FROM anon, authenticated;
GRANT ALL ON public.opportunity_pipelines TO service_role;
REVOKE ALL ON FUNCTION public.check_pipeline_ready_for_final_review(text) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.check_pipeline_ready_for_final_review(text) TO service_role;
REVOKE ALL ON FUNCTION public.set_pipeline_updated_at() FROM PUBLIC, anon, authenticated;
