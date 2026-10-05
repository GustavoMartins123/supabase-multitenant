from __future__ import annotations

import ast
import asyncio
from pathlib import Path
import re
import sys
import time
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'servidor/host-agent'))
from hostagent import commands
from hostagent.commands import RunningCommandState, CommandContext, _apply_progress_events, run_process


class LifecycleProgressContractTests(unittest.TestCase):
    def test_all_script_handlers_connect_their_progress_contract(self):
        pairs = {
            'handle_create_project': 'CREATE_PROGRESS_EVENTS',
            'handle_duplicate_project': 'DUPLICATE_PROGRESS_EVENTS',
            'handle_rotate_keys': 'ROTATE_PROGRESS_EVENTS',
            'handle_rename_project': 'REFERENCE_PROGRESS_EVENTS',
            'handle_backup_project': 'BACKUP_PROGRESS_EVENTS',
            'handle_restore_project': 'RESTORE_PROGRESS_EVENTS',
            'handle_delete_project_files': 'DELETE_FILES_PROGRESS_EVENTS',
            'handle_delete_project_storage': 'DELETE_STORAGE_PROGRESS_EVENTS',
        }
        tree = ast.parse((ROOT / 'servidor/host-agent/hostagent/commands.py').read_text(encoding='utf-8'))
        for node in tree.body:
            if isinstance(node, ast.AsyncFunctionDef) and node.name in pairs:
                keyword = next(k for call in ast.walk(node) if isinstance(call, ast.Call)
                               for k in call.keywords if k.arg == 'progress_events')
                self.assertEqual(keyword.value.id, pairs.pop(node.name))
        self.assertFalse(pairs)

    def test_each_event_has_a_real_emitter(self):
        sources = '\n'.join(p.read_text(encoding='utf-8') for p in (ROOT / 'servidor/generateProject').rglob('*')
                            if p.suffix in {'.sh', '.py'})
        for name in ('CREATE', 'DUPLICATE', 'ROTATE', 'REFERENCE', 'RESTORE', 'DELETE_FILES', 'DELETE_STORAGE'):
            for marker, (progress, step, message) in getattr(commands, name + '_PROGRESS_EVENTS').items():
                if marker.startswith('HOST_AGENT_PROGRESS=backup:'):
                    self.assertIn('backup_progress ' + marker.split(':')[1], sources)
                else:
                    self.assertIn(marker, sources)
                self.assertTrue(0 < progress < 100 and step and message, marker)

    def test_events_follow_output_order_not_dictionary_order(self):
        state = RunningCommandState()
        events = commands.CREATE_PROGRESS_EVENTS
        _apply_progress_events('\n'.join(('HOST_AGENT_PROGRESS=create:database_created',
                                         'HOST_AGENT_PROGRESS=create:storage_credentials_created',
                                         'HOST_AGENT_PROGRESS=create:files_rendered')), state, events, set())
        self.assertEqual((state.progress, state.current_step), (72, 'render_project_files'))

    def test_embedded_log_text_does_not_change_phase_and_regression_is_rejected(self):
        state = RunningCommandState()
        events = commands.DUPLICATE_PROGRESS_EVENTS
        _apply_progress_events('NOTICE: HOST_AGENT_PROGRESS=duplicate:start_services', state, events, set())
        self.assertEqual(state.progress, 0)
        seen = set()
        _apply_progress_events('HOST_AGENT_PROGRESS=duplicate:start_services', state, events, seen)
        with self.assertRaisesRegex(ValueError, 'regressed'):
            _apply_progress_events('HOST_AGENT_PROGRESS=duplicate:export_database', state, events, seen)


@unittest.skipIf(sys.platform == 'win32', 'real POSIX subprocess required')
class LifecycleProgressStreamTests(unittest.IsolatedAsyncioTestCase):
    async def test_fragmented_markers_and_large_logs_preserve_live_phase(self):
        state = RunningCommandState()
        ctx = CommandContext(SimpleNamespace(), state, 10, 'duplicate_project')
        child = """import sys,time
sys.stderr.write('HOST_AGENT_PROGRESS=duplicate:start_services\\n');sys.stderr.flush()
sys.stdout.write('x'*90000+'HOST_AGENT_PROGRESS=duplicate:start_services\\n');sys.stdout.flush()
sys.stdout.write('HOST_AGENT_PROGRESS=duplicate:export_');sys.stdout.flush();time.sleep(.15)
sys.stdout.write('database\\n');sys.stdout.flush();time.sleep(.3)
sys.stdout.write('HOST_AGENT_PROGRESS=duplicate:copy_storage\\n');sys.stdout.flush();time.sleep(.3)
"""
        task = asyncio.create_task(run_process([sys.executable, '-u', '-c', child], ctx,
                                               progress_events=commands.DUPLICATE_PROGRESS_EVENTS))
        await asyncio.wait_for(state.progress_changed.wait(), 3)
        self.assertEqual((state.progress, state.current_step), (25, 'export_database'))
        self.assertFalse(task.done())
        result = await task
        self.assertEqual(result.returncode, 0)
        self.assertEqual((state.progress, state.current_step), (35, 'copy_storage'))

    async def test_percentage_never_reaches_100_for_a_failed_script(self):
        state = RunningCommandState()
        ctx = CommandContext(SimpleNamespace(), state, 10, 'duplicate_project')
        result = await run_process([sys.executable, '-c',
                                   "print('HOST_AGENT_PROGRESS=duplicate:restore_database');raise SystemExit(4)"],
                                  ctx, progress_events=commands.DUPLICATE_PROGRESS_EVENTS)
        self.assertEqual(result.returncode, 4)
        self.assertEqual((state.progress, state.current_step), (40, 'restore_database'))


