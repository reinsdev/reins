"""T14 regressions for independent CLI processes sharing disk state."""

import contextlib
import io
import json
import multiprocessing
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from tests import CLI_LIB  # noqa: F401
from spec_driven import gitutil, hook, meta, retro
from spec_driven.cli import main
from spec_driven.commands import githook
from spec_driven.policies import gate_router
from spec_driven.project import Project


def invoke(*args):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = main(list(args))
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else 1
            if not isinstance(exc.code, int):
                err.write(str(exc.code))
    return code, out.getvalue(), err.getvalue()


class ProjectTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve() / 'project'
        self.root.mkdir()
        env = mock.patch.dict(os.environ, {'REINS_HOME': str(Path(self.tmp.name) / 'home')})
        env.start()
        self.addCleanup(env.stop)
        old = Path.cwd()
        os.chdir(str(self.root))
        self.addCleanup(os.chdir, str(old))
        self.git('init', '-q')
        self.git('config', 'user.name', 'T14 tester')
        self.git('config', 'user.email', 't14@example.invalid')
        self.git('config', 'core.autocrlf', 'false')
        (self.root / 'pom.xml').write_text('<project/>\n', encoding='utf-8')
        self.git('add', 'pom.xml')
        self.git('commit', '-qm', 'initial')
        self.project = Project(self.root)

    def git(self, *args):
        return gitutil.git(list(args), self.root)

    def change(self, name='first-change', phase='0', branch=None):
        directory = self.project.change_dir(name)
        directory.mkdir(parents=True)
        data = meta.new(name, 'feature', branch or gitutil.current_branch(self.root), gitutil.head(self.root))
        data['phase'] = phase
        with meta.lock(directory):
            meta.save(directory, data)
        return directory


class WorkspaceTest(ProjectTest):
    def test_new_rejects_untracked_staged_and_unstaged_changes(self):
        original = gitutil.current_branch(self.root)
        for mode in ('untracked', 'staged', 'unstaged'):
            with self.subTest(mode=mode):
                path = self.root / ('scratch.txt' if mode != 'unstaged' else 'pom.xml')
                path.write_text('user work %s\n' % mode, encoding='utf-8')
                if mode == 'staged':
                    self.git('add', 'scratch.txt')
                code, out, err = invoke('new', 'dirty-' + mode)
                self.assertNotEqual(code, 0)
                self.assertIn('worktree', out + err)
                self.assertIn('--no-branch', out + err)
                self.assertEqual(gitutil.current_branch(self.root), original)
                self.assertFalse(self.project.change_dir('dirty-' + mode).exists())
                self.assertEqual(path.read_text(encoding='utf-8'), 'user work %s\n' % mode)
                self.git('add', '-A')
                self.git('commit', '-qm', 'save work')

    def test_new_no_branch_preserves_dirty_work(self):
        original = gitutil.current_branch(self.root)
        (self.root / 'scratch.txt').write_text('user work', encoding='utf-8')
        self.assertEqual(invoke('new', 'safe-change', '--no-branch')[0], 0)
        self.assertEqual(gitutil.current_branch(self.root), original)
        self.assertEqual((self.root / 'scratch.txt').read_text(encoding='utf-8'), 'user work')

    def test_clean_new_switches_branch(self):
        self.assertEqual(invoke('new', 'clean-change')[0], 0)
        self.assertEqual(gitutil.current_branch(self.root), 'feat/clean-change')

    def test_router_stays_silent_for_multiple_changes_even_on_matching_branch(self):
        self.change()
        self.change('second-change', branch='another-branch')
        note = gate_router.prompt({'cwd': str(self.root), 'prompt': '继续'})
        self.assertIsNone(note)

    def test_router_keeps_single_change_hint(self):
        self.change()
        note = gate_router.prompt({'cwd': str(self.root), 'prompt': '继续'})
        self.assertIn('first-change', note)

    def test_status_explicit_change_limits_results(self):
        self.change()
        self.change('second-change')
        code, out, err = invoke('status', '--change', 'first-change', '--json')
        self.assertEqual(code, 0, err)
        self.assertEqual([c['change'] for c in json.loads(out)['changes']], ['first-change'])


