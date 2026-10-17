import json
import unittest

from support import ShingiTestCase


class BindTest(ShingiTestCase):
    def setUp(self):
        super().setUp()
        self.ids = {}
        for path in ("HOME-1", "HOME-1/a", "HOME-1/b"):
            status, out = self.shingi("create", path, "branch")
            self.assertEqual(status, 0, out)
            self.ids[path] = out["result"]["unit"]["id"]
        self.tree = self.tmp / "worktree"
        self.tree.mkdir()
        self.marker = self.tree / ".shingi" / "unit.json"

    def bind(self, *args, status=0, cwd=None):
        code, out = self.shingi("bind", *args, cwd=cwd)
        self.assertEqual(code, status, out)
        return out

    def marker_json(self):
        return json.loads(self.marker.read_text())

    def test_first_bind_writes_gitignore_and_marker(self):
        out = self.bind("HOME-1/a", str(self.tree))
        self.assertEqual(out["result"]["marker"], str(self.marker))
        self.assertEqual(out["result"]["unit"]["path"], "HOME-1/a")
        self.assertEqual((self.tree / ".shingi" / ".gitignore").read_text(), "*\n")
        self.assertEqual(self.marker_json(), {
            "schema": 1, "id": self.ids["HOME-1/a"], "path": "HOME-1/a", "dir": str(self.tree),
        })
        self.assertEqual(sorted(p.name for p in (self.tree / ".shingi").iterdir()), [".gitignore", "unit.json"])

    def test_dir_defaults_to_the_current_directory(self):
        self.bind("HOME-1/a", cwd=self.tree)
        self.assertEqual(self.marker_json()["dir"], str(self.tree))

    def test_a_relative_dir_is_from_the_current_directory(self):
        self.bind("HOME-1/a", "worktree", cwd=self.tmp)
        self.assertEqual(self.marker_json()["dir"], str(self.tree))

    def test_a_symlink_binds_its_real_path(self):
        link = self.tmp / "link"
        link.symlink_to(self.tree)
        out = self.bind("HOME-1/a", str(link))
        self.assertEqual(out["result"]["marker"], str(self.marker))
        self.assertEqual(self.marker_json()["dir"], str(self.tree))

    def test_binding_again_rewrites_and_refreshes_the_path(self):
        self.bind("HOME-1/a", str(self.tree))
        marker = self.marker_json()
        self.marker.write_text(json.dumps({**marker, "path": "HOME-1/old"}))
        out = self.bind("HOME-1/a", str(self.tree))
        self.assertEqual(out["warnings"], [])
        self.assertEqual(self.marker_json(), marker)

    def test_another_units_marker_is_bound_elsewhere(self):
        self.bind("HOME-1/a", str(self.tree))
        out = self.bind("HOME-1/b", str(self.tree), status=1)
        self.assertEqual(out["error"]["kind"], "bound-elsewhere")
        self.assertEqual(out["error"]["details"], {
            "marker": str(self.marker), "unit": "HOME-1/a", "id": self.ids["HOME-1/a"],
        })
        self.assertEqual(self.marker_json()["path"], "HOME-1/a")

    def test_replace_binds_over_another_unit(self):
        self.bind("HOME-1/a", str(self.tree))
        self.bind("HOME-1/b", str(self.tree), "--replace")
        self.assertEqual(self.marker_json()["id"], self.ids["HOME-1/b"])

    def test_replace_takes_no_value(self):
        out = self.bind("HOME-1/b", str(self.tree), "--replace=yes", status=2)
        self.assertEqual(out["error"]["kind"], "usage")

    def test_replace_from_input(self):
        self.bind("HOME-1/a", str(self.tree))
        code, out = self.shingi("bind", "-i", "-", stdin=json.dumps(
            {"unit": "HOME-1/b", "dir": str(self.tree), "replace": True}).encode())
        self.assertEqual(code, 0, out)
        self.assertEqual(self.marker_json()["id"], self.ids["HOME-1/b"])

    def test_a_foreign_marker_is_replaced_without_replace(self):
        self.bind("HOME-1/a", str(self.tree))
        self.marker.write_text(json.dumps({**self.marker_json(), "dir": "/somewhere/else"}))
        self.bind("HOME-1/b", str(self.tree))
        self.assertEqual(self.marker_json()["id"], self.ids["HOME-1/b"])

    def test_an_unusable_marker_is_replaced_without_replace(self):
        (self.tree / ".shingi").mkdir()
        self.marker.write_text("{not json")
        self.bind("HOME-1/b", str(self.tree))
        self.assertEqual(self.marker_json()["id"], self.ids["HOME-1/b"])

    def test_completes_a_shingi_folder_without_unit_json(self):
        (self.tree / ".shingi").mkdir()
        (self.tree / ".shingi" / ".gitignore").write_text("*\n")
        self.bind("HOME-1/a", str(self.tree))
        self.assertEqual(self.marker_json()["path"], "HOME-1/a")

    def test_refused_cases_change_nothing(self):
        (self.tree / "file").write_text("")
        cases = [
            (["HOME-1/nope", str(self.tree)], "not-found", "not-a-unit"),
            (["HOME-1/a", str(self.tmp / "missing")], "not-found", "no-folder"),
            (["HOME-1/a", str(self.tree / "file")], "not-found", "no-folder"),
            (["HOME-1/a", str(self.working)], "inside-root", None),
            (["HOME-1/a", str(self.working / "HOME-1" / "b")], "inside-root", None),
            (["home 1", str(self.tree)], "invalid-name", None),
        ]
        for args, kind, reason in cases:
            with self.subTest(args):
                out = self.bind(*args, status=1)
                self.assertEqual(out["error"]["kind"], kind)
                if reason:
                    self.assertEqual(out["error"]["details"]["reason"], reason)
                self.assertFalse((self.tree / ".shingi").exists())
                self.assertFalse((self.working / ".shingi").exists())
                self.assertFalse((self.working / "HOME-1" / "b" / ".shingi").exists())

    def test_refusals_details(self):
        out = self.bind("HOME-1/nope", str(self.tree), status=1)
        self.assertEqual(out["error"]["details"], {
            "unit": "HOME-1/nope", "missing": "HOME-1/nope", "cwd": str(self.tree), "reason": "not-a-unit", "marker": None,
        })
        missing = str(self.tmp / "missing")
        out = self.bind("HOME-1/a", missing, status=1)
        self.assertEqual(out["error"]["details"], {
            "unit": "HOME-1/a", "missing": None, "cwd": missing, "reason": "no-folder", "marker": None,
        })
        link = self.tmp / "into-root"
        link.symlink_to(self.working / "HOME-1" / "b")
        out = self.bind("HOME-1/a", str(link), status=1)
        self.assertEqual(out["error"]["kind"], "inside-root")
        self.assertEqual(out["error"]["details"], {"dir": str(self.working / "HOME-1" / "b"), "root": str(self.working)})

    def test_precedence(self):
        missing = str(self.tmp / "missing")
        self.assertEqual(self.bind("HOME-1/nope", missing, status=1)["error"]["details"]["reason"], "not-a-unit")
        (self.working / "HOME-1" / "a" / "uow.json").write_text("{}")
        self.assertEqual(self.bind("HOME-1/a", missing, status=1)["error"]["kind"], "unsupported-manifest")
        self.assertEqual(self.bind("HOME-1/b", str(self.working / "nope"), status=1)["error"]["details"]["reason"],
                         "no-folder")
        self.bind("HOME-1/b", str(self.tree))
        self.config.write_text("not toml [")
        self.assertEqual(self.bind("HOME-1/a", str(self.tree), status=1)["error"]["kind"], "invalid-rules")

    def test_passes_on_the_read_back_warnings(self):
        self.config.write_text('schema = 1\n[kind.group]\n')
        out = self.bind("HOME-1/a", str(self.tree))
        self.assertEqual([w["kind"] for w in out["warnings"]], ["undefined-kind"])

    def test_rewrites_the_gitignore(self):
        self.bind("HOME-1/a", str(self.tree))
        (self.tree / ".shingi" / ".gitignore").write_text("nothing\n")
        self.bind("HOME-1/a", str(self.tree))
        self.assertEqual((self.tree / ".shingi" / ".gitignore").read_text(), "*\n")

    def test_invalid_input(self):
        for inp, field, reason in [
            ({"unit": "HOME-1/a", "dir": str(self.tree), "replace": "yes"}, "/replace", "must be a boolean"),
            ({"unit": "HOME-1/a", "dir": str(self.tree) + "\0"}, "/dir", "holds a NUL"),
            ({"unit": "HOME-1/a", "dir": str(self.tree), "force": True}, "/force", "unknown field"),
            ({"unit": "HOME-1/a"}, "/dir", "required"),
        ]:
            with self.subTest(inp):
                code, out = self.shingi("bind", "-i", "-", stdin=json.dumps(inp).encode())
                self.assertEqual(code, 1, out)
                self.assertIn({"field": field, "reason": reason}, out["error"]["details"]["problems"])
        code, out = self.shingi("unbind", "-i", "-", stdin=b'{"dir": "rel"}')
        self.assertIn({"field": "/dir", "reason": "must be absolute"}, out["error"]["details"]["problems"])
        code, out = self.shingi("bind", "-i", "-", "--replace", stdin=b"{}")
        self.assertEqual((code, out["error"]["kind"]), (2, "usage"))

    def test_a_unit_with_an_unusable_manifest_is_refused(self):
        manifest = self.working / "HOME-1" / "a" / "uow.json"
        manifest.write_text("{}")
        out = self.bind("HOME-1/a", str(self.tree), status=1)
        self.assertEqual(out["error"]["kind"], "unsupported-manifest")
        self.assertEqual(out["error"]["details"], {"unit": "HOME-1/a", "path": str(manifest), "reason": "corrupt"})
        self.assertFalse((self.tree / ".shingi").exists())

    def test_input_dir_must_be_absolute(self):
        code, out = self.shingi("bind", "-i", "-", stdin=b'{"unit": "HOME-1/a", "dir": "rel"}')
        self.assertEqual(out["error"]["kind"], "invalid-input")
        self.assertIn({"field": "/dir", "reason": "must be absolute"}, out["error"]["details"]["problems"])


