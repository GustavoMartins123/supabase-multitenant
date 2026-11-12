ALTER TABLE access_quota_usage
    ADD COLUMN shard smallint NOT NULL DEFAULT 0 CHECK (shard BETWEEN 0 AND 15);
ALTER TABLE access_quota_usage DROP CONSTRAINT access_quota_usage_pkey;
ALTER TABLE access_quota_usage
    ADD PRIMARY KEY (project_id, scope_type, scope_id, period, period_start, shard);

CREATE OR REPLACE FUNCTION consume_access_quota(p_project uuid, p_slot uuid, p_admin boolean)
RETURNS bigint LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_catalog AS $$
DECLARE
    scope_ids uuid[];
    scope_kinds text[];
    scope_quotas jsonb[];
    idx integer;
    period_name text;
    period_begin timestamptz;
    period_end timestamptz;
    current_count bigint;
    limited boolean;
    wait_seconds bigint := 0;
    free_shard smallint := 1 + pg_backend_pid() % 15;
BEGIN
    IF p_slot IS NOT NULL AND NOT EXISTS (SELECT 1 FROM project_api_key_slots WHERE id=p_slot AND project_id=p_project AND status='active') THEN
        RAISE EXCEPTION 'Invalid quota slot';
    END IF;
    IF NOT EXISTS(SELECT 1 FROM project_access_policies WHERE project_id=p_project) THEN
        RAISE EXCEPTION 'Missing project policy';
    END IF;
    IF p_slot IS NOT NULL AND NOT EXISTS(SELECT 1 FROM slot_access_policies WHERE slot_id=p_slot) THEN
        RAISE EXCEPTION 'Missing slot policy';
    END IF;
    SELECT array_agg(s.id ORDER BY s.kind, s.id), array_agg(s.kind ORDER BY s.kind, s.id),
           array_agg(s.quota ORDER BY s.kind, s.id)
      INTO scope_ids, scope_kinds, scope_quotas
      FROM (
        SELECT p_project AS id, CASE WHEN p_admin THEN 'admin' ELSE 'project' END AS kind,
            CASE WHEN p_admin THEN NULL ELSE policy->'request_quota' END AS quota
            FROM project_access_policies WHERE project_id=p_project
        UNION ALL SELECT slot_id, 'slot', policy->'request_quota' FROM slot_access_policies
            WHERE slot_id=p_slot AND NOT p_admin
      ) s;
    FOR idx IN 1..array_length(scope_ids, 1) LOOP
        FOREACH period_name IN ARRAY ARRAY['day','month'] LOOP
            CONTINUE WHEN scope_quotas[idx]->>'period' IS DISTINCT FROM period_name;
            period_begin := date_trunc(period_name, now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC';
            period_end := ((period_begin AT TIME ZONE 'UTC') + CASE WHEN period_name='day' THEN interval '1 day' ELSE interval '1 month' END) AT TIME ZONE 'UTC';
            INSERT INTO access_quota_usage(project_id,scope_id,scope_type,period,period_start,shard)
                VALUES(p_project,scope_ids[idx],scope_kinds[idx],period_name,period_begin,0) ON CONFLICT DO NOTHING;
            PERFORM 1 FROM access_quota_usage
                WHERE project_id=p_project AND scope_id=scope_ids[idx] AND scope_type=scope_kinds[idx]
                    AND period=period_name AND period_start=period_begin AND shard=0 FOR UPDATE;
            SELECT sum(admitted) INTO current_count FROM access_quota_usage
                WHERE project_id=p_project AND scope_id=scope_ids[idx] AND scope_type=scope_kinds[idx]
                    AND period=period_name AND period_start=period_begin;
            IF current_count >= (scope_quotas[idx]->>'limit')::bigint THEN
                wait_seconds := greatest(wait_seconds, ceil(extract(epoch FROM period_end-now()))::bigint);
            END IF;
        END LOOP;
    END LOOP;
    IF wait_seconds > 0 THEN RETURN wait_seconds; END IF;
    FOR idx IN 1..array_length(scope_ids, 1) LOOP
        FOREACH period_name IN ARRAY ARRAY['day','month'] LOOP
            limited := scope_quotas[idx]->>'period' = period_name;
            period_begin := date_trunc(period_name, now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC';
            INSERT INTO access_quota_usage(project_id,scope_id,scope_type,period,period_start,shard,admitted)
                VALUES(p_project,scope_ids[idx],scope_kinds[idx],period_name,period_begin,
                    CASE WHEN limited THEN 0 ELSE free_shard END,1)
                ON CONFLICT (project_id,scope_type,scope_id,period,period_start,shard)
                DO UPDATE SET admitted = access_quota_usage.admitted + 1;
        END LOOP;
    END LOOP;
    RETURN 0;
END;
$$;