def hold_lock(directory, ready, release):
    with meta.lock(Path(directory)):
        ready.set()
        if not release.wait(10):
            raise RuntimeError('lock release was not signaled')


class LockTest(unittest.TestCase):
    def test_expired_holder_does_not_remove_successors_lock(self):
        ctx = multiprocessing.get_context('spawn')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / meta.LOCK_FILE
            first = meta.lock(Path(directory))
            first.__enter__()
            token = path.read_text(encoding='utf-8')
            old = time.time() - meta.LOCK_STALE - 1
            os.utime(str(path), (old, old))
            ready, release = ctx.Event(), ctx.Event()
            child = ctx.Process(target=hold_lock, args=(directory, ready, release))
            child.start()
            try:
                self.assertTrue(ready.wait(10))
                successor = path.read_text(encoding='utf-8')
                self.assertNotEqual(token, successor)
                first.__exit__(None, None, None)
                self.assertTrue(path.exists(), 'the expired owner deleted the new lock')
                self.assertEqual(path.read_text(encoding='utf-8'), successor)
            finally:
                first.__exit__(None, None, None)
                release.set()
                child.join(10)
                if child.is_alive():
                    child.terminate()
                    child.join()
            self.assertEqual(child.exitcode, 0)
            self.assertFalse(path.exists())

    def test_same_process_lock_replacement_has_unique_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / meta.LOCK_FILE
            first = meta.lock(Path(directory))
            first.__enter__()
            original = path.read_text(encoding='utf-8')
            old = time.time() - meta.LOCK_STALE - 1
            os.utime(str(path), (old, old))
            with meta.lock(Path(directory)):
                successor = path.read_text(encoding='utf-8')
                first.__exit__(None, None, None)
                self.assertNotEqual(original, successor)
                self.assertTrue(path.exists())
            self.assertFalse(path.exists())


def append_todos(directory, start, worker):
    if not start.wait(10):
        raise RuntimeError('workers were not started')
    for item in range(15):
        retro.add_todo(Path(directory), 'concurrent', '%s-%s' % (worker, item))


class RetroConcurrencyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name) / 'change'
        self.directory.mkdir()
        env = mock.patch.dict(os.environ, {'REINS_HOME': str(Path(self.tmp.name) / 'home')})
        env.start()
        self.addCleanup(env.stop)

    def test_failed_replace_keeps_previous_complete_document(self):
        retro.add_todo(self.directory, 'test', 'original')
        before = (self.directory / 'retrospective.md').read_bytes()
        with mock.patch('os.replace', side_effect=OSError('injected replace failure')):
            with self.assertRaises(OSError):
                retro.add_todo(self.directory, 'test', 'next')
        self.assertEqual((self.directory / 'retrospective.md').read_bytes(), before)
        self.assertTrue(retro.verify(self.directory))
        self.assertEqual(sorted(p.name for p in self.directory.iterdir()), ['.retro.sha256', 'retrospective.md'])

    def test_each_atomic_write_has_its_own_temporary_path(self):
        sources = []
        replace = os.replace

        def observe(source, destination):
            sources.append(Path(source))
            self.assertEqual(Path(source).parent, Path(destination).parent)
            self.assertNotEqual(Path(source), Path(destination))
            replace(source, destination)

        with mock.patch('os.replace', side_effect=observe):
            retro.add_todo(self.directory, 'test', 'first')
            retro.add_todo(self.directory, 'test', 'second')
        self.assertEqual(len(sources), 4)
        self.assertEqual(len(set(sources)), 4)
        self.assertTrue(retro.verify(self.directory))

    def test_verify_reloads_document_and_signature_after_mismatch(self):
        retro.add_todo(self.directory, 'test', 'old')
        document = self.directory / 'retrospective.md'
        document.write_text('intermediate\n', encoding='utf-8')

        def finish_write(_):
            document.write_text('complete\n', encoding='utf-8')
            (self.directory / retro.SIG_FILE).write_text(retro.signature('complete\n'), encoding='utf-8')

        with mock.patch('time.sleep', side_effect=finish_write):
            self.assertTrue(retro.verify(self.directory))

    def test_verify_retries_signature_without_replacing_explicit_staged_text(self):
        retro.add_todo(self.directory, 'test', 'old')
        document = self.directory / 'retrospective.md'
        document.write_text('staged\n', encoding='utf-8')

        def finish_signature(_):
            (self.directory / retro.SIG_FILE).write_text(retro.signature('staged\n'), encoding='utf-8')

        with mock.patch('time.sleep', side_effect=finish_signature):
            self.assertTrue(retro.verify(self.directory, 'staged\n'))
            self.assertFalse(retro.verify(self.directory, 'forged\n'))

    def test_spawn_append_preserves_all_rows_and_signature(self):
        ctx = multiprocessing.get_context('spawn')
        start = ctx.Event()
        children = [ctx.Process(target=append_todos, args=(str(self.directory), start, n)) for n in range(4)]
        for child in children:
            child.start()
        start.set()
        try:
            for child in children:
                child.join(15)
                self.assertEqual(child.exitcode, 0)
        finally:
            for child in children:
                if child.is_alive():
                    child.terminate()
                    child.join()
        self.assertEqual(set(retro.todos(self.directory)), {'%s-%s' % (w, i) for w in range(4) for i in range(15)})
        self.assertEqual(len(retro.todos(self.directory)), 60)
        self.assertTrue(retro.verify(self.directory))


