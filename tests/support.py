"""A temporary koan tree and working root, and running shingi and koan against them."""

import json
import os
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

RULES = """\
schema = 1

[kind.group]
description = "Work gathered under one name."
suggests    = ["group", "branch"]

[kind.branch]
description = "Work on one branch of one repository."
"""


FAKE_KOAN = """\
#!/usr/bin/env python3
# koan, failing on cue: FAKE_KOAN_<CALL>=error|warn-error|garbage|crash|sleep|warn|partial (CALL as LIST, CREATE_BATCH,
# BLOCK); partial does the call, then fails as koan does after making its tasks. FAKE_KOAN_<CALL>_TOUCH=<file>
# creates that file after the call, to stage a race.
import json, os, subprocess, sys
WARNING = {"kind": "unusable-file", "message": "bad task file", "ids": [9], "paths": ["/x/9.json"]}
ERROR = {"kind": "io", "rule": None, "message": "disk on fire", "ids": [9], "folders": [], "paths": [], "problems": [], "changed_paths": []}
call = sys.argv[1]
mode = os.environ.get("FAKE_KOAN_" + call.upper().replace("-", "_"), "")
if mode == "garbage":
    print("not an envelope")
    sys.exit(0)
if mode == "crash":
    sys.exit(137)
if mode == "sleep":  # tell the test it's waiting, then wait
    open(os.environ["FAKE_KOAN_STARTED"], "x").close()
    import time
    time.sleep(5)
if mode in ("error", "warn-error"):
    print(json.dumps({"ok": False, "error": ERROR, "warnings": [WARNING] if mode == "warn-error" else []}))
    sys.exit(1)
proc = subprocess.run([%r, *sys.argv[1:]], stdin=sys.stdin, capture_output=True)
out = proc.stdout
if mode == "warn":
    envelope = json.loads(out)
    envelope["warnings"].append(WARNING)
    out = (json.dumps(envelope) + "\\n").encode()
touch = os.environ.get("FAKE_KOAN_" + call.upper().replace("-", "_") + "_TOUCH")
if touch:
    open(touch, "x").close()
if mode == "partial":
    error = {**ERROR, "ids": json.loads(out)["result"]["ids"], "changed_paths": ["/x/state.json"]}
    print(json.dumps({"ok": False, "error": error, "warnings": []}))
    sys.exit(1)
sys.stdout.buffer.write(out)
sys.exit(proc.returncode)
"""


class ShingiTestCase(unittest.TestCase):
    def setUp(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        self.working = tmp / "shingi-root"
        self.working.mkdir()
        self.config = tmp / "shingi.toml"
        self.config.write_text(RULES)
        self.tmp = tmp
        self.env = {**os.environ, "HOME": str(tmp), "XDG_CONFIG_HOME": str(tmp / "config")}
        self.hooks_file = tmp / "config" / "shingi" / "hooks.json"
        if sys.platform == "darwin":
            self.hooks_file = tmp / "Library" / "Application Support" / "shingi" / "hooks.json"
        self.koan("init")

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
            self.env[f"FAKE_KOAN_{call.upper()}"] = str(mode)

    def write_hooks(self, **events):
        """Write the hooks file, each keyword an event's list of hooks."""
        self.hooks_file.parent.mkdir(parents=True, exist_ok=True)
        self.hooks_file.write_text(json.dumps({"schema": 1, "hooks": events}))

    def hook(self, script):
        """An executable sh script, written to the temp directory; its quoted path, as a command."""
        self.scripts = getattr(self, "scripts", 0) + 1
        path = self.tmp / f"hook-{self.scripts}.sh"
        path.write_text("#!/bin/sh\n" + script)
        path.chmod(path.stat().st_mode | stat.S_IXUSR)
        return shlex.quote(str(path))

    def recorder(self):
        """A hook command that copies its stdin to a file, and that file's path."""
        out = self.tmp / f"payload-{self.hook_count()}.json"
        return self.hook(f"cat > {shlex.quote(str(out))}\n"), out

    def hook_count(self):
        self.recorders = getattr(self, "recorders", 0) + 1
        return self.recorders

    def koan_show(self, task_id):
        return self.koan("show", str(task_id))["task"]
