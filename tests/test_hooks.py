import json
import os
import pty
import signal
import subprocess
import sys
import time
import errno
import unittest
from unittest import mock
from pathlib import Path

from shingi import hooks
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

    def test_a_hook_runs_in_the_callers_directory_with_shingis_environment(self):
        where = self.tmp / "where"
        self.write_hooks(create=[{"command": f'pwd > {where}; echo "$SHINGI_TEST_MARK" >> {where}'}])
        self.env["SHINGI_TEST_MARK"] = "marked"
        cwd = self.tmp / "elsewhere"
        cwd.mkdir()
        status, envelope = self.shingi("create", "HOME-1", "group", cwd=cwd)
        self.assertEqual(status, 0, envelope)
        self.assertEqual(where.read_text().split("\n")[:2], [str(cwd.resolve()), "marked"])

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

    def test_a_hooks_stdin_is_a_file_not_a_pipe(self):
        self.write_hooks(create=[{"command": "[ -f /dev/stdin ] || exit 9"}])
        status, envelope = self.shingi("create", "HOME-1", "group")
        self.assertEqual((status, envelope["warnings"]), (0, []))

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


class TimeoutTest(ShingiTestCase):
    def alive(self, pid):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        return True

    def test_a_hook_past_its_timeout_is_hook_timeout(self):
        background = self.tmp / "background.pid"
        self.addCleanup(HooksTest.kill_recorded, background)
        command = self.hook(f"echo partial >&2\nsleep 60 & echo $! > {background}\nsleep 60\n")
        self.write_hooks(create=[{"command": "true"}, {"command": command, "timeout": 0.5, "description": "slow"}])
        started = time.monotonic()
        status, envelope = self.shingi("create", "HOME-1", "group")
        elapsed = time.monotonic() - started
        self.assertEqual(status, 0, envelope)
        self.assertLess(elapsed, 0.5 + 1)
        (warning,) = envelope["warnings"]
        self.assertEqual(warning["kind"], "hook-timeout")
        self.assertEqual(warning["unit"], "HOME-1")
        self.assertEqual(warning["ids"], [])
        self.assertEqual(warning["details"], {
            "event": "create", "index": 1, "command": command, "description": "slow",
            "timeout": 0.5, "stderr": "partial\n",
        })
        self.assertFalse(self.alive(int(background.read_text())))

    def test_timeout_is_reported_as_the_file_wrote_it(self):
        self.write_hooks(create=[{"command": "sleep 60", "timeout": 1}])
        status, envelope = self.shingi("create", "HOME-1", "group")
        timeout = envelope["warnings"][0]["details"]["timeout"]
        self.assertEqual(timeout, 1)
        self.assertIsInstance(timeout, int)

    def test_a_hook_that_ignores_sigterm_is_killed_all_the_same(self):
        self.write_hooks(create=[{"command": self.hook("trap '' TERM\nwhile true; do sleep 1; done\n"), "timeout": 0.5}])
        started = time.monotonic()
        status, envelope = self.shingi("create", "HOME-1", "group")
        self.assertLess(time.monotonic() - started, 3)
        self.assertEqual(envelope["warnings"][0]["kind"], "hook-timeout")

    def test_the_default_timeout_is_ten_seconds(self):
        self.write_hooks(create=[{"command": "sleep 2"}])
        status, envelope = self.shingi("create", "HOME-1", "group")
        self.assertEqual(envelope["warnings"], [])

    def test_failing_and_timed_out_hooks_sort_among_the_commands_own_warnings(self):
        self.shingi("create", "HOME-1", "group")
        self.koan("delete-folder", "/shingi/HOME-1", "--recursive")  # so a child has a parent-unlinked warning
        self.write_hooks(create=[
            {"command": "exit 2"},
            {"command": "sleep 60", "timeout": 0.3},
            {"command": "exit 3"},
            {"command": "sleep 60", "timeout": 0.3},
        ])
        status, envelope = self.shingi("create", "HOME-1/x", "branch")
        self.assertEqual(status, 0, envelope)
        got = [(w["kind"], w["details"].get("index")) for w in envelope["warnings"]]
        self.assertEqual(got, [
            ("hook-failed", 0), ("hook-failed", 2),
            ("hook-timeout", 1), ("hook-timeout", 3),
            ("parent-unlinked", None), ("parent-unlinked", None),
        ])


