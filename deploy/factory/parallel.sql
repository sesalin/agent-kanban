-- Additive upgrade; retains all existing pipelines, task IDs and results.
-- Apply only to radars-n8n / uobeshcvmtawjxibciuy after sequential.sql.
BEGIN;
CREATE OR REPLACE FUNCTION public.factory_seq_steps(p public.opportunity_pipelines)
RETURNS text[] LANGUAGE sql IMMUTABLE SET search_path=public AS $$
 SELECT CASE WHEN p.factory_mode <> 'sequential' THEN ARRAY[]::text[]
 WHEN p.stage='BUILDING' THEN ARRAY(
   SELECT branch FROM unnest(ARRAY['mvp','prospection','landing']) AS branch
   WHERE (to_jsonb(p)->>('run_'||branch))::boolean
     AND to_jsonb(p)->>(branch||'_status') <> 'DONE')
 ELSE array_remove(ARRAY[public.factory_seq_next(p)],NULL) END;
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
 IF (p_step = ANY(public.factory_seq_steps(p))) IS NOT TRUE THEN RAISE EXCEPTION 'Preceding step is incomplete'; END IF;
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
 IF p.factory_mode <> 'sequential' OR (p_step = ANY(public.factory_seq_steps(p))) IS NOT TRUE
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

REVOKE ALL ON FUNCTION public.factory_seq_steps(public.opportunity_pipelines) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.factory_seq_steps(public.opportunity_pipelines) TO service_role;
COMMIT;
