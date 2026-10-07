import os
import shutil
import unittest

from support import ShingiTestCase


class PartialTest(ShingiTestCase):
    """An error after create or adopt made something, before the unit exists, lists what it made."""

    def setUp(self):
        super().setUp()
        status, out = self.shingi("create", "HOME-1", "group")
        self.assertEqual(status, 0, out)
        self.parent = out["result"]["unit"]

    def failed(self, *args):
        status, out = self.shingi(*args)
        self.assertEqual(status, 1, out)
        return out["error"]

    def tasks_made(self, path):
        return sorted(t["id"] for t in self.koan("list", "--folder", f"/work/{path}")["tasks"])

    def test_koans_own_partial_from_create_batch(self):
        self.fake_koan(create_batch="partial")
        error = self.failed("create", "HOME-1/a", "group")
        self.assertEqual(error["kind"], "koan-failed")
        self.assertEqual(error["partial"], {
            "koan_folders": ["/work/HOME-1/a"], "tasks": self.tasks_made("HOME-1/a"), "blocked": None, "files": [],
        })
        self.assertFalse((self.working / "HOME-1" / "a").exists())

    def test_none_when_create_batch_made_nothing_or_its_outcome_is_unknown(self):
        for mode in ("error", "crash"):
            with self.subTest(mode):
                self.fake_koan(create_batch=mode)
                error = self.failed("create", "HOME-1/a", "group")
                self.assertEqual(error["kind"], "koan-failed")
                self.assertNotIn("partial", error)

    def test_block_failing(self):
        for mode in ("error", "crash"):
            with self.subTest(mode):
                self.fake_koan(block=mode)
                path = f"HOME-1/{mode}"
                error = self.failed("create", path, "group")
                self.assertEqual(error["kind"], "koan-failed")
                self.assertEqual(error["details"]["call"], "block")
                self.assertEqual(error["partial"], {
                    "koan_folders": [f"/work/{path}"], "tasks": self.tasks_made(path), "blocked": None, "files": [],
                })

    def test_a_failed_calls_warnings_come_with_the_partial(self):
        self.fake_koan(block="warn-error")
        status, out = self.shingi("create", "HOME-1/a", "group")
        self.assertEqual(status, 1)
        self.assertIn("partial", out["error"])
        self.assertEqual([(w["kind"], w["details"]["call"]) for w in out["warnings"]], [("koan-warning", "block")])

    def test_name_taken_making_the_folder(self):
        self.fake_koan(block_touch=self.working / "HOME-1" / "a")
        error = self.failed("create", "HOME-1/a", "group")
        self.assertEqual(error["kind"], "name-taken")
        self.assertEqual(error["details"], {"entry": "a", "type": "file"})
        start, done = self.tasks_made("HOME-1/a")
        self.assertEqual(error["partial"], {
            "koan_folders": ["/work/HOME-1/a"],
            "tasks": [start, done],
            "blocked": {"task": self.parent["done"]["id"], "added": [done]},
            "files": [],
        })

    def test_io_making_the_folder(self):
        (self.working / "HOME-1").chmod(0o555)
        self.addCleanup((self.working / "HOME-1").chmod, 0o755)
        error = self.failed("create", "HOME-1/a", "group")
        self.assertEqual(error["kind"], "io")
        self.assertEqual(error["details"], {"path": str(self.working / "HOME-1" / "a"), "code": "EACCES"})
        self.assertEqual(error["partial"]["tasks"], self.tasks_made("HOME-1/a"))
        self.assertEqual(error["partial"]["files"], [])

    def test_adopt_io_writing_the_notes(self):
        folder = self.working / "HOME-1" / "a"
        folder.mkdir()
        folder.chmod(0o555)
        self.addCleanup(folder.chmod, 0o755)
        error = self.failed("adopt", "HOME-1/a", "group")
        self.assertEqual(error["kind"], "io")
        self.assertEqual(error["details"]["path"], str(folder / "uow.md"))
        self.assertEqual(error["partial"]["files"], [])
        self.assertEqual(len(error["partial"]["tasks"]), 2)

    def test_adopt_unit_exists_linking_the_manifest(self):
        folder = self.working / "HOME-1" / "a"
        folder.mkdir()
        self.fake_koan(block_touch=folder / "uow.json")
        error = self.failed("adopt", "HOME-1/a", "group")
        self.assertEqual(error["kind"], "unit-exists")
        self.assertEqual(error["partial"]["files"], [str(folder / "uow.md")])
        self.assertEqual(error["partial"]["koan_folders"], ["/work/HOME-1/a"])

    def test_undoing_it_then_running_create_again(self):
        self.fake_koan(block_touch=self.working / "HOME-1" / "a")
        partial = self.failed("create", "HOME-1/a", "group")["partial"]
        for task in partial["tasks"]:
            self.koan("delete", str(task))
        for folder in reversed(partial["koan_folders"]):
            self.koan("delete-folder", folder)
        os.remove(self.working / "HOME-1" / "a")  # what was in the way
        del self.env["FAKE_KOAN_BLOCK_TOUCH"]
        status, out = self.shingi("create", "HOME-1/a", "group")
        self.assertEqual(status, 0, out)
        self.assertEqual(out["warnings"], [])
        self.assertEqual(self.koan_show(self.parent["done"]["id"])["blocked_by"],
                         [self.parent["start"]["id"], out["result"]["unit"]["done"]["id"]])

    def test_none_once_the_unit_exists(self):
        self.fake_koan(list="error")
        status, out = self.shingi("create", "HOME-2", "group")
        self.assertEqual(status, 0, out)
        self.assertEqual([w["kind"] for w in out["warnings"]], ["koan-failed"])


if __name__ == "__main__":
    unittest.main()