class EventsTest(ShingiTestCase):
    def setUp(self):
        super().setUp()
        self.created, self.created_out = self.recorder()
        self.adopted, self.adopted_out = self.recorder()
        self.deleted, self.deleted_out = self.recorder()
        self.write_hooks(
            create=[{"command": self.created}], adopt=[{"command": self.adopted}], delete=[{"command": self.deleted}],
        )

    def fired(self):
        return sorted(out.name for out in (self.created_out, self.adopted_out, self.deleted_out) if out.exists())

    def test_adopt_fires_its_own_event(self):
        (self.working / "HOME-1").mkdir()
        status, envelope = self.shingi("adopt", "HOME-1", "group", "--title", "T")
        self.assertEqual(status, 0, envelope)
        payload = json.loads(self.adopted_out.read_text())
        self.assertEqual(payload["event"], "adopt")
        self.assertEqual(payload["input"], {"path": "HOME-1", "kind": "group", "title": "T"})
        self.assertEqual(payload["result"], envelope["result"])
        self.assertEqual(self.fired(), [self.adopted_out.name])

    def test_delete_fires_its_own_event(self):
        self.shingi("create", "HOME-1", "group")
        self.created_out.unlink()
        status, envelope = self.shingi("delete", "HOME-1")
        self.assertEqual(status, 0, envelope)
        payload = json.loads(self.deleted_out.read_text())
        self.assertEqual(payload["event"], "delete")
        self.assertEqual(payload["input"], {"unit": "HOME-1"})
        self.assertEqual(payload["result"], envelope["result"])
        self.assertEqual(payload["warnings"], [])
        self.assertEqual(self.fired(), [self.deleted_out.name])

    def test_create_fires_only_create(self):
        self.shingi("create", "HOME-1", "group")
        self.assertEqual(self.fired(), [self.created_out.name])

    def test_a_failed_adopt_or_delete_fires_nothing(self):
        self.assertEqual(self.shingi("adopt", "HOME-1", "group")[1]["error"]["kind"], "not-found")
        self.assertEqual(self.shingi("delete", "HOME-1")[1]["error"]["kind"], "not-found")
        self.assertEqual(self.fired(), [])

    def test_delete_puts_its_own_warnings_in_the_payload_and_the_hooks_after_them_in_order(self):
        command, out = self.recorder()
        self.shingi("create", "HOME-1", "group")
        self.fake_koan(delete_folder="warn")
        self.write_hooks(delete=[{"command": "exit 1"}, {"command": command}])
        status, envelope = self.shingi("delete", "HOME-1")
        self.assertEqual(status, 0, envelope)
        self.assertEqual([w["kind"] for w in envelope["warnings"]], ["hook-failed", "koan-warning"])
        self.assertEqual(json.loads(out.read_text())["warnings"], [envelope["warnings"][1]])

    def test_a_failing_delete_hook_warns_for_the_deleted_unit(self):
        self.write_hooks(delete=[{"command": "exit 5"}])
        self.shingi("create", "HOME-1", "group")
        status, envelope = self.shingi("delete", "HOME-1")
        self.assertEqual(status, 0, envelope)
        (warning,) = envelope["warnings"]
        self.assertEqual((warning["kind"], warning["unit"], warning["details"]["exit"]), ("hook-failed", "HOME-1", 5))
        self.assertEqual(warning["details"]["event"], "delete")


class InterruptTest(ShingiTestCase):
    def wait_for(self, path, timeout=10):
        deadline = time.monotonic() + timeout
        while not path.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertTrue(path.exists(), f"{path} never appeared")

    def gone(self, pid_file):
        pid = int(pid_file.read_text())
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return True
            time.sleep(0.05)
        return False

    def test_an_interrupt_kills_the_hook_and_shingi_dies_of_the_signal(self):
        for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
            with self.subTest(signal=signum.name):
                name = f"HOME-{int(signum)}"
                hook_pid, background, ran = (self.tmp / f"{name}.{x}" for x in ("hook", "bg", "ran"))
                for path in (hook_pid, background, ran):
                    path.unlink(missing_ok=True)
                first = self.hook(f"echo $$ > {hook_pid}\nsleep 60 & echo $! > {background}\nsleep 60\n")
                self.write_hooks(create=[{"command": first}, {"command": f"touch {ran}"}])
                proc = subprocess.Popen(
                    ["shingi", "create", name, "group", "--config", str(self.config)],
                    env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                )
                try:
                    self.wait_for(background)
                    proc.send_signal(signum)
                    out, err = proc.communicate(timeout=10)
                finally:
                    proc.kill()
                self.assertEqual(proc.returncode, -signum)
                self.assertEqual((out, err), (b"", b""))
                self.assertTrue(self.gone(hook_pid))
                self.assertTrue(self.gone(background))
                self.assertFalse(ran.exists())
                self.assertEqual(self.shingi("where", name)[0], 0)  # the unit exists

    def test_an_ignored_signal_stays_ignored_while_a_hook_runs(self):
        started = self.tmp / "started"
        self.write_hooks(create=[{"command": self.hook(f"touch {started}\nsleep 1\n")}])
        proc = subprocess.Popen(
            ["shingi", "create", "HOME-1", "group", "--config", str(self.config)],
            env=self.env, stdout=subprocess.PIPE, preexec_fn=lambda: signal.signal(signal.SIGHUP, signal.SIG_IGN),
        )
        self.wait_for(started)
        proc.send_signal(signal.SIGHUP)
        out, _ = proc.communicate(timeout=10)
        self.assertEqual(proc.returncode, 0)
        self.assertTrue(json.loads(out)["ok"])


