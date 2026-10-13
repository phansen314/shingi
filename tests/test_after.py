import json
import unittest

from support import ShingiTestCase


class AfterTest(ShingiTestCase):
    """create's --after: the new unit's start task waits on each named unit's done task."""

    def create(self, *args):
        status, out = self.shingi("create", *args)
        self.assertEqual(status, 0, out)
        return out["result"]["unit"]

    def refused(self, *args, stdin=b""):
        status, out = self.shingi("create", *args, stdin=stdin)
        self.assertEqual(status, 1, out)
        return out["error"]

    def test_the_start_task_waits_on_each_done_task(self):
        story = self.create("HOME-1", "group")
        setup = self.create("HOME-1/setup", "group")
        other = self.create("HOME-2", "group")
        status, out = self.shingi("create", "HOME-1/research", "group", "--after", "HOME-1/setup,HOME-2")
        self.assertEqual(status, 0, out)
        self.assertEqual(out["warnings"], [])
        research = out["result"]["unit"]
        self.assertEqual(
            self.koan_show(research["start"]["id"])["blocked_by"],
            [story["start"]["id"], setup["done"]["id"], other["done"]["id"]],
        )
        self.assertEqual(self.koan_show(research["done"]["id"])["blocked_by"], [research["start"]["id"]])

    def test_a_repeated_option_adds_to_the_list(self):
        a, b, c = (self.create(name, "group") for name in ("A", "B", "C"))
        unit = self.create("D", "group", "--after", "B", "--after=C,A")
        # koan keeps a task's blockers in ID order, whatever order they were given in.
        self.assertEqual(
            self.koan_show(unit["start"]["id"])["blocked_by"], [a["done"]["id"], b["done"]["id"], c["done"]["id"]]
        )

    def test_the_four_phase_story(self):
        self.create("HOME-1", "group")
        self.create("HOME-1/setup", "group")
        research = self.create("HOME-1/research", "group", "--after", "HOME-1/setup")
        implementation = self.create("HOME-1/implementation", "group", "--after", "HOME-1/research")
        branch = self.create("HOME-1/implementation/1-schema", "branch")
        review = self.create("HOME-1/review", "group", "--after", "HOME-1/implementation")
        self.assertIn(research["done"]["id"], self.koan_show(implementation["start"]["id"])["blocked_by"])
        self.assertEqual(self.koan_show(branch["start"]["id"])["blocked_by"], [implementation["start"]["id"]])
        self.assertIn(branch["done"]["id"], self.koan_show(implementation["done"]["id"])["blocked_by"])
        self.assertIn(implementation["done"]["id"], self.koan_show(review["start"]["id"])["blocked_by"])

    def test_from_input(self):
        a = self.create("A", "group")
        inp = json.dumps({"path": "B", "kind": "group", "after": ["A"]}).encode()
        status, out = self.shingi("create", "-i", "-", stdin=inp)
        self.assertEqual(status, 0, out)
        self.assertEqual(self.koan_show(out["result"]["unit"]["start"]["id"])["blocked_by"], [a["done"]["id"]])

    def test_an_empty_list_is_no_list(self):
        status, out = self.shingi("create", "-i", "-", stdin=b'{"path": "A", "kind": "group", "after": []}')
        self.assertEqual(status, 0, out)
        self.assertEqual(self.koan_show(out["result"]["unit"]["start"]["id"])["blocked_by"], [])

    def test_a_done_unit_is_linked_without_a_warning(self):
        a = self.create("A", "group")
        self.koan("done", str(a["start"]["id"]))
        self.koan("done", str(a["done"]["id"]))
        status, out = self.shingi("create", "B", "group", "--after", "A")
        self.assertEqual(status, 0, out)
        self.assertEqual(out["warnings"], [])
        unit = out["result"]["unit"]
        self.assertEqual(self.koan_show(unit["start"]["id"])["blocked_by"], [a["done"]["id"]])
        self.assertEqual(unit["start"]["readiness"], "ready")

    def test_refuses_a_bad_name(self):
        self.create("A", "group")
        error = self.refused("B", "group", "--after", "A,bad-")
        self.assertEqual(error["kind"], "invalid-name")
        self.assertEqual(
            error["details"], {"field": "/after/1", "path": "bad-", "index": 0, "segment": "bad-", "reason": "hyphen"}
        )
        self.assertFalse((self.working / "B").exists())

    def test_an_empty_piece_is_a_bad_name(self):
        self.create("A", "group")
        for value in ("", "A,,B"):
            with self.subTest(value):
                error = self.refused("B", "group", "--after", value)
                self.assertEqual(error["kind"], "invalid-name")
                self.assertEqual(error["details"]["reason"], "empty")

    def test_the_units_own_name_is_checked_first(self):
        error = self.refused("bad-", "group", "--after", "also bad")
        self.assertEqual(error["details"]["field"], "/path")

    def test_refuses_the_unit_itself_and_its_ancestors(self):
        self.create("HOME-1", "group")
        self.create("HOME-1/a", "group")
        for after, relation in (("HOME-1/a/b", "self"), ("HOME-1", "ancestor"), ("HOME-1/a", "ancestor")):
            with self.subTest(after):
                error = self.refused("HOME-1/a/b", "group", "--after", after)
                self.assertEqual(error["kind"], "after-lineage")
                self.assertEqual(error["details"], {"field": "/after/0", "after": after, "relation": relation})
        self.assertFalse((self.working / "HOME-1/a/b").exists())

    def test_a_name_that_only_starts_the_same_is_no_ancestor(self):
        self.create("HOME-1", "group")
        self.create("HOME-10", "group", "--after", "HOME-1")

    def test_lineage_is_checked_before_the_parent(self):
        error = self.refused("HOME-1/a", "group", "--after", "HOME-1")
        self.assertEqual(error["kind"], "after-lineage")

    def test_refuses_a_path_that_is_not_a_unit(self):
        self.create("HOME-1", "group")
        (self.working / "HOME-1/plain").mkdir()
        error = self.refused("HOME-2", "group", "--after", "HOME-1,HOME-1/plain/x")
        self.assertEqual(error["kind"], "after-not-found")
        self.assertEqual(
            error["details"], {"field": "/after/1", "after": "HOME-1/plain/x", "missing": "HOME-1/plain"}
        )
        self.assertFalse((self.working / "HOME-2").exists())
        self.assertEqual(self.shingi("list")[1]["warnings"], [])  # no tasks were made

    def test_the_new_name_is_checked_before_after_is_looked_up(self):
        self.create("HOME-1", "group")
        self.assertEqual(self.refused("HOME-1", "group", "--after", "HOME-9")["kind"], "unit-exists")

    def test_refuses_a_path_given_twice(self):
        self.create("A", "group")
        error = self.refused("B", "group", "--after", "A,A")
        self.assertEqual(error["kind"], "invalid-input")
        self.assertEqual(error["details"]["problems"], [{"field": "/after/1", "reason": "names a path already given"}])

    def test_refuses_an_after_that_is_not_an_array_of_strings(self):
        error = self.refused("-i", "-", stdin=b'{"path": "B", "kind": "group", "after": "A"}')
        self.assertEqual(error["details"]["problems"], [{"field": "/after", "reason": "must be an array"}])
        error = self.refused("-i", "-", stdin=b'{"path": "B", "kind": "group", "after": ["A", 1]}')
        self.assertEqual(error["details"]["problems"], [{"field": "/after/1", "reason": "must be a string"}])

    def test_an_unusable_manifest_leaves_the_link_out(self):
        a = self.create("A", "group")
        self.create("B", "group")
        (self.working / "B/uow.json").write_text("{")
        status, out = self.shingi("create", "C", "group", "--after", "B,A")
        self.assertEqual(status, 0, out)
        self.assertEqual(
            [(w["kind"], w["unit"], w["ids"], w["details"]) for w in out["warnings"]],
            [("after-unlinked", "C", [], {"after": "B", "reason": "unsupported-manifest"})],
        )
        self.assertEqual(self.koan_show(out["result"]["unit"]["start"]["id"])["blocked_by"], [a["done"]["id"]])

    def test_a_missing_done_task_leaves_the_link_out(self):
        a, b = self.create("A", "group"), self.create("B", "group")
        self.koan("delete", str(a["done"]["id"]))
        self.koan("delete", str(b["done"]["id"]))
        status, out = self.shingi("create", "C", "group", "--after", "B,A")
        self.assertEqual(status, 0, out)
        self.assertEqual(
            [(w["kind"], w["details"]) for w in out["warnings"]],
            [
                ("after-unlinked", {"after": "A", "reason": "missing-task"}),
                ("after-unlinked", {"after": "B", "reason": "missing-task"}),
            ],
        )
        self.assertEqual(self.koan_show(out["result"]["unit"]["start"]["id"])["blocked_by"], [])

    def test_koan_failing_to_find_the_tasks_makes_nothing(self):
        self.create("A", "group")
        self.fake_koan(list="error")
        error = self.refused("B", "group", "--after", "A")
        self.assertEqual(error["kind"], "koan-failed")
        self.assertNotIn("partial", error)
        self.assertFalse((self.working / "B").exists())

    def test_a_cycle_through_links_already_there_is_koans_to_refuse(self):
        self.create("HOME-1", "group")
        implementation = self.create("HOME-1/implementation", "group")
        self.create("HOME-1/followup", "group", "--after", "HOME-1/implementation")
        error = self.refused("HOME-1/implementation/x", "branch", "--after", "HOME-1/followup")
        self.assertEqual(error["kind"], "koan-failed")
        self.assertEqual(error["details"]["call"], "block")
        self.assertEqual((error["details"]["error"]["kind"], error["details"]["error"]["rule"]), ("conflict", "cycle"))
        self.assertEqual(len(error["partial"]["tasks"]), 2)
        self.assertIsNone(error["partial"]["blocked"])
        self.assertFalse((self.working / "HOME-1/implementation/x").exists())
        self.assertNotIn(error["partial"]["tasks"][1], self.koan_show(implementation["done"]["id"])["blocked_by"])


class AdoptAfterTest(ShingiTestCase):
    """adopt takes no after."""

    def test_the_option_is_unknown(self):
        (self.working / "A").mkdir()
        status, out = self.shingi("adopt", "A", "group", "--after", "B")
        self.assertEqual(status, 2, out)
        self.assertEqual(out["error"]["kind"], "usage")

    def test_the_field_is_unknown(self):
        (self.working / "A").mkdir()
        status, out = self.shingi("adopt", "-i", "-", stdin=b'{"path": "A", "kind": "group", "after": []}')
        self.assertEqual(status, 1, out)
        self.assertEqual(out["error"]["details"]["problems"], [{"field": "/after", "reason": "unknown field"}])
        self.assertFalse((self.working / "A/uow.json").exists())


if __name__ == "__main__":
    unittest.main()
