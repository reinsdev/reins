import unittest

from tests import CLI_LIB  # noqa: F401
from tests.support_t2 import commit, java_repo, mdparse_ready
from spec_driven import gitutil, taskstate
from spec_driven.project import Project

TASKS = """# Tasks: demo

## Foundation
- [ ] T1. 建表
- [x] T2. 状态机事件
- [~] T3. 延期
- [ ] T-regression. 回归测试
- [ ] 不是任务的条目

```
- [ ] T9. 代码块里的不算
```
"""


class RedTest(unittest.TestCase):
    def test_is_red(self):
        c = lambda s, t=None: {"subject": s, "trailers": t or {}}  # noqa: E731
        self.assertTrue(taskstate.is_red(c("RED: add test")))
        self.assertTrue(taskstate.is_red(c("x", {"TDD-Phase": ["red"]})))
        self.assertFalse(taskstate.is_red(c("Reduce noise")))
        self.assertFalse(taskstate.is_red(c("green")))


class DoneTest(unittest.TestCase):
    def test_done_from_non_red_commits(self):
        with java_repo() as root:
            base = gitutil.head(root)
            commit(root, "RED: t\n\nTask-Id: T1\nTDD-Phase: RED")
            h2 = commit(root, "impl\n\nTask-Id: T2")
            h3 = commit(root, "impl\n\nTask-Id: T-regression, T4")
            done = taskstate.done_tasks(Project(root), {"baseCommit": base})
            self.assertEqual(done, {"T2": [h2], "T-regression": [h3], "T4": [h3]})


@unittest.skipUnless(mdparse_ready(), "needs T1 mdparse.checkboxes")
class RenderTest(unittest.TestCase):
    def test_render_and_open(self):
        done = {"T1": ["h"]}
        out = taskstate.render(TASKS, done)
        self.assertIn("- [x] T1. 建表", out)
        self.assertIn("- [ ] T2. 状态机事件", out)       # ticked by hand, no commit: unticked
        self.assertIn("- [~] T3. 延期", out)
        self.assertIn("- [ ] T9. 代码块里的不算", out)
        self.assertEqual(taskstate.open_tasks(TASKS, done), ["T2", "T-regression"])
        self.assertEqual(len(out.splitlines()), len(TASKS.splitlines()))


if __name__ == "__main__":
    unittest.main()
