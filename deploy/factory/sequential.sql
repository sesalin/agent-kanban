-- Apply only to radars-n8n / uobeshcvmtawjxibciuy, after the existing factory migrations.
BEGIN;
ALTER TABLE public.opportunity_pipelines
    ADD COLUMN IF NOT EXISTS factory_mode text NOT NULL DEFAULT 'events' CHECK (factory_mode IN ('events','sequential')),
    ADD COLUMN IF NOT EXISTS evaluation_task_id text,
    ADD COLUMN IF NOT EXISTS final_task_id text,
    ADD COLUMN IF NOT EXISTS last_error text;

CREATE TABLE IF NOT EXISTS public.factory_daily_reports (
    report_date date PRIMARY KEY,
    message text NOT NULL,
    sent_at timestamptz,
    telegram_message_id bigint,
    created_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE public.factory_daily_reports ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.factory_daily_reports FROM anon, authenticated;
GRANT ALL ON public.factory_daily_reports TO service_role;

CREATE TABLE IF NOT EXISTS public.factory_runtime (
    id text PRIMARY KEY,
    last_error text,
    updated_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE public.factory_runtime ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.factory_runtime FROM anon, authenticated;
GRANT ALL ON public.factory_runtime TO service_role;

CREATE OR REPLACE FUNCTION public.factory_seq_next(p public.opportunity_pipelines)
RETURNS text LANGUAGE sql IMMUTABLE SET search_path=public AS $$
 SELECT CASE
 WHEN p.factory_mode <> 'sequential' THEN NULL
 WHEN p.stage='RESEARCH' THEN 'research'
 WHEN p.stage='EVALUATING' THEN 'evaluation'
 WHEN p.stage='BUILDING' AND p.run_mvp AND p.mvp_status <> 'DONE' THEN 'mvp'
 WHEN p.stage='BUILDING' AND p.run_prospection AND p.prospection_status <> 'DONE' THEN 'prospection'
 WHEN p.stage='BUILDING' AND p.run_landing AND p.landing_status <> 'DONE' THEN 'landing'
 WHEN p.stage='FINAL_REVIEW' THEN 'final'
 ELSE NULL END;
$$;

CREATE OR REPLACE FUNCTION public.factory_seq_candidates(p_limit integer DEFAULT 20)
RETURNS jsonb LANGUAGE sql SET search_path=public AS $$
 SELECT coalesce(jsonb_agg(to_jsonb(s)), '[]'::jsonb) FROM (
  SELECT r.* FROM (
   SELECT 'radar_gobierno_nl' AS radar_table,event_id,title,package_path,package_filename,packaged_at FROM public.radar_gobierno_nl WHERE analysis_status='completed' AND muse_status='ready' AND package_status='ready'
   UNION ALL
   SELECT 'radar_compras_publicas',event_id,title,package_path,package_filename,packaged_at FROM public.radar_compras_publicas WHERE analysis_status='completed' AND muse_status='ready' AND package_status='ready'
   UNION ALL
   SELECT 'radar_regulacion_federal',event_id,title,package_path,package_filename,packaged_at FROM public.radar_regulacion_federal WHERE analysis_status='completed' AND muse_status='ready' AND package_status='ready'
  ) r WHERE NOT EXISTS (SELECT 1 FROM public.opportunity_pipelines p WHERE p.event_id=r.event_id)
  AND NOT EXISTS (SELECT 1 FROM public.factory_runtime f WHERE f.id='source:'||r.event_id AND f.last_error IS NOT NULL AND f.updated_at > now()-interval '1 hour')
  ORDER BY packaged_at NULLS LAST,event_id LIMIT greatest(1,least(p_limit,50))
 ) s;
$$;

CREATE OR REPLACE FUNCTION public.factory_seq_start(p_payload jsonb)
RETURNS public.opportunity_pipelines LANGUAGE plpgsql SET search_path=public AS $$
DECLARE p public.opportunity_pipelines;
BEGIN
 SELECT * INTO p FROM public.opportunity_pipelines WHERE event_id=p_payload->>'event_id' FOR UPDATE;
 IF FOUND THEN
  IF p.factory_mode <> 'sequential' THEN RAISE EXCEPTION 'Event already uses the event-driven pipeline'; END IF;
  RETURN p;
 END IF;
 p := public.factory_start(p_payload);
 UPDATE public.opportunity_pipelines SET factory_mode='sequential' WHERE id=p.id RETURNING * INTO p;
 RETURN p;
END;
$$;

CREATE OR REPLACE FUNCTION public.factory_seq_record_task(p_event_id text,p_step text,p_task_id text)
RETURNS public.opportunity_pipelines LANGUAGE plpgsql SET search_path=public AS $$
DECLARE p public.opportunity_pipelines; col text; previous text;
BEGIN
 IF p_step NOT IN ('research','evaluation','mvp','prospection','landing','final') OR p_task_id IS NULL OR p_task_id !~ '^[1-9][0-9]*$' THEN RAISE EXCEPTION 'Invalid sequential task'; END IF;
 SELECT * INTO STRICT p FROM public.opportunity_pipelines WHERE event_id=p_event_id FOR UPDATE;
 IF p.factory_mode <> 'sequential' THEN RAISE EXCEPTION 'Sequential pipeline required'; END IF;
 col := CASE p_step WHEN 'research' THEN 'brio_task_id' ELSE p_step || '_task_id' END;
 previous := to_jsonb(p)->>col;
 IF previous IS NOT NULL THEN
  IF previous <> p_task_id THEN RAISE EXCEPTION 'Step already has another task'; END IF;
  RETURN p;
 END IF;
 IF public.factory_seq_next(p) IS DISTINCT FROM p_step THEN RAISE EXCEPTION 'Preceding step is incomplete'; END IF;
 IF p_step IN ('research','mvp','prospection','landing') THEN
  RETURN public.factory_record_task(p_event_id,CASE p_step WHEN 'research' THEN 'brio' ELSE p_step END,p_task_id);
 END IF;
 EXECUTE format('UPDATE public.opportunity_pipelines SET %I=$1,last_error=NULL WHERE id=$2 RETURNING *',col) INTO p USING p_task_id,p.id;
 RETURN p;
END;
$$;

-- The coordinator validates a reviewed Kanban card and its ZIP before calling this RPC.
CREATE OR REPLACE FUNCTION public.factory_seq_complete(p_event_id text,p_step text,p_task_id text,p_payload jsonb)
RETURNS public.opportunity_pipelines LANGUAGE plpgsql SET search_path=public AS $$
DECLARE p public.opportunity_pipelines; col text;
BEGIN
 SELECT * INTO STRICT p FROM public.opportunity_pipelines WHERE event_id=p_event_id FOR UPDATE;
 col := CASE p_step WHEN 'research' THEN 'brio_task_id' ELSE p_step || '_task_id' END;
 IF p.factory_mode <> 'sequential' OR public.factory_seq_next(p) IS DISTINCT FROM p_step
 OR to_jsonb(p)->>col IS DISTINCT FROM p_task_id OR p_payload->>'event_id' IS DISTINCT FROM p_event_id THEN RAISE EXCEPTION 'Unexpected sequential completion'; END IF;
 IF p_step='research' THEN p := public.factory_research_done(p_payload);
 ELSIF p_step='evaluation' THEN p := public.factory_decide(p_payload);
 ELSIF p_step IN ('mvp','prospection','landing') THEN
  PERFORM public.factory_branch_done(p_payload);
  SELECT * INTO STRICT p FROM public.opportunity_pipelines WHERE event_id=p_event_id;
 ELSIF p_step='final' THEN p := public.factory_final_close(p_payload);
 ELSE RAISE EXCEPTION 'Invalid step'; END IF;
 UPDATE public.opportunity_pipelines SET last_error=NULL WHERE id=p.id RETURNING * INTO p;
 RETURN p;
END;
$$;

REVOKE ALL ON FUNCTION public.factory_seq_next(public.opportunity_pipelines),public.factory_seq_candidates(integer),public.factory_seq_start(jsonb),public.factory_seq_record_task(text,text,text),public.factory_seq_complete(text,text,text,jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.factory_seq_next(public.opportunity_pipelines),public.factory_seq_candidates(integer),public.factory_seq_start(jsonb),public.factory_seq_record_task(text,text,text),public.factory_seq_complete(text,text,text,jsonb) TO service_role;
COMMIT;
