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


FAKE_KOAN = """\
#!/usr/bin/env python3
# koan, failing on cue: FAKE_KOAN_<CALL>=error|warn-error|garbage|crash|warn (CALL as LIST, CREATE_BATCH, BLOCK).
import json, os, subprocess, sys
call = sys.argv[1]
mode = os.environ.get("FAKE_KOAN_" + call.upper().replace("-", "_"), "")
if mode == "garbage":
    print("not an envelope")
    sys.exit(0)
if mode == "crash":
    sys.exit(137)
if mode in ("error", "warn-error"):
    warnings = [{"kind": "unusable-file", "message": "bad task file", "paths": ["/x/9.json"], "ids": [9], "reason": "corrupt"}]
    error = {"kind": "io", "message": "disk on fire", "details": {}}
    print(json.dumps({"ok": False, "error": error, "warnings": warnings if mode == "warn-error" else []}))
    sys.exit(1)
proc = subprocess.run([%r, *sys.argv[1:]], stdin=sys.stdin, capture_output=True)
out = proc.stdout
if mode == "warn":
    envelope = json.loads(out)
    envelope["warnings"].append({"kind": "unusable-file", "message": "bad task file", "paths": ["/x/9.json"], "ids": [9], "reason": "corrupt"})
    out = (json.dumps(envelope) + "\\n").encode()
sys.stdout.buffer.write(out)
sys.exit(proc.returncode)
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

    def fake_koan(self, **modes):
        """Put a koan first on PATH that fails each named call as told, e.g. list="error"."""
        bin_dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, bin_dir)
        fake = bin_dir / "koan"
        fake.write_text(FAKE_KOAN % shutil.which("koan"))
        fake.chmod(0o755)
        self.env["PATH"] = f"{bin_dir}:{self.env['PATH']}"
        for call, mode in modes.items():
            self.env[f"FAKE_KOAN_{call.upper()}"] = mode

    def koan_show(self, task_id):
        return self.koan("show", str(task_id))["tasks"][0]
