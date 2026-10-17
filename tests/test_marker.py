import json
import os
import shutil
import subprocess
import unittest

from support import ShingiTestCase


class MarkerTest(ShingiTestCase):
    def setUp(self):
        super().setUp()
        self.ids = {}
        for path in ("HOME-1", "HOME-1/a", "HOME-1/b"):
            status, out = self.shingi("create", path, "branch")
            self.assertEqual(status, 0, out)
            self.ids[path] = out["result"]["unit"]["id"]
        self.tree = self.tmp / "worktree"
        (self.tree / "src" / "deep").mkdir(parents=True)
        self.marker = self.tree / ".shingi" / "unit.json"
        self.bind("HOME-1/a", self.tree)

    def bind(self, unit, folder):
        status, out = self.shingi("bind", unit, str(folder))
        self.assertEqual(status, 0, out)

    def rewrite(self, **fields):
        self.marker.write_text(json.dumps({**json.loads(self.marker.read_text()), **fields}))

    def where(self, cwd, status=0):
        code, out = self.shingi("where", cwd=cwd)
        self.assertEqual(code, status, out)
        return out

    def assert_not_found(self, out, reason="outside-root", marker=None):
        self.assertEqual(out["error"]["kind"], "not-found")
        self.assertEqual(out["error"]["details"]["reason"], reason)
        self.assertEqual(out["error"]["details"]["marker"], marker)

    def test_from_the_worktree_root(self):
        out = self.where(self.tree)
        self.assertEqual(out["result"]["path"], "HOME-1/a")
        self.assertEqual(out["warnings"], [])

    def test_from_a_subdirectory(self):
        self.assertEqual(self.where(self.tree / "src" / "deep")["result"]["path"], "HOME-1/a")

    def test_context_too(self):
        code, out = self.shingi("context", cwd=self.tree / "src")
        self.assertEqual(code, 0, out)
        self.assertEqual(out["result"]["unit"]["path"], "HOME-1/a")
        self.assertEqual(out["result"]["marker"], str(self.marker))

    def test_context_marker_is_null_without_one(self):
        for args, cwd in ((["HOME-1/a"], self.tree), ([], self.working / "HOME-1" / "a")):
            with self.subTest(args):
                code, out = self.shingi("context", *args, cwd=cwd)
                self.assertEqual(code, 0, out)
                self.assertIsNone(out["result"]["marker"])

    def test_an_unbound_folder_inside_shows_the_outer_marker(self):
        # A group bound to a checkout covers an unbound worktree inside it; context says by which marker.
        inner = self.tree / "src" / "deep"
        code, out = self.shingi("context", cwd=inner)
        self.assertEqual(code, 0, out)
        self.assertEqual((out["result"]["unit"]["path"], out["result"]["marker"]), ("HOME-1/a", str(self.marker)))
        self.bind("HOME-1/b", inner)
        code, out = self.shingi("context", cwd=inner)
        self.assertEqual((out["result"]["unit"]["path"], out["result"]["marker"]),
                         ("HOME-1/b", str(inner / ".shingi" / "unit.json")))

    def test_the_working_root_wins_over_a_marker(self):
        # A marker inside the working root is never looked at: bind refuses one, so plant it.
        folder = self.working / "HOME-1" / "b"
        shutil.copytree(self.tree / ".shingi", folder / ".shingi")
        self.assertEqual(self.where(folder)["result"]["path"], "HOME-1/b")
        plain = self.working / "scratch"
        plain.mkdir()
        shutil.copytree(self.tree / ".shingi", plain / ".shingi")
        self.assert_not_found(self.where(plain, status=1), reason="no-unit")

    def test_the_nearest_marker_wins(self):
        inner = self.tree / "src"
        self.bind("HOME-1/b", inner)
        self.assertEqual(self.where(inner / "deep")["result"]["path"], "HOME-1/b")
        self.assertEqual(self.where(self.tree)["result"]["path"], "HOME-1/a")

    def test_a_shingi_folder_without_unit_json_is_passed(self):
        inner = self.tree / "src"
        (inner / ".shingi").mkdir()
        (inner / ".shingi" / ".gitignore").write_text("*\n")
        self.assertEqual(self.where(inner / "deep")["result"]["path"], "HOME-1/a")

    def test_a_foreign_marker_is_never_used(self):
        self.rewrite(dir="/somewhere/else")
        out = self.where(self.tree / "src", status=1)
        self.assert_not_found(out)
        self.assertEqual(out["warnings"], [{
            "kind": "foreign-marker", "message": out["warnings"][0]["message"], "unit": None, "ids": [],
            "details": {"path": str(self.marker), "dir": "/somewhere/else"},
        }])

    def test_a_copied_marker_is_foreign(self):
        copy = self.tmp / "copy"
        shutil.copytree(self.tree, copy)
        out = self.where(copy, status=1)
        self.assertEqual([w["kind"] for w in out["warnings"]], ["foreign-marker"])

    def test_a_stale_marker_finds_its_unit_by_id(self):
        self.rewrite(path="HOME-1/old")
        out = self.where(self.tree)
        self.assertEqual(out["result"]["path"], "HOME-1/a")
        self.assertEqual([(w["kind"], w["unit"], w["details"]) for w in out["warnings"]], [
            ("stale-marker", "HOME-1/a", {"path": str(self.marker), "stale": "HOME-1/old"}),
        ])

    def test_a_path_holding_another_unit_is_stale(self):
        self.rewrite(path="HOME-1/b")
        out = self.where(self.tree)
        self.assertEqual(out["result"]["path"], "HOME-1/a")
        self.assertEqual(out["warnings"][0]["kind"], "stale-marker")

    def test_a_deleted_unit(self):
        status, out = self.shingi("delete", "HOME-1/a")
        self.assertEqual(status, 0, out)
        out = self.where(self.tree, status=1)
        self.assert_not_found(out, reason="unit-deleted", marker=str(self.marker))
        self.assertEqual(out["warnings"], [])

    def test_unusable_markers(self):
        for text, reason in [
            ("{", "corrupt"),
            (json.dumps({"schema": 2, "id": self.ids["HOME-1/a"], "path": "HOME-1/a", "dir": str(self.tree)}),
             "unsupported-format"),
            (json.dumps({"schema": 1, "id": self.ids["HOME-1/a"], "path": "HOME-1/a"}), "corrupt"),
            (json.dumps({"schema": 1, "id": self.ids["HOME-1/a"], "path": "/HOME-1", "dir": str(self.tree)}),
             "corrupt"),
        ]:
            with self.subTest(reason=reason, text=text):
                self.marker.write_text(text)
                out = self.where(self.tree, status=1)
                self.assert_not_found(out)
                self.assertEqual([(w["kind"], w["unit"], w["details"]) for w in out["warnings"]], [
                    ("unsupported-marker", None, {"path": str(self.marker), "reason": reason}),
                ])

    def test_an_unreadable_marker(self):
        self.marker.unlink()
        self.marker.mkdir()
        out = self.where(self.tree, status=1)
        self.assertEqual(out["warnings"][0]["details"]["reason"], "unreadable")

    def test_the_walk_stops_at_a_foreign_or_unusable_marker(self):
        inner = self.tree / "src"
        self.bind("HOME-1/b", inner)
        inner_marker = inner / ".shingi" / "unit.json"
        good = inner_marker.read_text()
        for text, kind in [
            (json.dumps({**json.loads(good), "dir": "/elsewhere"}), "foreign-marker"),
            ("not json", "unsupported-marker"),
        ]:
            with self.subTest(kind):
                inner_marker.write_text(text)
                out = self.where(inner / "deep", status=1)
                self.assert_not_found(out)
                self.assertEqual([w["kind"] for w in out["warnings"]], [kind])

    def test_a_copy_sharing_the_id_finds_the_first_in_path_order(self):
        shutil.copytree(self.working / "HOME-1" / "a", self.working / "HOME-1" / "c")
        self.rewrite(path="HOME-1/old")
        self.assertEqual(self.where(self.tree)["result"]["path"], "HOME-1/a")

    def test_no_working_root_is_unit_deleted(self):
        self.working.rename(self.tmp / "elsewhere")
        self.assert_not_found(self.where(self.tree, status=1), reason="unit-deleted", marker=str(self.marker))

    def test_context_warns_as_where(self):
        self.rewrite(path="HOME-1/old")
        code, out = self.shingi("context", cwd=self.tree)
        self.assertEqual(code, 0, out)
        self.assertEqual([w["kind"] for w in out["warnings"]], ["stale-marker"])
        self.assertEqual(out["result"]["marker"], str(self.marker))
        self.rewrite(dir="/elsewhere")
        code, out = self.shingi("context", cwd=self.tree)
        self.assertEqual((code, out["error"]["kind"]), (1, "not-found"))
        self.assertEqual([w["kind"] for w in out["warnings"]], ["foreign-marker"])

    @unittest.skipIf(os.geteuid() == 0, "root reads anything")
    def test_a_folder_that_cant_be_looked_in_is_io(self):
        src = self.tree / "src"
        src.chmod(0)
        self.addCleanup(src.chmod, 0o755)
        code, out = self.shingi("where", "-i", "-", stdin=json.dumps({"cwd": str(src / "deep")}).encode())
        self.assertEqual((code, out["error"]["kind"]), (1, "io"))

    def test_reads_never_write(self):
        self.rewrite(path="HOME-1/old")
        before = self.marker.read_bytes()
        self.where(self.tree)
        self.assertEqual(self.marker.read_bytes(), before)

    def test_no_marker_is_outside_root(self):
        out = self.where(self.tmp, status=1)
        self.assert_not_found(out)
        self.assertEqual(out["warnings"], [])


