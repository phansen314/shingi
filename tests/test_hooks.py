import json
import os
import pty
import signal
import subprocess
import sys
import time
import unittest

from support import ShingiTestCase


class HooksTest(ShingiTestCase):
    def create(self, *args):
        return self.shingi("create", "HOME-1", "group", *args)

    def test_create_gives_its_hook_the_payload(self):
        command, out = self.recorder()
        self.write_hooks(create=[{"command": command}])
        status, envelope = self.create()
        self.assertEqual(status, 0, envelope)
        raw = out.read_bytes()
        self.assertTrue(raw.endswith(b"\n"))
        self.assertEqual(raw.count(b"\n"), 1)
        payload = json.loads(raw)
        self.assertEqual(sorted(payload), ["event", "input", "result", "schema", "tool", "version", "warnings"])
        self.assertEqual(payload["schema"], 1)
        self.assertEqual(payload["tool"], "shingi")
        self.assertEqual(payload["version"], self.koan_free_version())
        self.assertEqual(payload["event"], "create")
        self.assertEqual(payload["input"], {"path": "HOME-1", "kind": "group"})
        self.assertEqual(payload["result"], envelope["result"])
        self.assertEqual(payload["warnings"], [])

    def koan_free_version(self):
        return self.shingi("version")[1]["result"]["version"]

    def test_input_is_as_the_command_line_set_it(self):
        command, out = self.recorder()
        self.write_hooks(create=[{"command": command}])
        self.create("--title", "A title", "--notes", "Some notes")
        self.assertEqual(
            json.loads(out.read_text())["input"],
            {"path": "HOME-1", "kind": "group", "title": "A title", "notes": "Some notes"},
        )

    def test_create_with_input_gives_the_same_input(self):
        command, out = self.recorder()
        self.write_hooks(create=[{"command": command}])
        given = {"path": "HOME-1", "kind": "group", "title": "T"}
        status, envelope = self.shingi("create", "-i", "-", stdin=json.dumps(given).encode())
        self.assertEqual(status, 0, envelope)
        self.assertEqual(json.loads(out.read_text())["input"], given)

    def test_a_failed_create_fires_nothing(self):
        command, out = self.recorder()
        self.shingi("create", "HOME-1", "group")
        self.write_hooks(create=[{"command": command}])
        status, envelope = self.create()
        self.assertEqual(envelope["error"]["kind"], "unit-exists")
        self.assertFalse(out.exists())

    def test_a_create_that_fails_part_way_fires_nothing(self):
        command, out = self.recorder()
        self.shingi("create", "HOME-1", "group")
        self.write_hooks(create=[{"command": command}])
        self.fake_koan(block="error")
        status, envelope = self.shingi("create", "HOME-1/x", "branch")
        self.assertEqual(envelope["error"]["kind"], "koan-failed")
        self.assertIn("partial", envelope["error"])
        self.assertFalse(out.exists())

    def test_a_read_fires_nothing(self):
        command, out = self.recorder()
        self.shingi("create", "HOME-1", "group")
        self.write_hooks(create=[{"command": command}])
        for args in (["where", "HOME-1"], ["list"], ["kinds"], ["version"]):
            self.shingi(*args)
        self.assertFalse(out.exists())

    def test_hooks_run_in_the_files_order(self):
        log = self.tmp / "order"
        self.write_hooks(create=[
            {"command": self.hook(f"echo first >> {log}\n")},
            {"command": self.hook(f"echo second >> {log}\n")},
            {"command": self.hook(f"echo third >> {log}\n")},
        ])
        self.create()
        self.assertEqual(log.read_text(), "first\nsecond\nthird\n")

    def test_a_failing_hook_does_not_stop_the_next(self):
        command, out = self.recorder()
        self.write_hooks(create=[{"command": "exit 1"}, {"command": command}])
        status, envelope = self.create()
        self.assertEqual(status, 0)
        self.assertEqual([w["kind"] for w in envelope["warnings"]], ["hook-failed"])
        self.assertTrue(out.exists())

    def test_a_hooks_stdout_never_reaches_shingis(self):
        self.write_hooks(create=[{"command": "echo noise; echo more noise"}])
        proc = subprocess.run(
            ["shingi", "create", "HOME-1", "group", "--config", str(self.config)],
            env=self.env, capture_output=True,
        )
        self.assertEqual(proc.stdout.count(b"\n"), 1)
        self.assertTrue(json.loads(proc.stdout)["ok"])
        self.assertNotIn(b"noise", proc.stdout)

    def test_a_hook_that_fails_is_a_warning_and_the_command_succeeds(self):
        for command, exit_status in (("exit 3", 3), ("no-such-command-here", 127), ("kill -KILL $$", 137)):
            with self.subTest(command=command):
                self.write_hooks(create=[{"command": command}])
                name = f"HOME-{exit_status}"
                status, envelope = self.shingi("create", name, "group")
                self.assertEqual(status, 0, envelope)
                self.assertTrue(envelope["ok"])
                self.assertEqual(envelope["result"]["unit"]["path"], name)
                (warning,) = envelope["warnings"]
                self.assertEqual(warning["kind"], "hook-failed")
                self.assertEqual(warning["details"]["exit"], exit_status)
                self.assertEqual(warning["unit"], name)
                self.assertEqual(warning["ids"], [])

    def test_hook_failed_details(self):
        command = self.hook("echo oops >&2\nexit 4\n")
        self.write_hooks(create=[{"command": "true"}, {"command": command}])
        status, envelope = self.create()
        (warning,) = envelope["warnings"]
        self.assertEqual(warning["details"], {
            "event": "create", "index": 1, "command": command, "description": None,
            "exit": 4, "stderr": "oops\n",
        })

    def test_stderr_is_the_last_2048_bytes(self):
        command = self.hook("head -c 5000 /dev/zero | tr '\\0' a >&2\nprintf END >&2\nexit 1\n")
        self.write_hooks(create=[{"command": command}])
        status, envelope = self.create()
        stderr = envelope["warnings"][0]["details"]["stderr"]
        self.assertEqual(len(stderr), 2048)
        self.assertTrue(stderr.endswith("aaaEND"))

    def test_stderr_with_invalid_utf8_is_replaced(self):
        self.write_hooks(create=[{"command": "printf '\\377ok' >&2; exit 1"}])
        status, envelope = self.create()
        self.assertEqual(envelope["warnings"][0]["details"]["stderr"], "�ok")

    def test_a_hook_that_cant_be_started(self):
        # /bin/sh itself can't be missing, so an argument too long to exec stands in for one that can't start.
        self.write_hooks(create=[{"command": "x" * (3 * 1024 * 1024)}])
        status, envelope = self.create()
        self.assertEqual(status, 0, envelope)
        (warning,) = envelope["warnings"]
        self.assertEqual(warning["kind"], "hook-failed")
        self.assertIsNone(warning["details"]["exit"])
        self.assertEqual(warning["details"]["stderr"], "")

    def test_a_hook_that_never_reads_stdin_does_not_block(self):
        self.write_hooks(create=[{"command": "sleep 2"}])
        notes = b"n" * (4 * 1024 * 1024)
        started = time.monotonic()
        status, envelope = self.shingi("create", "HOME-1", "group", "--notes-file", "-", stdin=notes)
        elapsed = time.monotonic() - started
        self.assertEqual(status, 0, envelope)
        self.assertEqual(envelope["warnings"], [])
        self.assertGreater(elapsed, 1.5)  # the hook ran, and shingi waited for it only
        self.assertLess(elapsed, 5)

    def test_the_payload_carries_the_commands_warnings(self):
        command, out = self.recorder()
        self.shingi("create", "HOME-1", "group")
        self.koan("delete-folder", "/shingi/HOME-1", "--recursive")
        self.write_hooks(create=[{"command": command}])
        status, envelope = self.shingi("create", "HOME-1/x", "branch")
        self.assertEqual(status, 0, envelope)
        self.assertTrue(envelope["warnings"])
        self.assertEqual(json.loads(out.read_text())["warnings"], envelope["warnings"])

    def test_two_hooks_each_read_the_whole_payload(self):
        first, first_out = self.recorder()
        second, second_out = self.recorder()
        # The first hook reads only a little, and leaves a background process holding its stdin.
        pid = self.tmp / "background.pid"
        self.addCleanup(self.kill_recorded, pid)
        self.write_hooks(create=[
            {"command": self.hook(f"head -c 10 > /dev/null; sleep 30 & echo $! > {pid}\n")},
            {"command": first},
            {"command": second},
        ])
        status, envelope = self.create()
        self.assertEqual(status, 0, envelope)
        self.assertEqual(first_out.read_bytes(), second_out.read_bytes())
        self.assertEqual(json.loads(first_out.read_text())["event"], "create")

    @staticmethod
    def kill_recorded(pid_file):
        try:
            os.kill(int(pid_file.read_text()), signal.SIGKILL)
        except (OSError, ValueError):
            pass

    def test_a_background_process_does_not_hold_the_command(self):
        marker = self.tmp / "background"
        self.write_hooks(create=[{"command": f"(sleep 6; touch {marker}) &"}])
        started = time.monotonic()
        proc = subprocess.run(
            [sys.executable, "-m", "shingi", "create", "HOME-1", "group", "--config", str(self.config)],
            env=self.env, capture_output=True,
        )
        self.assertLess(time.monotonic() - started, 4)
        self.assertTrue(json.loads(proc.stdout)["ok"])
        self.assertFalse(marker.exists())
        deadline = time.monotonic() + 10
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.1)
        self.assertTrue(marker.exists())

    def test_a_hook_has_no_controlling_terminal(self):
        """Under a pty that is shingi's controlling terminal, a hook that opens /dev/tty fails."""
        self.write_hooks(create=[{"command": "exec 3</dev/tty"}])
        master, slave = pty.openpty()
        try:
            proc = subprocess.Popen(
                [sys.executable, "-m", "shingi", "create", "HOME-1", "group", "--config", str(self.config)],
                env=self.env, stdin=slave, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                preexec_fn=lambda: self.become_session_leader(slave),
            )
        finally:
            os.close(slave)
        try:
            out, _ = proc.communicate(timeout=20)
        finally:
            os.close(master)
        envelope = json.loads(out)
        self.assertEqual(proc.returncode, 0, envelope)
        (warning,) = envelope["warnings"]
        self.assertEqual(warning["kind"], "hook-failed")

    @staticmethod
    def become_session_leader(tty):
        import fcntl
        import termios
        os.setsid()
        fcntl.ioctl(tty, termios.TIOCSCTTY, 0)


if __name__ == "__main__":
    unittest.main()
