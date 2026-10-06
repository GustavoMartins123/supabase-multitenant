CREATE TABLE project_access_policies (
    project_id uuid PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
    policy jsonb NOT NULL CHECK (jsonb_typeof(policy) = 'object'),
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    updated_by uuid REFERENCES users(id) ON DELETE SET NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE slot_access_policies (
    slot_id uuid PRIMARY KEY REFERENCES project_api_key_slots(id) ON DELETE CASCADE,
    policy jsonb NOT NULL CHECK (jsonb_typeof(policy) = 'object'),
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    updated_by uuid REFERENCES users(id) ON DELETE SET NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO project_access_policies(project_id, policy)
SELECT id, '{"geo_mode":"unrestricted","allowed_countries":null,"allowed_networks":[],"rate_limit":null,"request_quota":null}'::jsonb FROM projects;
INSERT INTO slot_access_policies(slot_id, policy)
SELECT id, '{"geo_mode":"inherit","allowed_countries":null,"allowed_networks":[],"rate_limit":null,"request_quota":null}'::jsonb FROM project_api_key_slots;

CREATE FUNCTION provision_access_policy() RETURNS trigger
LANGUAGE plpgsql SET search_path = public, pg_catalog AS $$
BEGIN
    IF TG_TABLE_NAME = 'projects' THEN
        INSERT INTO project_access_policies(project_id, policy) VALUES
        (NEW.id, '{"geo_mode":"unrestricted","allowed_countries":null,"allowed_networks":[],"rate_limit":null,"request_quota":null}'::jsonb);
    ELSE
        INSERT INTO slot_access_policies(slot_id, policy) VALUES
        (NEW.id, '{"geo_mode":"inherit","allowed_countries":null,"allowed_networks":[],"rate_limit":null,"request_quota":null}'::jsonb);
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER provision_project_access_policy AFTER INSERT ON projects
FOR EACH ROW EXECUTE FUNCTION provision_access_policy();
CREATE TRIGGER provision_slot_access_policy AFTER INSERT ON project_api_key_slots
FOR EACH ROW EXECUTE FUNCTION provision_access_policy();

CREATE TABLE access_quota_usage (
    project_id uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    scope_id uuid NOT NULL,
    scope_type text NOT NULL CHECK (scope_type IN ('project','slot','admin')),
    period text NOT NULL CHECK (period IN ('day','month')),
    period_start timestamptz NOT NULL,
    admitted bigint NOT NULL DEFAULT 0 CHECK (admitted >= 0),
    PRIMARY KEY(project_id, scope_type, scope_id, period, period_start)
);
CREATE TABLE access_rate_epoch (
    singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
    epoch uuid NOT NULL,
    initialized boolean NOT NULL DEFAULT false
);
INSERT INTO access_rate_epoch(singleton, epoch) VALUES(true, gen_random_uuid());

REVOKE ALL ON project_access_policies, slot_access_policies, access_quota_usage,
    access_rate_epoch FROM PUBLIC;
REVOKE ALL ON FUNCTION provision_access_policy() FROM PUBLIC;

CREATE FUNCTION initialize_access_rate_epoch() RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_catalog AS $$
BEGIN
    UPDATE access_rate_epoch SET initialized=true WHERE singleton AND NOT initialized;
END;
$$;
REVOKE ALL ON FUNCTION initialize_access_rate_epoch() FROM PUBLIC;

CREATE FUNCTION consume_access_quota(p_project uuid, p_slot uuid, p_admin boolean)
RETURNS bigint LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_catalog AS $$
DECLARE
    scope record;
    period_name text;
    period_begin timestamptz;
    period_end timestamptz;
    current_count bigint;
    quota jsonb;
    wait_seconds bigint := 0;
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
    FOR scope IN
        SELECT p_project AS id, CASE WHEN p_admin THEN 'admin' ELSE 'project' END AS kind,
            CASE WHEN p_admin THEN NULL ELSE policy->'request_quota' END AS quota
            FROM project_access_policies WHERE project_id=p_project
        UNION ALL SELECT slot_id, 'slot', policy->'request_quota' FROM slot_access_policies
            WHERE slot_id=p_slot AND NOT p_admin
        ORDER BY kind,id
    LOOP
        quota := scope.quota;
        FOREACH period_name IN ARRAY ARRAY['day','month'] LOOP
            period_begin := date_trunc(period_name, now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC';
            period_end := ((period_begin AT TIME ZONE 'UTC') + CASE WHEN period_name='day' THEN interval '1 day' ELSE interval '1 month' END) AT TIME ZONE 'UTC';
            INSERT INTO access_quota_usage(project_id,scope_id,scope_type,period,period_start)
                VALUES(p_project,scope.id,scope.kind,period_name,period_begin) ON CONFLICT DO NOTHING;
            SELECT admitted INTO current_count FROM access_quota_usage
                WHERE project_id=p_project AND scope_id=scope.id AND scope_type=scope.kind
                    AND period=period_name AND period_start=period_begin FOR UPDATE;
            IF quota->>'period'=period_name AND current_count >= (quota->>'limit')::bigint THEN
                wait_seconds := greatest(wait_seconds, ceil(extract(epoch FROM period_end-now()))::bigint);
            END IF;
        END LOOP;
    END LOOP;
    IF wait_seconds > 0 THEN RETURN wait_seconds; END IF;
    UPDATE access_quota_usage SET admitted=admitted+1 WHERE project_id=p_project
        AND ((p_admin AND scope_type='admin' AND scope_id=p_project)
            OR (NOT p_admin AND ((scope_type='project' AND scope_id=p_project) OR (scope_type='slot' AND scope_id=p_slot))))
        AND period_start = date_trunc(period, now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC';
    RETURN 0;
END;
$$;
REVOKE ALL ON FUNCTION consume_access_quota(uuid,uuid,boolean) FROM PUBLIC;

ALTER TABLE studio_step_up_grant_consumptions
    DROP CONSTRAINT studio_step_up_grant_consumptions_action_check;
ALTER TABLE studio_step_up_grant_consumptions
    ADD CONSTRAINT studio_step_up_grant_consumptions_action_check CHECK (action IN (
        'delete_project', 'reveal_secret_key', 'create_secret_key', 'rotate_secret_key',
        'activate_secret_key', 'update_secret_key_policy', 'cancel_secret_key_rotation',
        'revoke_secret_key', 'update_access_policy'
    ));

CREATE FUNCTION remove_slot_access_usage() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_catalog AS $$
BEGIN
    DELETE FROM access_quota_usage WHERE project_id=OLD.project_id
        AND scope_type='slot' AND scope_id=OLD.id;
    RETURN OLD;
END;
$$;
REVOKE ALL ON FUNCTION remove_slot_access_usage() FROM PUBLIC;
CREATE TRIGGER remove_slot_access_usage AFTER DELETE ON project_api_key_slots
FOR EACH ROW EXECUTE FUNCTION remove_slot_access_usage();
