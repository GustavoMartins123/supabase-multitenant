import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("openapi_to_30", ROOT / "tools/openapi_to_30.py")
converter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(converter)


class OpenApiConversionTests(unittest.TestCase):
    def test_nullable_branch_preserves_constraints_and_metadata(self):
        value = {
            "anyOf": [{"type": "string", "maxLength": 20}, {"type": "null"}],
            "title": "Reference",
            "default": None,
        }
        self.assertEqual(
            converter._convert(value),
            {
                "type": "string",
                "maxLength": 20,
                "nullable": True,
                "title": "Reference",
                "default": None,
            },
        )
        self.assertIn("anyOf", value)

    def test_null_only_has_no_invalid_openapi_30_null_type(self):
        self.assertEqual(
            converter._convert({"type": "null", "default": None}),
            {"type": "object", "nullable": True, "enum": [None], "default": None},
        )

    def test_nonnullable_union_is_not_narrowed(self):
        value = {"anyOf": [{"type": "string"}, {"type": "integer"}]}
        self.assertEqual(converter._convert(value), value)


if __name__ == "__main__":
    unittest.main()