def record_logs(home, start, worker):
    os.environ['REINS_HOME'] = home
    if not start.wait(10):
        raise RuntimeError('workers were not started')
    for item in range(30):
        hook._record({'worker': worker, 'item': item, 'prompt': 'private prompt', 'command': '中文' * 3000}, 'allow')


class LogTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        env = mock.patch.dict(os.environ, {'REINS_HOME': str(self.home)})
        env.start()
        self.addCleanup(env.stop)
        self.log = self.home / 'logs/hooks.jsonl'

    def test_record_is_one_unbuffered_append_without_prompt(self):
        calls = []
        write = os.write

        def observe(fd, data):
            calls.append(data)
            return write(fd, data)

        with mock.patch('os.write', side_effect=observe):
            hook._record({'prompt': 'private prompt', 'kind': 'shell'}, 'allow', ['broken policy'])
        self.assertEqual(len(calls), 1)
        record = json.loads(self.log.read_text(encoding='utf-8'))
        self.assertNotIn('prompt', record)
        self.assertEqual(record['verdict'], 'allow')
        self.assertEqual(record['policyErrors'], ['broken policy'])

    def test_spawn_writes_leave_complete_json_records(self):
        ctx = multiprocessing.get_context('spawn')
        start = ctx.Event()
        children = [ctx.Process(target=record_logs, args=(str(self.home), start, n)) for n in range(4)]
        for child in children:
            child.start()
        start.set()
        try:
            for child in children:
                child.join(15)
                self.assertEqual(child.exitcode, 0)
        finally:
            for child in children:
                if child.is_alive():
                    child.terminate()
                    child.join()
        records = [json.loads(line) for line in self.log.read_text(encoding='utf-8').splitlines()]
        self.assertEqual(len(records), 120)
        self.assertEqual({(r['worker'], r['item']) for r in records}, {(w, i) for w in range(4) for i in range(30)})
        self.assertTrue(all('prompt' not in r for r in records))

    def test_spawn_rotation_preserves_backup_and_concurrent_records(self):
        self.log.parent.mkdir()
        old = (json.dumps({'old': 'x' * (5 * 1024 * 1024)}) + '\n').encode('utf-8')
        self.log.write_bytes(old)
        ctx = multiprocessing.get_context('spawn')
        start = ctx.Event()
        children = [ctx.Process(target=record_logs, args=(str(self.home), start, n)) for n in range(4)]
        for child in children:
            child.start()
        start.set()
        try:
            for child in children:
                child.join(15)
                self.assertEqual(child.exitcode, 0)
        finally:
            for child in children:
                if child.is_alive():
                    child.terminate()
                    child.join()
        backup = self.log.with_name('hooks.jsonl.1').read_bytes()
        self.assertTrue(backup.startswith(old))
        records = [json.loads(line) for line in (backup[len(old):] + self.log.read_bytes()).splitlines()]
        self.assertEqual(len(records), 120)
        self.assertEqual({(r['worker'], r['item']) for r in records}, {(w, i) for w in range(4) for i in range(30)})

    def test_rotation_replaces_only_one_backup(self):
        self.log.parent.mkdir()
        old = b'x' * (5 * 1024 * 1024 + 1)
        self.log.write_bytes(old)
        backup = self.log.with_name('hooks.jsonl.1')
        backup.write_bytes(b'previous rotation')
        hook._record({'kind': 'shell'}, 'allow')
        self.assertEqual(backup.read_bytes(), old)
        self.assertEqual(json.loads(self.log.read_text(encoding='utf-8'))['verdict'], 'allow')
        self.assertEqual(sorted(p.name for p in self.log.parent.glob('hooks.jsonl*')), ['hooks.jsonl', 'hooks.jsonl.1'])

    def test_overlapping_rotation_keeps_the_large_backup(self):
        self.log.parent.mkdir()
        old = b'x' * (5 * 1024 * 1024 + 1) + b'\n'
        self.log.write_bytes(old)
        original_stat = Path.stat
        nested = []

        def interleave(path, *args, **kwargs):
            info = original_stat(path, *args, **kwargs)
            if path == self.log and not nested:
                nested.append(True)
                hook._record({'writer': 'second'}, 'allow')
            return info

        with mock.patch.object(Path, 'stat', interleave):
            hook._record({'writer': 'first'}, 'allow')
        backup = self.log.with_name('hooks.jsonl.1').read_bytes()
        self.assertTrue(backup.startswith(old))
        records = backup[len(old):] + self.log.read_bytes()
        self.assertEqual({json.loads(line)['writer'] for line in records.splitlines()}, {'first', 'second'})

    def test_rotation_failure_still_appends_and_does_not_block(self):
        self.log.parent.mkdir()
        old = b'x' * (5 * 1024 * 1024 + 1) + b'\n'
        self.log.write_bytes(old)
        with mock.patch('os.replace', side_effect=OSError('busy backup')):
            hook._record({'kind': 'shell'}, 'allow')
        data = self.log.read_bytes()
        self.assertTrue(data.startswith(old))
        self.assertEqual(json.loads(data[len(old):])['verdict'], 'allow')

    def test_log_io_failure_does_not_block(self):
        with mock.patch('os.open', side_effect=OSError('disk full')):
            self.assertIsNone(hook._record({'kind': 'shell'}, 'allow'))


