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
        grant = script.index('GRANT USAGE ON SCHEMA graphql, graphql_public TO anon, authenticated, service_role;')
        self.assertLess(script.index('CREATE EXTENSION IF NOT EXISTS pg_graphql;'), grant)
        self.assertLess(grant, script.index('ALTER DATABASE _supabase_template WITH is_template = true;'))
        self.assertIn('GRANT EXECUTE ON FUNCTION graphql_public.graphql(text, text, jsonb, jsonb)', script)


if __name__ == '__main__':
    unittest.main()
