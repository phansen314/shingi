import unittest

from support import RULES, ShingiTestCase


class UndefinedKindTest(ShingiTestCase):
    def setUp(self):
        super().setUp()
        for path, kind in (("HOME-1", "group"), ("HOME-1/a", "branch"), ("HOME-1/b", "group")):
            status, out = self.shingi("create", path, kind)
            self.assertEqual(status, 0, out)
        # Remove the branch kind from the rules.
        rules = RULES.format(working=self.working).split("[kind.branch]")[0]
        self.config.write_text(rules.replace('"group", "branch"', '"group"'))

    def test_where_warns_and_reports_the_unit_as_usual(self):
        status, out = self.shingi("where", "HOME-1/a")
        self.assertEqual(status, 0, out)
        self.assertEqual(out["result"]["kind"], "branch")
        self.assertEqual(out["result"]["state"], "not-started")
        self.assertEqual(out["warnings"], [{
            "kind": "undefined-kind",
            "message": out["warnings"][0]["message"],
            "unit": "HOME-1/a",
            "ids": [],
            "details": {"kind": "branch"},
        }])

    def test_a_parent_doesnt_warn_about_its_children(self):
        _, out = self.shingi("where", "HOME-1")
        self.assertEqual(out["result"]["children"][0], {"path": "HOME-1/a", "kind": "branch"})
        self.assertEqual(out["warnings"], [])

    def test_list_warns_once_per_unit(self):
        _, out = self.shingi("list")
        self.assertEqual([(w["kind"], w["unit"]) for w in out["warnings"]], [("undefined-kind", "HOME-1/a")])

    def test_create_refuses_it(self):
        status, out = self.shingi("create", "HOME-2", "branch")
        self.assertEqual(status, 1)
        self.assertEqual(out["error"]["kind"], "unknown-kind")


if __name__ == "__main__":
    unittest.main()
