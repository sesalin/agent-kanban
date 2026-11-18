-- Append to supabase.sql inside its transaction. Only n8n's server credential executes these RPCs.
CREATE OR REPLACE FUNCTION public.factory_get(p_event_id text)
RETURNS public.opportunity_pipelines LANGUAGE plpgsql SET search_path = public AS $$
DECLARE p public.opportunity_pipelines;
BEGIN
    SELECT * INTO STRICT p FROM public.opportunity_pipelines WHERE event_id=p_event_id;
    RETURN p;
END;
$$;

CREATE OR REPLACE FUNCTION public.factory_start(p_payload jsonb)
RETURNS public.opportunity_pipelines LANGUAGE plpgsql SET search_path = public AS $$
DECLARE
    p public.opportunity_pipelines;
    source_row jsonb;
    source_table text := p_payload->>'radar_table';
    event_key text := p_payload->>'event_id';
BEGIN
    IF source_table NOT IN ('radar_gobierno_nl', 'radar_compras_publicas', 'radar_regulacion_federal')
       OR source_table IS NULL OR event_key IS NULL OR event_key !~ '^[A-Za-z0-9][A-Za-z0-9_-]*$'
       OR nullif(p_payload->>'title', '') IS NULL THEN
        RAISE EXCEPTION 'Invalid radar event';
    END IF;
    EXECUTE format('SELECT to_jsonb(r) FROM public.%I r WHERE event_id=$1', source_table)
        INTO source_row USING event_key;
    IF source_row IS NULL OR source_row->>'package_status' <> 'ready' THEN
        RAISE EXCEPTION 'Radar event must have a ready package';
    END IF;
    INSERT INTO public.opportunity_pipelines(event_id, radar_table, title, base_folder, input_zip_path)
    VALUES(event_key, source_table, p_payload->>'title', event_key, event_key || '/01_input/paquete.zip')
    ON CONFLICT(event_id) DO NOTHING;
    SELECT * INTO STRICT p FROM public.opportunity_pipelines WHERE event_id=event_key FOR UPDATE;
    IF p.radar_table <> source_table THEN RAISE EXCEPTION 'Event already belongs to another radar'; END IF;
    RETURN p;
END;
$$;

CREATE OR REPLACE FUNCTION public.factory_record_task(p_event_id text, p_branch text, p_task_id text)
RETURNS public.opportunity_pipelines LANGUAGE plpgsql SET search_path = public AS $$
DECLARE
    p public.opportunity_pipelines;
    task_column text;
    existing_id text;
BEGIN
    IF p_branch NOT IN ('brio', 'mvp', 'prospection', 'landing')
       OR p_task_id IS NULL OR p_task_id !~ '^[1-9][0-9]*$' THEN
        RAISE EXCEPTION 'Invalid task reference';
    END IF;
    SELECT * INTO STRICT p FROM public.opportunity_pipelines WHERE event_id=p_event_id FOR UPDATE;
    task_column := p_branch || '_task_id';
    existing_id := to_jsonb(p)->>task_column;
    IF existing_id IS NOT NULL AND existing_id <> p_task_id THEN
        RAISE EXCEPTION 'Branch already has a different task';
    END IF;
    IF existing_id IS NOT NULL THEN RETURN p; END IF;
    IF (p_branch='brio' AND p.stage <> 'RESEARCH')
       OR (p_branch <> 'brio' AND (p.stage <> 'BUILDING' OR NOT (to_jsonb(p)->>('run_' || p_branch))::boolean)) THEN
        RAISE EXCEPTION 'Branch is not active';
    END IF;
    EXECUTE format('UPDATE public.opportunity_pipelines SET %I=$1 WHERE id=$2 RETURNING *', task_column)
        INTO p USING p_task_id, p.id;
    IF p_branch='brio' THEN
        EXECUTE format('UPDATE public.%I SET pipeline_id=$1, kanban_task_id=$2, muse_status=''sent'', muse_sent_at=now() WHERE event_id=$3', p.radar_table)
            USING p.id, p_task_id, p_event_id;
    END IF;
    RETURN p;
END;
$$;

