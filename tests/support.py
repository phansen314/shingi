"""A temporary koan tree and working root, and running shingi and koan against them."""

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


class ShingiTestCase(unittest.TestCase):
    def setUp(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        self.working = tmp / "working"
        self.working.mkdir()
        self.config = tmp / "shingi.toml"
        self.config.write_text(RULES.format(working=self.working))
        self.env = {**os.environ, "XDG_CONFIG_HOME": str(tmp / "config")}
        self.koan("init", str(tmp / "tree"))

    def shingi(self, *args, cwd=None, stdin=b""):
        """Run shingi; return its exit status and envelope."""
        proc = subprocess.run(
            [shutil.which("shingi"), *args, "--config", str(self.config)],
            env=self.env, capture_output=True, cwd=cwd, input=stdin,
        )
        return proc.returncode, json.loads(proc.stdout)

    def koan(self, *args):
        """Run koan; return its result."""
        proc = subprocess.run(["koan", *args], env=self.env, capture_output=True, check=True)
        return json.loads(proc.stdout)["result"]

    def koan_show(self, task_id):
        return self.koan("show", str(task_id))["tasks"][0]