@unittest.skipUnless(shutil.which("git"), "needs git")
class GitTest(ShingiTestCase):
    def git(self, *args, cwd):
        proc = subprocess.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "init.defaultBranch=main", *args],
            cwd=cwd, env=self.env, capture_output=True, text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return proc.stdout

    def test_git_never_sees_the_marker(self):
        self.assertEqual(self.shingi("create", "HOME-1", "branch")[0], 0)
        repo = self.tmp / "repo"
        repo.mkdir()
        self.git("init", cwd=repo)
        (repo / "README").write_text("hi\n")
        self.git("add", "-A", cwd=repo)
        self.git("commit", "-m", "first", cwd=repo)
        tree = self.tmp / "wt"
        self.git("worktree", "add", "-b", "HOME-1", str(tree), cwd=repo)
        status, out = self.shingi("bind", "HOME-1", str(tree))
        self.assertEqual(status, 0, out)
        self.assertEqual(self.git("status", "--porcelain", "--untracked-files=all", cwd=tree), "")
        self.git("add", "-A", cwd=tree)
        self.assertEqual(self.git("diff", "--cached", "--name-only", cwd=tree), "")
        self.assertEqual(self.shingi("where", cwd=tree)[1]["result"]["path"], "HOME-1")
        self.git("worktree", "remove", str(tree), cwd=repo)
        self.assertFalse(tree.exists())


if __name__ == "__main__":
    unittest.main()
