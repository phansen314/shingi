import json
import os
import shutil
import signal
import subprocess
import time
import unittest

from support import ShingiTestCase


class HelpTest(ShingiTestCase):
    def help(self, *args):
        proc = subprocess.run([shutil.which("shingi"), *args], env=self.env, capture_output=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stderr, b"")
        return proc.stdout.decode()

    def test_with_no_command(self):
        for flag in ("--help", "-h"):
            with self.subTest(flag):
                out = self.help(flag)
                self.assertTrue(out.startswith("Usage: shingi <command>"))
                for command in ("where", "context", "list", "kinds", "version", "create", "adopt"):
                    self.assertIn(f"  {command} ", out)

    def test_for_a_command_runs_nothing(self):
        out = self.help("create", "HOME-1", "group", "--help")
        self.assertTrue(out.startswith("Usage: shingi create <path> <kind>"))
        self.assertFalse((self.working / "HOME-1").exists())

    def test_an_options_value_is_not_help(self):
        status, out = self.shingi("create", "HOME-1", "group", "--title", "--help")
        self.assertEqual(status, 0, out)
        self.assertEqual(out["result"]["unit"]["title"], "--help")


class DoubleDashTest(ShingiTestCase):
    def shingi(self, *args):
        """Run shingi with --config before the arguments, since everything after -- is one."""
        proc = subprocess.run([shutil.which("shingi"), args[0], "--config", str(self.config), *args[1:]],
                              env=self.env, capture_output=True)
        return proc.returncode, json.loads(proc.stdout)

    def test_ends_options(self):
        status, out = self.shingi("where", "--", "-h")
        self.assertEqual(status, 1)
        self.assertEqual(out["error"]["details"]["reason"], "hyphen")

    def test_an_option_after_it_is_an_argument(self):
        status, out = self.shingi("kinds", "--", "--title")
        self.assertEqual(status, 2)
        self.assertEqual(out["error"]["details"]["problems"][0]["argument"], "--title")


class OutcomeUnknownTest(ShingiTestCase):
    def test_unwritable_stdout_is_exit_3(self):
        read, write = os.pipe()
        os.close(read)
        proc = subprocess.run([shutil.which("shingi"), "version"], env=self.env, stdout=write, stderr=subprocess.PIPE)
        os.close(write)
        self.assertEqual(proc.returncode, 3)
        self.assertEqual(proc.stderr.count(b"\n"), 1)
        self.assertIn(b"outcome is unknown", proc.stderr)

    def test_closed_stdout_is_exit_3(self):
        proc = subprocess.run([shutil.which("shingi"), "version"], env=self.env, stdout=subprocess.DEVNULL,
                              stderr=subprocess.PIPE, preexec_fn=lambda: os.close(1))
        self.assertEqual(proc.returncode, 3, proc.stderr)
        self.assertIn(b"outcome is unknown", proc.stderr)

    def test_an_interrupt_is_a_crash(self):
        self.shingi("create", "HOME-1", "group")
        started = self.working.parent / "started"
        self.fake_koan(list="sleep")
        self.env["FAKE_KOAN_STARTED"] = str(started)
        proc = subprocess.Popen([shutil.which("shingi"), "where", "HOME-1", "--config", str(self.config)],
                                env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        deadline = time.monotonic() + 10
        while not started.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        proc.send_signal(signal.SIGINT)
        out, err = proc.communicate()
        self.assertEqual(proc.returncode, -signal.SIGINT)
        self.assertEqual((out, err), (b"", b""))


class StderrTest(ShingiTestCase):
    def test_one_line_whatever_the_message_holds(self):
        proc = subprocess.run([shutil.which("shingi"), "kinds", "--config", "a\nb\x1b"],
                              env=self.env, capture_output=True, cwd=self.working)
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(proc.stderr.count(b"\n"), 1, proc.stderr)
        self.assertIn(b"a\\nb\\x1b", proc.stderr)


if __name__ == "__main__":
    unittest.main()