CREATE OR REPLACE FUNCTION public.factory_research_done(p_payload jsonb)
RETURNS public.opportunity_pipelines LANGUAGE plpgsql SET search_path = public AS $$
DECLARE p public.opportunity_pipelines;
BEGIN
    SELECT * INTO STRICT p FROM public.opportunity_pipelines WHERE event_id=p_payload->>'event_id' FOR UPDATE;
    IF p.brio_task_id IS DISTINCT FROM p_payload->>'brio_task_id'
       OR p_payload->>'research_zip_path' IS DISTINCT FROM p.base_folder || '/02_research/research.zip' THEN
        RAISE EXCEPTION 'Research task or result path mismatch';
    END IF;
    IF p.stage='EVALUATING' THEN RETURN p; END IF;
    IF p.stage <> 'RESEARCH' THEN RAISE EXCEPTION 'Research is already closed'; END IF;
    UPDATE public.opportunity_pipelines SET stage='EVALUATING', research_zip_path=p_payload->>'research_zip_path'
        WHERE id=p.id RETURNING * INTO p;
    EXECUTE format('UPDATE public.%I SET muse_status=''completed'', muse_completed_at=now(), muse_result_path=$1, muse_result_filename=''research.zip'', muse_result_summary=$2, review_status=''pending'' WHERE event_id=$3', p.radar_table)
        USING p.research_zip_path, p_payload->>'summary', p.event_id;
    RETURN p;
END;
$$;

CREATE OR REPLACE FUNCTION public.factory_decide(p_payload jsonb)
RETURNS public.opportunity_pipelines LANGUAGE plpgsql SET search_path = public AS $$
DECLARE
    p public.opportunity_pipelines;
    branch text;
    active boolean;
    verdict text := p_payload->>'decision';
BEGIN
    SELECT * INTO STRICT p FROM public.opportunity_pipelines WHERE event_id=p_payload->>'event_id' FOR UPDATE;
    IF p.brio_task_id IS DISTINCT FROM p_payload->>'brio_task_id' OR verdict IS NULL OR verdict NOT IN ('GO','NO_GO') THEN
        RAISE EXCEPTION 'Invalid decision or research task';
    END IF;
    IF p.decision IS NOT NULL THEN
        IF p.decision <> verdict OR p.specs_payload <> p_payload THEN RAISE EXCEPTION 'Decision already recorded with different values'; END IF;
        RETURN p;
    END IF;
    IF p.stage <> 'EVALUATING' THEN RAISE EXCEPTION 'Pipeline must be evaluating'; END IF;
    FOREACH branch IN ARRAY ARRAY['mvp', 'prospection', 'landing'] LOOP
        IF jsonb_typeof(p_payload->'branches'->('run_' || branch)) IS DISTINCT FROM 'boolean' THEN
            RAISE EXCEPTION 'All branch flags must be booleans';
        END IF;
        active := (p_payload->'branches'->>('run_' || branch))::boolean;
        IF verdict='NO_GO' AND active THEN RAISE EXCEPTION 'NO_GO cannot activate branches'; END IF;
        IF active AND nullif(p_payload->'specs'->>(CASE branch WHEN 'prospection' THEN 'icp_prompt' ELSE branch || '_prompt' END), '') IS NULL THEN
            RAISE EXCEPTION 'Active branch requires a specification';
        END IF;
    END LOOP;
    IF verdict='GO' AND NOT ((p_payload->'branches'->>'run_mvp')::boolean OR (p_payload->'branches'->>'run_prospection')::boolean OR (p_payload->'branches'->>'run_landing')::boolean) THEN
        RAISE EXCEPTION 'GO requires at least one active branch';
    END IF;
    UPDATE public.opportunity_pipelines SET
        decision=verdict, decision_notes=p_payload->>'decision_notes', specs_payload=p_payload,
        stage=CASE verdict WHEN 'GO' THEN 'BUILDING' ELSE 'REJECTED' END,
        run_mvp=(p_payload->'branches'->>'run_mvp')::boolean,
        run_prospection=(p_payload->'branches'->>'run_prospection')::boolean,
        run_landing=(p_payload->'branches'->>'run_landing')::boolean,
        mvp_status=CASE WHEN (p_payload->'branches'->>'run_mvp')::boolean THEN 'PENDING' ELSE 'SKIPPED' END,
        prospection_status=CASE WHEN (p_payload->'branches'->>'run_prospection')::boolean THEN 'PENDING' ELSE 'SKIPPED' END,
        landing_status=CASE WHEN (p_payload->'branches'->>'run_landing')::boolean THEN 'PENDING' ELSE 'SKIPPED' END,
        completed_at=CASE verdict WHEN 'NO_GO' THEN now() ELSE NULL END
    WHERE id=p.id RETURNING * INTO p;
    EXECUTE format('UPDATE public.%I SET review_status=''reviewed'', resolution=$1, resolution_notes=$2, resolved_at=$3 WHERE event_id=$4', p.radar_table)
        USING CASE WHEN verdict='NO_GO' THEN 'discarded' WHEN p.run_mvp THEN 'build_mvp' ELSE 'interesting' END,
              p.decision_notes, p.completed_at, p.event_id;
    RETURN p;
