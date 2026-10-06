import shutil
import unittest

from support import ShingiTestCase


class ListTest(ShingiTestCase):
    def create(self, path, kind="group"):
        status, out = self.shingi("create", path, kind)
        self.assertEqual(status, 0, out)
        return out["result"]["unit"]

    def test_an_empty_working_root_has_no_units(self):
        status, out = self.shingi("list")
        self.assertEqual(status, 0, out)
        self.assertEqual(out, {"ok": True, "result": {"root": None, "units": []}, "warnings": []})

    def test_lists_every_unit_in_path_order(self):
        for path in ("a-b", "a", "a/c", "a/c/d", "z"):
            self.create(path)
        status, out = self.shingi("list")
        self.assertEqual(status, 0, out)
        self.assertEqual([u["path"] for u in out["result"]["units"]], ["a", "a/c", "a/c/d", "a-b", "z"])
        self.assertEqual(out["warnings"], [])

    def test_each_unit_is_as_where_reports_it(self):
        self.create("HOME-1")
        self.create("HOME-1/a", "branch")
        _, out = self.shingi("list")
        for unit in out["result"]["units"]:
            _, where = self.shingi("where", unit["path"])
            self.assertEqual(unit, where["result"])

    def test_lists_one_subtree(self):
        for path in ("HOME-1", "HOME-1/a", "HOME-1/a/x", "HOME-1/b", "HOME-2"):
            self.create(path)
        _, out = self.shingi("list", "HOME-1/a")
        self.assertEqual(out["result"]["root"], "HOME-1/a")
        self.assertEqual([u["path"] for u in out["result"]["units"]], ["HOME-1/a", "HOME-1/a/x"])

    def test_skips_working_material(self):
        self.create("HOME-1")
        material = self.working / "HOME-1" / "drafts" / "copy"
        material.mkdir(parents=True)
        (material / "uow.json").write_text("{}")  # inside material, a manifest is material too
        (self.working / ".hidden").mkdir()
        (self.working / ".hidden" / "uow.json").write_text("{}")
        (self.working / "plain" / "HOME-9").mkdir(parents=True)
        _, out = self.shingi("list")
        self.assertEqual([u["path"] for u in out["result"]["units"]], ["HOME-1"])

    def test_tasks_whose_unit_is_gone_are_orphans(self):
        unit = self.create("HOME-1")
        self.create("HOME-2")
        shutil.rmtree(self.working / "HOME-1")
        status, out = self.shingi("list")
        self.assertEqual(status, 0, out)
        self.assertEqual([u["path"] for u in out["result"]["units"]], ["HOME-2"])
        self.assertEqual([w["kind"] for w in out["warnings"]], ["orphan-task", "orphan-task"])
        self.assertEqual([w["ids"] for w in out["warnings"]], [[unit["start"]["id"]], [unit["done"]["id"]]])
        self.assertEqual(
            out["warnings"][0]["details"],
            {"folder": "/work/HOME-1", "source": "shingi-start", "shingi_unit": unit["id"]},
        )
        self.assertIsNone(out["warnings"][0]["unit"])

    def test_a_missing_root_is_not_found(self):
        status, out = self.shingi("list", "HOME-1")
        self.assertEqual(status, 1)
        self.assertEqual(out["error"]["kind"], "not-found")


if __name__ == "__main__":
    unittest.main()