class UnbindTest(ShingiTestCase):
    def setUp(self):
        super().setUp()
        self.assertEqual(self.shingi("create", "HOME-1", "branch")[0], 0)
        self.tree = self.tmp / "worktree"
        (self.tree / "src").mkdir(parents=True)
        self.shingi_dir = self.tree / ".shingi"

    def test_removes_a_marker(self):
        self.assertEqual(self.shingi("bind", "HOME-1", str(self.tree))[0], 0)
        status, out = self.shingi("unbind", str(self.tree))
        self.assertEqual(status, 0, out)
        self.assertEqual(out["result"], {"dir": str(self.tree), "removed": [
            str(self.shingi_dir / "unit.json"), str(self.shingi_dir / ".gitignore"), str(self.shingi_dir),
        ]})
        self.assertFalse(self.shingi_dir.exists())
        self.assertTrue((self.tree / "src").is_dir())

    def test_removes_a_shingi_folder_without_unit_json_and_temp_files(self):
        self.shingi_dir.mkdir()
        (self.shingi_dir / ".gitignore").write_text("*\n")
        temp = self.shingi_dir / f".unit.json.{'0' * 32}.tmp"
        temp.write_text("{")
        status, out = self.shingi("unbind", cwd=self.tree)
        self.assertEqual(status, 0, out)
        self.assertEqual(out["result"]["removed"], [str(temp), str(self.shingi_dir / ".gitignore"), str(self.shingi_dir)])
        self.assertFalse(self.shingi_dir.exists())

    def test_anything_else_is_left_and_io(self):
        self.assertEqual(self.shingi("bind", "HOME-1", str(self.tree))[0], 0)
        (self.shingi_dir / "other").write_text("")
        status, out = self.shingi("unbind", str(self.tree))
        self.assertEqual(status, 1, out)
        self.assertEqual(out["error"]["kind"], "io")
        self.assertEqual(out["error"]["details"]["path"], str(self.shingi_dir))
        self.assertEqual(sorted(p.name for p in self.shingi_dir.iterdir()), ["other"])

    def test_no_marker_for_a_missing_folder_or_a_shingi_file(self):
        (self.tree / ".shingi").write_text("")
        for folder in (self.tmp / "missing", self.tree):
            with self.subTest(folder):
                status, out = self.shingi("unbind", str(folder))
                self.assertEqual(status, 1, out)
                self.assertEqual(out["error"]["details"]["reason"], "no-marker")

    def test_removed_order_with_temp_files(self):
        self.assertEqual(self.shingi("bind", "HOME-1", str(self.tree))[0], 0)
        temps = [f".gitignore.{'b' * 32}.tmp", f".unit.json.{'a' * 32}.tmp", f".gitignore.{'0' * 32}.tmp"]
        for name in temps:
            (self.shingi_dir / name).write_text("")
        status, out = self.shingi("unbind", str(self.tree))
        self.assertEqual(status, 0, out)
        self.assertEqual(out["result"]["removed"], [str(self.shingi_dir / name) for name in (
            "unit.json", f".gitignore.{'0' * 32}.tmp", f".gitignore.{'b' * 32}.tmp", f".unit.json.{'a' * 32}.tmp",
            ".gitignore",
        )] + [str(self.shingi_dir)])

    def test_no_marker_from_a_subdirectory(self):
        self.assertEqual(self.shingi("bind", "HOME-1", str(self.tree))[0], 0)
        status, out = self.shingi("unbind", cwd=self.tree / "src")
        self.assertEqual(status, 1)
        self.assertEqual(out["error"]["kind"], "not-found")
        self.assertEqual(out["error"]["details"], {
            "unit": None, "missing": None, "cwd": str(self.tree / "src"), "reason": "no-marker", "marker": None,
        })
        self.assertTrue((self.shingi_dir / "unit.json").exists())


class BrokenHooksTest(ShingiTestCase):
    def test_bind_and_unbind_work_with_a_broken_hooks_file(self):
        self.assertEqual(self.shingi("create", "HOME-1", "branch")[0], 0)
        self.hooks_file.parent.mkdir(parents=True, exist_ok=True)
        self.hooks_file.write_text("{")
        tree = self.tmp / "worktree"
        tree.mkdir()
        for args in (["bind", "HOME-1", str(tree)], ["unbind", str(tree)]):
            with self.subTest(args):
                status, out = self.shingi(*args)
                self.assertEqual(status, 0, out)
                self.assertEqual(out["warnings"], [])


if __name__ == "__main__":
    unittest.main()
