import unittest

from support import ShingiTestCase


class NestingTest(ShingiTestCase):
    def create(self, path, kind="group"):
        status, out = self.shingi("create", path, kind)
        self.assertEqual(status, 0, out)
        return out["result"]["unit"]

    def test_two_children_link_to_their_parent(self):
        parent = self.create("HOME-1")
        a = self.create("HOME-1/a", "branch")
        b = self.create("HOME-1/b", "branch")

        for child in (a, b):
            self.assertEqual(child["parent"], "HOME-1")
            self.assertEqual(child["koan_folder"], "/work/HOME-1/" + child["path"].split("/")[-1])
            self.assertEqual(self.koan_show(child["start"]["id"])["blocked_by"], [parent["start"]["id"]])
            self.assertEqual(self.koan_show(child["done"]["id"])["blocked_by"], [child["start"]["id"]])
        self.assertEqual(
            self.koan_show(parent["done"]["id"])["blocked_by"],
            sorted([parent["start"]["id"], a["done"]["id"], b["done"]["id"]]),
        )

        _, out = self.shingi("where", "HOME-1")
        self.assertEqual(
            out["result"]["children"],
            [{"path": "HOME-1/a", "kind": "branch"}, {"path": "HOME-1/b", "kind": "branch"}],
        )

    def test_children_wait_for_their_parent_to_start(self):
        parent = self.create("HOME-1")
        a = self.create("HOME-1/a")
        self.assertEqual(a["start"]["readiness"], "blocked")

        self.koan("done", str(parent["start"]["id"]))
        _, out = self.shingi("where", "HOME-1/a")
        self.assertEqual(out["result"]["start"]["readiness"], "ready")

    def test_a_done_parent_is_left_alone(self):
        parent = self.create("HOME-1")
        self.koan("done", str(parent["start"]["id"]))
        self.koan("done", str(parent["done"]["id"]))
        status, out = self.shingi("create", "HOME-1/late", "group")
        self.assertEqual(status, 0, out)
        self.assertEqual(self.koan_show(parent["done"]["id"])["blocked_by"], [parent["start"]["id"]])
        self.assertEqual(out["warnings"], [{
            "kind": "parent-done",
            "message": out["warnings"][0]["message"],
            "unit": "HOME-1/late",
            "ids": [parent["done"]["id"]],
            "details": {"parent": "HOME-1"},
        }])

    def test_an_open_parent_gives_no_warning(self):
        self.create("HOME-1")
        _, out = self.shingi("create", "HOME-1/a", "group")
        self.assertEqual(out["warnings"], [])

    def test_a_missing_parent_is_parent_not_found(self):
        status, out = self.shingi("create", "HOME-1/a/b", "group")
        self.assertEqual(status, 1)
        self.assertEqual(out["error"]["kind"], "parent-not-found")
        self.assertEqual(out["error"]["details"], {"parent": "HOME-1/a", "missing": "HOME-1"})
        self.assertEqual(list(self.working.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
