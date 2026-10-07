import unittest

from support import ShingiTestCase


class ContextTest(ShingiTestCase):
    def setUp(self):
        super().setUp()
        self.units = {}
        for path, kind, title in (
            ("HOME-1", "group", "Payment retries"),
            ("HOME-1/foo-split", "group", "foo: seven stacked MRs"),
            ("HOME-1/foo-split/1-schema", "branch", "foo: schema changes"),
            ("HOME-1/foo-split/1-schema/sub", "group", "sub"),
        ):
            status, out = self.shingi("create", path, kind, "--title", title, "--notes", f"notes for {path}")
            self.assertEqual(status, 0, out)
            self.units[path] = out["result"]["unit"]

    def context(self, *args, **kwargs):
        status, out = self.shingi("context", *args, **kwargs)
        self.assertEqual(status, 0, out)
        return out

    def test_the_unit_is_as_where_reports_it(self):
        out = self.context("HOME-1/foo-split/1-schema")
        _, where = self.shingi("where", "HOME-1/foo-split/1-schema")
        self.assertEqual(out["result"]["unit"], where["result"])
        self.assertEqual(out["warnings"], [])

    def test_the_ancestor_chain(self):
        out = self.context("HOME-1/foo-split/1-schema")
        self.assertEqual(out["result"]["ancestors"], [
            {"path": "HOME-1", "id": self.units["HOME-1"]["id"], "kind": "group", "title": "Payment retries"},
            {"path": "HOME-1/foo-split", "id": self.units["HOME-1/foo-split"]["id"], "kind": "group",
             "title": "foo: seven stacked MRs"},
        ])

    def test_its_and_its_parents_notes(self):
        out = self.context("HOME-1/foo-split/1-schema")
        self.assertEqual(out["result"]["notes"], "# foo: schema changes\n\nnotes for HOME-1/foo-split/1-schema\n")
        self.assertEqual(out["result"]["parent_notes"], "# foo: seven stacked MRs\n\nnotes for HOME-1/foo-split\n")

    def test_a_top_level_unit(self):
        out = self.context("HOME-1")
        self.assertEqual(out["result"]["ancestors"], [])
        self.assertIsNone(out["result"]["parent_notes"])

    def test_its_open_tasks_only_its_own(self):
        unit = self.units["HOME-1/foo-split/1-schema"]
        folder = unit["koan_folder"]
        work = self.koan("create", "Schema changes", "--folder", folder, "--blocked-by", str(unit["start"]["id"]))
        finished = self.koan("create", "Already done", "--folder", folder)
        self.koan("done", str(finished["id"]))
        out = self.context("HOME-1/foo-split/1-schema")
        tasks = out["result"]["tasks"]
        self.assertEqual([t["id"] for t in tasks], [unit["start"]["id"], unit["done"]["id"], work["id"]])
        self.assertEqual(tasks[0]["tags"], ["shingi", "shingi-start"])
        self.assertEqual(tasks[2], {
            "id": work["id"], "title": "Schema changes", "readiness": "blocked",
            "blocking": [unit["start"]["id"]], "tags": [], "notes_path": tasks[2]["notes_path"],
        })

    def test_from_the_current_directory(self):
        out = self.context(cwd=self.working / "HOME-1" / "foo-split")
        self.assertEqual(out["result"]["unit"]["path"], "HOME-1/foo-split")

    def test_an_ancestors_broken_manifest_is_null_without_a_warning(self):
        (self.working / "HOME-1" / "uow.json").write_text("{")
        out = self.context("HOME-1/foo-split")
        self.assertEqual(out["result"]["ancestors"][0], {"path": "HOME-1", "id": None, "kind": None, "title": "Payment retries"})
        self.assertEqual(out["warnings"], [])

    def test_koan_failing_nulls_the_tasks(self):
        self.fake_koan(list="error")
        out = self.context("HOME-1/foo-split")
        self.assertIsNone(out["result"]["tasks"])
        self.assertIsNone(out["result"]["unit"]["start"])
        self.assertEqual([w["kind"] for w in out["warnings"]], ["koan-failed"])
        self.assertEqual(out["result"]["notes"], "# foo: seven stacked MRs\n\nnotes for HOME-1/foo-split\n")

    def test_its_own_broken_manifest(self):
        (self.working / "HOME-1" / "uow.json").write_text("{")
        out = self.context("HOME-1")
        self.assertIsNone(out["result"]["tasks"])
        self.assertEqual([w["kind"] for w in out["warnings"]], ["unsupported-manifest"])

    def test_not_a_unit(self):
        status, out = self.shingi("context", "HOME-9")
        self.assertEqual(status, 1)
        self.assertEqual(out["error"]["kind"], "not-found")


if __name__ == "__main__":
    unittest.main()
