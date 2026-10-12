import unittest

from support import ShingiTestCase


class DeleteTest(ShingiTestCase):
    """delete makes a unit a plain folder again: its tasks and manifest go, its files stay."""

    def setUp(self):
        super().setUp()
        self.units = {}
        for path in ("HOME-1", "HOME-1/a", "HOME-1/b"):
            status, out = self.shingi("create", path, "group", "--notes", f"notes for {path}")
            self.assertEqual(status, 0, out)
            self.units[path] = out["result"]["unit"]
        self.folder = self.working / "HOME-1" / "a"

    def blocked_by(self, task_id):
        return self.koan("show", str(task_id))["task"]["blocked_by"]

    def test_removes_the_tasks_and_the_manifest_and_nothing_else(self):
        a, parent = self.units["HOME-1/a"], self.units["HOME-1"]
        work = self.koan("create", "Schema changes", "--folder", a["koan_folder"])["task"]["id"]
        (self.folder / "drafts").mkdir()
        (self.folder / "drafts" / "plan.txt").write_text("the plan")
        status, out = self.shingi("delete", "HOME-1/a")
        self.assertEqual(status, 0, out)
        self.assertEqual(out, {"ok": True, "warnings": [], "result": {
            "path": "HOME-1/a",
            "koan_folder": "/shingi/HOME-1/a",
            "working_folder": str(self.folder),
            "tasks": sorted([a["start"]["id"], a["done"]["id"], work]),
            "unblocked": [parent["done"]["id"]],
        }})
        self.assertEqual(sorted(p.name for p in self.folder.iterdir()), ["drafts", "uow.md"])
        self.assertEqual((self.folder / "uow.md").read_text(), "# a\n\nnotes for HOME-1/a\n")
        self.assertEqual((self.folder / "drafts" / "plan.txt").read_text(), "the plan")

    def test_the_parent_no_longer_waits_on_it(self):
        parent = self.units["HOME-1"]
        self.shingi("delete", "HOME-1/a")
        self.assertEqual(self.blocked_by(parent["done"]["id"]),
                         [parent["start"]["id"], self.units["HOME-1/b"]["done"]["id"]])

    def test_the_tree_is_clean_afterwards(self):
        self.shingi("delete", "HOME-1/a")
        status, out = self.shingi("list")
        self.assertEqual([u["path"] for u in out["result"]["units"]], ["HOME-1", "HOME-1/b"])
        self.assertEqual(out["warnings"], [])
        self.assertEqual(self.shingi("where", "HOME-1")[1]["result"]["children"], [{"path": "HOME-1/b", "kind": "group"}])

    def test_again_is_not_found(self):
        self.shingi("delete", "HOME-1/a")
        status, out = self.shingi("delete", "HOME-1/a")
        self.assertEqual((status, out["error"]["kind"]), (1, "not-found"))

    def test_adopt_makes_it_a_unit_again_with_its_notes(self):
        self.shingi("delete", "HOME-1/a")
        self.assertEqual(self.shingi("create", "HOME-1/a", "branch")[1]["error"]["kind"], "name-taken")
        status, out = self.shingi("adopt", "HOME-1/a", "branch")
        self.assertEqual(status, 0, out)
        unit = out["result"]["unit"]
        self.assertEqual((unit["kind"], unit["title"]), ("branch", "a"))
        self.assertNotEqual(unit["id"], self.units["HOME-1/a"]["id"])
        self.assertEqual(self.shingi("list")[1]["warnings"], [])

    def test_refuses_a_unit_with_children(self):
        status, out = self.shingi("delete", "HOME-1")
        self.assertEqual(status, 1)
        self.assertEqual(out["error"]["kind"], "has-children")
        self.assertEqual(out["error"]["details"], {"unit": "HOME-1", "children": ["HOME-1/a", "HOME-1/b"]})
        self.assertEqual(self.shingi("list")[1]["warnings"], [])
        self.assertTrue((self.working / "HOME-1" / "uow.json").is_file())

    def test_a_top_level_unit(self):
        for path in ("HOME-1/a", "HOME-1/b", "HOME-1"):
            status, out = self.shingi("delete", path)
            self.assertEqual(status, 0, out)
        self.assertEqual(out["result"]["unblocked"], [])
        self.assertEqual(self.shingi("list")[1], {"ok": True, "result": {"root": None, "units": []}, "warnings": []})

    def test_a_broken_manifest_is_no_obstacle(self):
        (self.folder / "uow.json").write_text("{")
        status, out = self.shingi("delete", "HOME-1/a")
        self.assertEqual(status, 0, out)
        self.assertEqual(len(out["result"]["tasks"]), 2)
        self.assertEqual(self.shingi("list")[1]["warnings"], [])

    def test_a_koan_folder_already_gone(self):
        self.koan("delete-folder", "/shingi/HOME-1/a", "--recursive")
        status, out = self.shingi("delete", "HOME-1/a")
        self.assertEqual(status, 0, out)
        self.assertEqual((out["result"]["tasks"], out["result"]["unblocked"]), ([], []))
        self.assertFalse((self.folder / "uow.json").exists())

    def test_koan_failing_leaves_the_unit(self):
        for mode, error in (("error", "io"), ("crash", None)):
            with self.subTest(mode):
                self.fake_koan(delete_folder=mode)
                status, out = self.shingi("delete", "HOME-1/a")
                self.assertEqual((status, out["error"]["kind"]), (1, "koan-failed"))
                self.assertEqual(out["error"]["details"]["call"], "delete-folder")
                self.assertEqual(out["error"]["details"]["error"] and out["error"]["details"]["error"]["kind"], error)
                self.assertNotIn("partial", out["error"])
                self.assertTrue((self.folder / "uow.json").is_file())

    def test_run_again_after_the_manifest_couldnt_be_removed(self):
        self.folder.chmod(0o555)
        status, out = self.shingi("delete", "HOME-1/a")
        self.folder.chmod(0o755)
        self.assertEqual((status, out["error"]["kind"]), (1, "io"))
        self.assertEqual(out["error"]["details"], {"path": str(self.folder / "uow.json"), "code": "EACCES"})
        listed = self.shingi("list", "HOME-1/a")[1]
        self.assertEqual([w["kind"] for w in listed["warnings"]], ["missing-task", "missing-task"])
        status, out = self.shingi("delete", "HOME-1/a")
        self.assertEqual(status, 0, out)
        self.assertEqual(self.shingi("list")[1]["warnings"], [])

    def test_koans_warnings_are_passed_on(self):
        self.fake_koan(delete_folder="warn")
        status, out = self.shingi("delete", "HOME-1/a")
        self.assertEqual(status, 0, out)
        self.assertEqual([(w["kind"], w["details"]["call"]) for w in out["warnings"]], [("koan-warning", "delete-folder")])

    def test_the_path_is_checked(self):
        self.assertEqual(self.shingi("delete", "HOME-1/-a")[1]["error"]["kind"], "invalid-name")
        self.assertEqual(self.shingi("delete", "HOME-9")[1]["error"]["kind"], "not-found")
        status, out = self.shingi("delete", cwd=self.folder)
        self.assertEqual((status, out["error"]["kind"]), (2, "usage"))
        status, out = self.shingi("delete", "-i", "-", stdin=b'{"cwd": "/x"}')
        self.assertEqual([p["field"] for p in out["error"]["details"]["problems"]], ["/cwd", "/unit"])


if __name__ == "__main__":
    unittest.main()