class JobProgressSpanTests(unittest.IsolatedAsyncioTestCase):
    def mirror(self):
        tree = ast.parse((ROOT / 'servidor/api-internal/app/project_backgrounds.py').read_text(encoding='utf-8'))
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_job_progress_mirror')
        namespace = {'_set_job_status': AsyncMock()}
        exec(compile(ast.Module(body=[function], type_ignores=[]), '<progress-mirror>', 'exec'), namespace)
        return namespace

    async def test_host_progress_reserves_room_for_control_plane_finalization(self):
        namespace = self.mirror()
        mirror = namespace['_job_progress_mirror']('job', start_progress=5, end_progress=70)
        for progress in (10, 25, 50, 80, 98):
            await mirror({'progress': progress, 'current_step': str(progress), 'message': 'active phase'})
        values = [call.kwargs['progress'] for call in namespace['_set_job_status'].await_args_list]
        self.assertEqual(values, sorted(values))
        self.assertLess(values[-1], 70)

    async def test_invalid_progress_and_persistence_failure_are_explicit(self):
        namespace = self.mirror()
        mirror = namespace['_job_progress_mirror']('job', start_progress=5, end_progress=70)
        with self.assertRaises(ValueError):
            await mirror({'progress': 101, 'current_step': 'invalid', 'message': 'invalid'})
        namespace['_set_job_status'].side_effect = RuntimeError('database unavailable')
        with self.assertRaisesRegex(RuntimeError, 'database unavailable'):
            await mirror({'progress': 25, 'current_step': 'export_database', 'message': 'export'})


class TerminalProgressTests(unittest.IsolatedAsyncioTestCase):
    def load_function(self, name, namespace):
        tree = ast.parse((ROOT / 'servidor/api-internal/app/host_agent.py').read_text(encoding='utf-8'))
        function = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == name)
        future = ast.parse('from __future__ import annotations').body[0]
        exec(compile(ast.Module(body=[future, function], type_ignores=[]), '<host-agent-wait>', 'exec'), namespace)
        return namespace[name]

    async def test_failed_and_cancelled_commands_mirror_the_final_phase(self):
        for status in ('failed', 'cancelled'):
            with self.subTest(status=status):
                row = {'status': status, 'progress': 40, 'current_step': 'restore_database',
                       'message': 'Database restore failed'}
                pool = SimpleNamespace(fetchrow=AsyncMock(return_value=row))
                mirror_namespace = JobProgressSpanTests().mirror()
                callback = mirror_namespace['_job_progress_mirror']('job', start_progress=5, end_progress=70)
                wait = self.load_function('wait_command', {})
                self.assertIs(await wait(pool, 'command', on_progress=callback), row)
                args = mirror_namespace['_set_job_status'].await_args.kwargs
                self.assertEqual((args['progress'], args['current_step']), (31, 'restore_database'))

    async def test_done_does_not_complete_the_job_before_api_finalization(self):
        row = {'status': 'done', 'progress': 100, 'current_step': 'completed'}
        pool = SimpleNamespace(fetchrow=AsyncMock(return_value=row))
        callback = AsyncMock()
        wait = self.load_function('wait_command', {})
        self.assertIs(await wait(pool, 'command', on_progress=callback), row)
        callback.assert_not_awaited()

    async def test_failure_after_last_heartbeat_delivers_newer_phase(self):
        running = {'status': 'running', 'progress': 25, 'current_step': 'export_database',
                   'message': 'Exporting', 'timeout_seconds': 10}
        failed = {**running, 'status': 'failed', 'progress': 40,
                  'current_step': 'restore_database', 'message': 'Restore failed'}
        pool = SimpleNamespace(fetchrow=AsyncMock(side_effect=[running, failed]),
                               fetchval=AsyncMock(return_value=None))
        callback = AsyncMock()
        wait = self.load_function('wait_command', {'asyncio': asyncio, 'time': time,
                                                  'WAIT_EXTRA_MARGIN_SECONDS': 1,
                                                  'LEASE_EXPIRED_GRACE_SECONDS': 1})
        await wait(pool, 'command', on_progress=callback, poll_interval=0)
        self.assertEqual([call.args[0]['current_step'] for call in callback.await_args_list],
                         ['export_database', 'restore_database'])

    async def test_terminal_progress_persistence_failure_is_not_suppressed(self):
        pool = SimpleNamespace(fetchrow=AsyncMock(return_value={'status': 'failed'}))
        callback = AsyncMock(side_effect=RuntimeError('database unavailable'))
        wait = self.load_function('wait_command', {})
        with self.assertRaisesRegex(RuntimeError, 'database unavailable'):
            await wait(pool, 'command', on_progress=callback)

    async def test_reused_terminal_command_goes_through_the_same_progress_path(self):
        pool = SimpleNamespace()
        callback = AsyncMock()
        existing = {'id': 'existing-command', 'status': 'failed'}
        namespace = {'find_command_for_job': AsyncMock(return_value=existing),
                     'wait_command': AsyncMock(return_value=existing)}
        run = self.load_function('run_command_for_job', namespace)
        self.assertIs(await run(pool, job_id='job', command='rename_project', project='project',
                                project_uuid=None, requested_by=None, reuse_terminal=True,
                                on_progress=callback), existing)
        namespace['wait_command'].assert_awaited_once_with(pool, 'existing-command', on_progress=callback)


if __name__ == '__main__':
    unittest.main()
