"""Contracts complement (never replace) the mandatory real container drill."""
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / 'tests/integration/fixtures'
sys.path.insert(0, str(FIXTURES))
try:
    spec = importlib.util.spec_from_file_location('p1_measurement_contract', FIXTURES / 'p1_benchmark.py')
    benchmark = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(benchmark)
finally:
    sys.path.remove(str(FIXTURES))


class P1EndToEndContractTest(unittest.TestCase):
    def test_fernet_refreshes_wall_clock_without_skew_tolerance(self):
        source = (ROOT / 'studio/nginx/lua/resty/fernet.lua').read_text(encoding='utf-8')
        self.assertIn('ngx.update_time()', source)
        self.assertIn('return ngx.time()', source)
        self.assertNotIn('return os.time()', source)
        self.assertIn('if time_diff < 0 then', source)

    def test_nearest_rank_and_closed_loop_throughput(self):
        measured = [{'status': 200, 'milliseconds': n} for n in range(1, 101)]
        result = benchmark.summarize(measured, 2000)
        self.assertEqual(result['latency_ms'], {'p50': 50, 'p95': 95, 'p99': 99})
        self.assertEqual(result['requests_per_second'], 50)
        self.assertEqual(result['errors'], 0)

    def test_denials_are_errors_not_dropped_samples(self):
        result = benchmark.summarize([{'status': 403, 'milliseconds': 1},
                                      {'status': 503, 'milliseconds': 2}], 10)
        self.assertEqual(result['requests'], 2)
        self.assertEqual(result['errors'], 2)
        self.assertEqual(result['statuses'], {'403': 1, '503': 1})

    def test_invalid_measurement_fails_explicitly(self):
        for measured, elapsed in [([], 1), ([{'status': 200, 'milliseconds': -1}], 1),
                                   ([{'status': 200, 'milliseconds': float('nan')}], 1),
                                   ([{'status': 200, 'milliseconds': 1}], 0),
                                   ([{'status': 200, 'milliseconds': 1}], float('inf'))]:
            with self.assertRaises(ValueError):
                benchmark.summarize(measured, elapsed)

    def test_benchmark_is_after_delete_outage_and_tenant_acceptance(self):
        source = (FIXTURES / 'p1_end_to_end.py').read_text(encoding='utf-8')
        self.assertLess(source.index("print('PASS step-up protected full API/agent delete"),
                        source.index('from p1_benchmark import measure'))
        self.assertIn("expect('owner', 'GET', restored_rest, 503)", source)
        self.assertIn("external_request(beta, external['api_key'], 403)", source)
        self.assertIn("'replication-slot-scope'", source)

    def test_browser_no_certificate_bypass_and_bounded_load(self):
        source = (FIXTURES / 'p1_browser_driver.py').read_text(encoding='utf-8')
        self.assertNotIn('ignore_https_errors', source)
        self.assertNotIn('ignore-certificate-errors', source)
        self.assertIn('samples>1000', source)
        self.assertIn('concurrency>16', source)
        self.assertIn('AbortSignal.timeout(30000)', source)

    def test_replication_cleanup_null_and_cross_database_fail_closed(self):
        source = (ROOT / 'servidor/api-internal/app/migrations/0011_project_replication_slot_cleanup.sql').read_text(encoding='utf-8')
        self.assertIn('project_ref IS NULL OR slot IS NULL', source)
        self.assertIn('SECURITY DEFINER SET search_path = pg_catalog', source)
        self.assertIn("target_database IS DISTINCT FROM '_supabase_' || project_ref", source)
        self.assertIn('FROM PUBLIC', source)


if __name__ == '__main__':
    unittest.main()