class HookRefreshTest(ProjectTest):
    def install_old(self, existing=False):
        old = self.root / 'old-plugin/spec-driven'
        if existing:
            old.parent.mkdir()
            old.write_text('#!/bin/sh\nexit 0\n', encoding='utf-8')
        with mock.patch.object(githook, 'LAUNCHER', old):
            githook.install(self.root)
        return old

    def test_status_refreshes_missing_and_outdated_cli_preserving_foreign_hook(self):
        self.change()
        hooks = self.root / '.git/hooks'
        foreign = '#!/bin/sh\necho foreign\n'
        (hooks / 'pre-commit').write_text(foreign, encoding='utf-8')
        for exists in (False, True):
            with self.subTest(old_cli_exists=exists):
                old = self.install_old(exists)
                code, out, err = invoke('status', '--json')
                self.assertEqual(code, 0, err)
                self.assertEqual(json.loads(out)['changes'][0]['change'], 'first-change')
                for event in githook.EVENTS:
                    text = (hooks / event).read_text(encoding='utf-8')
                    self.assertIn(githook.LAUNCHER.as_posix(), text)
                    self.assertNotIn(old.as_posix(), text)
                self.assertEqual((hooks / 'pre-commit.reins-chained').read_text(encoding='utf-8'), foreign)

    def test_advance_refreshes_hook_even_when_gate_blocks(self):
        self.change()
        self.install_old()
        code, out, err = invoke('advance', '--change', 'first-change')
        self.assertEqual(code, 3, out + err)
        self.assertIn(githook.LAUNCHER.as_posix(), (self.root / '.git/hooks/pre-commit').read_text(encoding='utf-8'))

    def test_refresh_error_only_warns_and_keeps_command_result(self):
        self.change()
        self.install_old()
        with mock.patch.object(githook, 'install', side_effect=OSError('busy hooks')):
            code, out, err = invoke('status', '--json')
            self.assertEqual(code, 0)
            self.assertTrue(json.loads(out)['enabled'])
            self.assertIn('busy hooks', err)
            code, out, err = invoke('advance', '--change', 'first-change')
            self.assertEqual(code, 3)
            self.assertIn('busy hooks', err)

    def test_missing_launcher_warns_but_commit_succeeds(self):
        self.install_old()
        (self.root / 'code.txt').write_text('code', encoding='utf-8')
        self.git('add', 'code.txt')
        # Git's hook runner executes the installed shell script on every platform.
        self.git('commit', '-qm', 'commit without installed plugin')
        self.assertEqual(self.git('log', '-1', '--format=%s'), 'commit without installed plugin')


