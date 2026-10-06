import hashlib
import importlib.util
import io
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
SOURCE = '11111111-1111-4111-8111-111111111111'
DESTINATION = '22222222-2222-4222-8222-222222222222'
spec = importlib.util.spec_from_file_location('vector_rekey_sql', ROOT / 'servidor/generateProject/lib/vector_rekey_sql.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class VectorRekeySqlTest(unittest.TestCase):
    def test_empty_and_nonempty_csv_generate_complete_transaction(self):
        self.assertEqual(module.render(SOURCE, DESTINATION, io.StringIO('')), 'BEGIN;\nCOMMIT;\n')
        sql = module.render(SOURCE, DESTINATION, io.StringIO('bucket,index\n"b,ucket",index\n'))
        self.assertTrue(sql.startswith('BEGIN;\n'))
        self.assertTrue(sql.endswith('COMMIT;\n'))
        for tenant in (SOURCE, DESTINATION):
            digest = hashlib.sha256(b'pgvector__bucket\0' + f'{tenant}-index'.encode()).hexdigest()[:24]
            self.assertIn('vector_' + digest, sql)
        self.assertEqual(sql.count('DO $rekey$'), 2)

    def test_invalid_uuid_same_uuid_and_ambiguous_rows_fail_before_sql(self):
        for source, destination, csv in [('invalid', DESTINATION, ''), (SOURCE, SOURCE, ''),
                                         (SOURCE, DESTINATION, 'bucket\n'),
                                         (SOURCE, DESTINATION, 'bucket,\n')]:
            with self.subTest(source=source, csv=csv), self.assertRaises(ValueError):
                module.render(source, destination, io.StringIO(csv))

    def test_bash_invokes_file_not_shell_quoted_python_program(self):
        script = (ROOT / 'servidor/generateProject/lib/vector_lifecycle.sh').read_text(encoding='utf-8')
        body = script.split('vector_rekey_physical_tables() {', 1)[1].split('\n}\n', 1)[0]
        self.assertIn('python3 "$STORAGE_LIFECYCLE_DIR/vector_rekey_sql.py"', body)
        self.assertNotIn('python3 -c', body)


if __name__ == '__main__':
    unittest.main()
