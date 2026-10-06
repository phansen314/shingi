import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

RULES = """\
schema = 1

[roots]
koan    = "/work"
working = "{working}"

[kind.group]
description = "Work gathered under one name."
suggests    = ["group", "branch"]

[kind.branch]
description = "Work on one branch of one repository."
"""


class CreateTest(unittest.TestCase):
    def setUp(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        self.working = tmp / "working"
        self.working.mkdir()
        self.config = tmp / "shingi.toml"
        self.config.write_text(RULES.format(working=self.working))
        self.env = {**os.environ, "XDG_CONFIG_HOME": str(tmp / "config")}
        subprocess.run(["koan", "init", str(tmp / "tree")], env=self.env, capture_output=True, check=True)

    def shingi(self, *args):
        proc = subprocess.run(
            [shutil.which("shingi"), *args, "--config", str(self.config)], env=self.env, capture_output=True
        )
        return proc.returncode, json.loads(proc.stdout)

    def koan_show(self, task_id):
        proc = subprocess.run(["koan", "show", str(task_id)], env=self.env, capture_output=True, check=True)
        return json.loads(proc.stdout)["result"]["tasks"][0]

    def test_creates_a_top_level_unit(self):
        status, out = self.shingi("create", "HOME-1", "group", "--title", "Payment retries")
        self.assertEqual(status, 0, out)
        unit = out["result"]["unit"]
        folder = self.working.resolve() / "HOME-1"

        manifest = json.loads((folder / "uow.json").read_text())
        self.assertEqual(manifest, {"schema": 1, "id": unit["id"], "kind": "group"})
        self.assertEqual((folder / "uow.md").read_text(), "# Payment retries\n")
        self.assertEqual(sorted(p.name for p in folder.iterdir()), ["uow.json", "uow.md"])

        self.assertEqual(unit["path"], "HOME-1")
        self.assertEqual(unit["kind"], "group")
        self.assertEqual(unit["title"], "Payment retries")
        self.assertEqual(unit["state"], "not-started")
        self.assertIsNone(unit["parent"])
        self.assertEqual(unit["children"], [])
        self.assertEqual(unit["koan_folder"], "/work/HOME-1")
        self.assertEqual(unit["working_folder"], str(folder))
        self.assertEqual(unit["notes_path"], str(folder / "uow.md"))
        self.assertEqual(unit["start"]["readiness"], "ready")
        self.assertEqual(unit["done"]["readiness"], "blocked")

        start, done = self.koan_show(unit["start"]["id"]), self.koan_show(unit["done"]["id"])
        self.assertEqual(start["title"], "Start: HOME-1")
        self.assertEqual(start["tags"], ["shingi", "shingi-start"])
        self.assertEqual(start["extra"], {"source": "shingi-start", "shingi-unit": unit["id"]})
        self.assertEqual(done["blocked_by"], [start["id"]])

    def test_title_defaults_to_the_name(self):
        status, out = self.shingi("create", "HOME-2", "group")
        self.assertEqual(status, 0, out)
        self.assertEqual(out["result"]["unit"]["title"], "HOME-2")

    def test_refuses_an_existing_unit(self):
        self.shingi("create", "HOME-1", "group")
        status, out = self.shingi("create", "HOME-1", "group")
        self.assertEqual(status, 1)
        self.assertEqual(out["error"]["kind"], "unit-exists")

    def test_refuses_an_unknown_kind(self):
        status, out = self.shingi("create", "HOME-1", "story")
        self.assertEqual(status, 1)
        self.assertEqual(out["error"]["kind"], "unknown-kind")
        self.assertEqual(out["error"]["details"]["defined"], ["branch", "group"])
        self.assertEqual(list(self.working.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
