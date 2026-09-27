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
