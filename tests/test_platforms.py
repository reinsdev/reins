import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests import CLI_LIB  # noqa: F401
from reinsdev import platforms


class FindCliTest(unittest.TestCase):
    def test_falls_back_to_installer_dir_outside_path(self):
        with tempfile.TemporaryDirectory() as home:
            name = "opencode.exe" if os.name == "nt" else "opencode"
            exe = Path(home) / ".opencode" / "bin" / name
            exe.parent.mkdir(parents=True)
            exe.write_text("")
            exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
            env = {"PATH": "", "HOME": home, "USERPROFILE": home}
            with mock.patch.dict(os.environ, env):
                self.assertEqual(Path(platforms.find_cli("opencode")), exe)
                self.assertIsNone(platforms.find_cli("no-such-cli"))


if __name__ == "__main__":
    unittest.main()
