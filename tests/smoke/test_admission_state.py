import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import AsyncMock
import uuid

ROOT = Path(__file__).resolve().parents[2]
for name, path in (
    ("access_policy", ROOT / "servidor/api-internal/app/access_policy.py"),
    ("access_admission", ROOT / "servidor/key-authorizer/admission.py"),
):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
AdmissionEngine = module.AdmissionEngine


class Context:
    def __init__(self, value):
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, *args):
        pass


class AdmissionEpochTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engines = []

    async def asyncTearDown(self):
        for engine in self.engines:
            await engine.http.aclose()

    def engine(self, initialized, stored, size):
        epoch = uuid.uuid4()
        connection = AsyncMock()
        connection.fetchrow.return_value = {"epoch": epoch, "initialized": initialized}
        connection.transaction = lambda: Context(connection)
        pool = type("Pool", (), {"acquire": lambda _: Context(connection)})()
        redis = AsyncMock()
        redis.get.return_value = str(epoch) if stored == "matching" else stored
        redis.dbsize.return_value = size
        engine = AdmissionEngine(pool, redis, "192.0.2.10/32")
        self.engines.append(engine)
        return engine, connection, redis, epoch

    async def test_first_initialization_requires_empty_database(self):
        engine, connection, redis, _ = self.engine(False, None, 1)
        with self.assertRaisesRegex(RuntimeError, "empty Redis"):
            await engine.startup()
        redis.set.assert_not_awaited()
        self.assertEqual(connection.execute.await_count, 1)

    async def test_explicit_empty_database_initializes_epoch(self):
        engine, connection, redis, epoch = self.engine(False, None, 0)
        await engine.startup()
        redis.set.assert_awaited_once_with("access:epoch", str(epoch), nx=True)
        connection.execute.assert_awaited_with("SELECT initialize_access_rate_epoch()")

    async def test_lost_initialized_epoch_never_replenishes(self):
        engine, _, redis, _ = self.engine(True, None, 0)
        with self.assertRaisesRegex(RuntimeError, "explicit maintenance"):
            await engine.startup()
        redis.set.assert_not_awaited()

    async def test_intact_epoch_is_read_only(self):
        engine, connection, redis, _ = self.engine(True, "matching", 3)
        await engine.startup()
        redis.set.assert_not_awaited()
        self.assertEqual(connection.execute.await_count, 1)


if __name__ == "__main__":
    unittest.main()