class CannotRunTest(unittest.TestCase):
    """Shingi failing to make what hooks need is a warning per hook, never a failed command."""

    def run_hooks(self):
        loaded = {"create": [hooks.Hook("true"), hooks.Hook("true", disabled=True), hooks.Hook("true", description="d")]}
        return hooks.run(loaded, "create", {}, {}, [], unit="HOME-1")

    def assert_every_hook_failed(self, warnings):
        self.assertEqual([(w["kind"], w["details"]["index"]) for w in warnings], [("hook-failed", 0), ("hook-failed", 2)])
        for warning in warnings:
            self.assertEqual((warning["unit"], warning["details"]["exit"], warning["details"]["stderr"]), ("HOME-1", None, ""))
            self.assertIn("No space left", warning["message"])

    def test_no_temp_directory(self):
        with mock.patch("tempfile.TemporaryDirectory", side_effect=OSError(errno.ENOSPC, "No space left on device")):
            self.assert_every_hook_failed(self.run_hooks())

    def test_no_payload(self):
        with mock.patch.object(Path, "write_text", side_effect=OSError(errno.ENOSPC, "No space left on device")):
            self.assert_every_hook_failed(self.run_hooks())

    def test_no_stderr_file_for_one_hook(self):
        real_open = open

        def refuse(path, *args, **kwargs):
            if Path(path).name == "stderr-2":
                raise OSError(errno.ENOSPC, "No space left on device")
            return real_open(path, *args, **kwargs)

        with mock.patch("builtins.open", refuse):
            warnings = self.run_hooks()
        self.assertEqual([(w["kind"], w["details"]["index"]) for w in warnings], [("hook-failed", 2)])


class ByHandTest(ShingiTestCase):
    """The recipe in the hooks spec, run as written."""

    RECIPE = (
        'shingi where "$1" | jq -c --arg version "$(shingi version | jq -r .result.version)" '
        "'{schema: 1, tool: \"shingi\", version: $version, event: \"create\", "
        "input: {path: .result.path, kind: .result.kind}, result: {unit: .result}, warnings: []}'"
    )

    def by_hand(self, unit):
        proc = subprocess.run(
            ["sh", "-c", self.RECIPE, "sh", unit], env=self.env, capture_output=True, check=True,
        )
        return proc.stdout

    def test_the_recipe_makes_the_payload_shingi_sent(self):
        command, out = self.recorder()
        self.write_hooks(create=[{"command": command}])
        self.shingi("create", "HOME-1", "group")
        sent = json.loads(out.read_text())
        by_hand = json.loads(self.by_hand("HOME-1"))
        self.assertEqual(sorted(by_hand), sorted(sent))
        for field in sent:
            if field == "warnings":
                self.assertEqual(type(by_hand[field]), type(sent[field]))
            else:
                self.assertEqual(by_hand[field], sent[field], field)

    def test_the_example_hook_copies_the_template_once(self):
        example = self.hook(
            "unit=$(jq -c .result.unit)\n"
            '[ "$(printf \'%s\' "$unit" | jq -r .kind)" = branch ] || exit 0\n'
            "plan=$(printf '%s' \"$unit\" | jq -r .working_folder)/plan.md\n"
            '[ -e "$plan" ] || cp ~/templates/branch-plan.md "$plan"\n'
        )
        (self.tmp / "templates").mkdir()
        (self.tmp / "templates" / "branch-plan.md").write_text("template\n")
        self.shingi("create", "HOME-1", "group")
        self.shingi("create", "HOME-1/b", "branch")
        plan = self.working / "HOME-1" / "b" / "plan.md"
        for unit in ("HOME-1", "HOME-1/b"):
            subprocess.run(["sh", "-c", example], input=self.by_hand(unit), env=self.env, check=True)
        self.assertEqual(plan.read_text(), "template\n")
        self.assertFalse((self.working / "HOME-1" / "plan.md").exists())
        plan.write_text("edited\n")
        subprocess.run(["sh", "-c", example], input=self.by_hand("HOME-1/b"), env=self.env, check=True)
        self.assertEqual(plan.read_text(), "edited\n")


if __name__ == "__main__":
    unittest.main()
