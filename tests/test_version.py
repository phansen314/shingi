import json
import shutil
import subprocess
import unittest
from importlib.metadata import version


def shingi(*args):
    return subprocess.run([shutil.which("shingi"), *args], capture_output=True)


class VersionTest(unittest.TestCase):
    def test_reports_the_package_version(self):
        proc = shingi("version")
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stderr, b"")
        self.assertTrue(proc.stdout.endswith(b"\n"))
        self.assertEqual(proc.stdout.count(b"\n"), 1)
        self.assertEqual(
            json.loads(proc.stdout),
            {"ok": True, "result": {"version": version("shingi")}, "warnings": []},
        )

    def test_unknown_command_is_a_usage_error(self):
        proc = shingi("nope")
        self.assertEqual(proc.returncode, 2)
        envelope = json.loads(proc.stdout)
        self.assertFalse(envelope["ok"])
        self.assertEqual(envelope["error"]["kind"], "usage")
        self.assertEqual(envelope["error"]["details"]["problems"][0]["argument"], "nope")
        self.assertEqual(proc.stderr.count(b"\n"), 1)


if __name__ == "__main__":
    unittest.main()
