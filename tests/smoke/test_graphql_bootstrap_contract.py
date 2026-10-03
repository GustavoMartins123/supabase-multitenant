"""Canonical PostgREST/GraphQL bootstrap, complemented by the real P1 drill."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]


class GraphqlBootstrapTest(unittest.TestCase):
    def test_new_project_exposes_graphql_wrapper_schema(self):
        template = (ROOT / 'servidor/generateProject/.envtemplate').read_text(encoding='utf-8')
        self.assertIn('PGRST_DB_SCHEMAS=public,graphql_public\n', template)

    def test_dumped_template_reestablishes_extension_acl_before_sealing(self):
        script = (ROOT / 'servidor/volumes/db/create_template.sh').read_text(encoding='utf-8')
        self.assertLess(script.index('-f /etc/supabase/graphql.sql'), script.index('ALTER DATABASE _supabase_template WITH is_template = true;'))
        contract = (ROOT / 'servidor/volumes/db/graphql.sql').read_text(encoding='utf-8')
        self.assertIn('CREATE EXTENSION IF NOT EXISTS pg_graphql;', contract)
        self.assertIn('GRANT USAGE ON SCHEMA graphql, graphql_public TO anon, authenticated, service_role;', contract)
        self.assertIn('REVOKE EXECUTE ON FUNCTION graphql_public.graphql(text,text,jsonb,jsonb) FROM PUBLIC;', contract)
        for action in ('duplicate', 'restore'):
            lifecycle = (ROOT / f'servidor/generateProject/lib/{action}_project_impl.sh').read_text(encoding='utf-8')
            self.assertIn('< "$PROJECT_ROOT/volumes/db/graphql.sql"', lifecycle)


if __name__ == '__main__':
    unittest.main()