END;
$$;

CREATE OR REPLACE FUNCTION public.factory_branch_done(p_payload jsonb)
RETURNS jsonb LANGUAGE plpgsql SET search_path = public AS $$
DECLARE
    p public.opportunity_pipelines;
    branch text := p_payload->>'branch';
    folder text;
    filename text;
    ready boolean;
BEGIN
    IF branch IS NULL OR branch NOT IN ('mvp','prospection','landing') THEN RAISE EXCEPTION 'Invalid branch'; END IF;
    SELECT * INTO STRICT p FROM public.opportunity_pipelines WHERE event_id=p_payload->>'event_id' FOR UPDATE;
    folder := CASE branch WHEN 'mvp' THEN '04_mvp' WHEN 'prospection' THEN '05_prospects' ELSE '06_landing' END;
    filename := CASE branch WHEN 'prospection' THEN 'prospects.zip' ELSE branch || '.zip' END;
    IF p.stage NOT IN ('BUILDING','FINAL_REVIEW') OR NOT (to_jsonb(p)->>('run_' || branch))::boolean
       OR to_jsonb(p)->>(branch || '_task_id') IS DISTINCT FROM p_payload->>'task_id'
       OR p_payload->>'zip_path' IS DISTINCT FROM p.base_folder || '/' || folder || '/' || filename THEN
        RAISE EXCEPTION 'Inactive branch or mismatched task/result path';
    END IF;
    EXECUTE format('UPDATE public.opportunity_pipelines SET %I=''DONE'', %I=$1 WHERE id=$2 RETURNING *', branch || '_status', branch || '_zip_path')
        INTO p USING p_payload->>'zip_path', p.id;
    ready := p.stage='BUILDING' AND (NOT p.run_mvp OR p.mvp_status='DONE')
        AND (NOT p.run_prospection OR p.prospection_status='DONE')
        AND (NOT p.run_landing OR p.landing_status='DONE')
        AND (p.run_mvp OR p.run_prospection OR p.run_landing);
    IF ready THEN
        UPDATE public.opportunity_pipelines SET stage='FINAL_REVIEW' WHERE id=p.id RETURNING * INTO p;
    END IF;
    RETURN to_jsonb(p) || jsonb_build_object('wake_final_review', ready);
END;
$$;

CREATE OR REPLACE FUNCTION public.factory_final_close(p_payload jsonb)
RETURNS public.opportunity_pipelines LANGUAGE plpgsql SET search_path = public AS $$
DECLARE p public.opportunity_pipelines;
BEGIN
    SELECT * INTO STRICT p FROM public.opportunity_pipelines WHERE event_id=p_payload->>'event_id' FOR UPDATE;
    IF nullif(p_payload->>'executive_summary','') IS NULL OR p_payload->>'bundle_path'
       IS DISTINCT FROM '/mnt/c/_mcp/muse-packages/' || p.base_folder || '/' THEN
        RAISE EXCEPTION 'Invalid final summary or bundle path';
    END IF;
    IF p.stage='DONE' AND p.final_summary=p_payload->>'executive_summary' THEN RETURN p; END IF;
    IF p.stage <> 'FINAL_REVIEW' THEN RAISE EXCEPTION 'Pipeline must be in final review'; END IF;
    UPDATE public.opportunity_pipelines SET stage='DONE', final_summary=p_payload->>'executive_summary',
        final_bundle_path=p_payload->>'bundle_path', completed_at=now() WHERE id=p.id RETURNING * INTO p;
    EXECUTE format('UPDATE public.%I SET resolved_at=$1, resolution_notes=$2 WHERE event_id=$3', p.radar_table)
        USING p.completed_at, p.final_summary, p.event_id;
    RETURN p;
END;
$$;

REVOKE ALL ON FUNCTION public.factory_get(text), public.factory_start(jsonb), public.factory_record_task(text,text,text),
    public.factory_research_done(jsonb), public.factory_decide(jsonb), public.factory_branch_done(jsonb),
    public.factory_final_close(jsonb) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.factory_get(text), public.factory_start(jsonb), public.factory_record_task(text,text,text),
    public.factory_research_done(jsonb), public.factory_decide(jsonb), public.factory_branch_done(jsonb),
    public.factory_final_close(jsonb) TO service_role;
COMMIT;
