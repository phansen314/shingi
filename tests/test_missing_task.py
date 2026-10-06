import shutil
import unittest

from support import ShingiTestCase


class MissingTaskTest(ShingiTestCase):
    def create(self, path, kind="group"):
        status, out = self.shingi("create", path, kind)
        self.assertEqual(status, 0, out)
        return out["result"]["unit"]

    def test_a_deleted_task_is_null_and_warned(self):
        unit = self.create("HOME-1")
        self.koan("delete", str(unit["done"]["id"]))
        status, out = self.shingi("where", "HOME-1")
        self.assertEqual(status, 0, out)
        self.assertIsNone(out["result"]["done"])
        self.assertIsNone(out["result"]["state"])
        self.assertEqual(out["result"]["start"]["id"], unit["start"]["id"])
        self.assertEqual(out["warnings"], [{
            "kind": "missing-task",
            "message": out["warnings"][0]["message"],
            "unit": "HOME-1",
            "ids": [],
            "details": {"role": "done"},
        }])

    def test_a_copied_unit_is_missing_both(self):
        self.create("HOME-1")
        shutil.copytree(self.working / "HOME-1", self.working / "HOME-2")
        status, out = self.shingi("where", "HOME-2")
        self.assertEqual(status, 0, out)
        self.assertEqual([w["details"]["role"] for w in out["warnings"]], ["start", "done"])

    def test_list_warns_per_unit_and_role(self):
        a = self.create("HOME-1")
        self.create("HOME-2")
        b = self.create("HOME-3")
        self.koan("delete", str(b["done"]["id"]))
        self.koan("delete", str(a["start"]["id"]))
        _, out = self.shingi("list")
        self.assertEqual(
            [(w["kind"], w["unit"], w["details"]["role"]) for w in out["warnings"]],
            [("missing-task", "HOME-1", "start"), ("missing-task", "HOME-3", "done")],
        )

    def test_not_warned_for_an_unusable_manifest(self):
        self.create("HOME-1")
        (self.working / "HOME-1" / "uow.json").write_text("{")
        _, out = self.shingi("where", "HOME-1")
        self.assertEqual([w["kind"] for w in out["warnings"]], ["unsupported-manifest"])


if __name__ == "__main__":
    unittest.main()