class TasksSyncCommitTest(ProjectTest):
    TASKS = '# Tasks\n\n- [ ] T1 Implement first task\n- [ ] T2 Implement second task\n'

    def setUp(self):
        super().setUp()
        self.directory = self.change(phase='4')
        self.tasks = self.directory / 'tasks.md'
        self.tasks.write_text(self.TASKS, encoding='utf-8')
        self.git('add', '.openspec')
        self.git('commit', '-qm', 'tasks approved')
        meta.update(self.directory, lambda data: data.update(phase='6'))
        (self.root / 'implementation.txt').write_text('first task', encoding='utf-8')
        self.git('add', 'implementation.txt')
        self.git('commit', '-qm', 'first task complete\n\nTask-Id: T1')
        githook.install(self.root)

    def stage_tasks(self, text):
        self.tasks.write_bytes(text.encode('utf-8'))
        self.git('add', self.tasks.relative_to(self.root).as_posix())

    def test_cli_tasks_sync_can_be_committed_in_phase_six(self):
        code, out, err = invoke('tasks-sync', '--change', 'first-change', '--apply')
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.tasks.read_text(encoding='utf-8'), self.TASKS.replace('[ ] T1', '[x] T1'))
        self.git('add', self.tasks.relative_to(self.root).as_posix())
        self.assertEqual(githook.pre_commit(self.project), [])
        self.git('commit', '-qm', 'sync completed task')
        self.assertEqual(self.git('log', '-1', '--format=%s'), 'sync completed task')

    def test_body_id_addition_deletion_and_false_checkmarks_stay_frozen(self):
        synced = self.TASKS.replace('[ ] T1', '[x] T1')
        changes = [synced.replace('first task', 'rewritten task'),
                   synced.replace('T1', 'T3'),
                   synced + '- [ ] T3 Extra task\n',
                   synced.replace('- [ ] T2 Implement second task\n', ''),
                   synced.replace('[ ] T2', '[x] T2')]
        for text in changes:
            with self.subTest(text=text):
                self.stage_tasks(text)
                self.assertIn('已冻结', '\n'.join(githook.pre_commit(self.project)))

    def test_unstaged_legitimate_text_cannot_hide_staged_body_edit(self):
        self.stage_tasks(self.TASKS.replace('first task', 'forged task'))
        self.tasks.write_text(self.TASKS.replace('[ ] T1', '[x] T1'), encoding='utf-8')
        self.assertIn('已冻结', '\n'.join(githook.pre_commit(self.project)))

    def test_red_commit_does_not_authorize_checkbox(self):
        (self.root / 'red-test.txt').write_text('failing test', encoding='utf-8')
        self.git('add', 'red-test.txt')
        self.git('commit', '-qm', 'failing second task\n\nTask-Id: T2\nTDD-Phase: RED')
        self.stage_tasks(self.TASKS.replace('[ ] T2', '[x] T2'))
        self.assertIn('已冻结', '\n'.join(githook.pre_commit(self.project)))

    def test_later_phase_keeps_tasks_frozen(self):
        meta.update(self.directory, lambda data: data.update(phase='7'))
        self.stage_tasks(self.TASKS.replace('[ ] T1', '[x] T1'))
        self.assertIn('已冻结', '\n'.join(githook.pre_commit(self.project)))
