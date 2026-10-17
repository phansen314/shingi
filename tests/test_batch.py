import json
import os
import shutil
import subprocess
import unittest
from unittest import mock

from support import ShingiTestCase

from shingi import cli, operations

STORY = [  # out of order on purpose: the order made follows the paths, not the input
    {"path": "HOME-1/review", "kind": "group", "after": ["HOME-1/implementation"]},
    {"path": "HOME-1/implementation/2-model", "kind": "branch", "after": ["HOME-1/implementation/1-schema"]},
    {"path": "HOME-1", "kind": "group", "title": "Payment retries", "notes": "Story: retry payments."},
    {"path": "HOME-1/research", "kind": "group", "after": ["HOME-1/setup"]},
    {"path": "HOME-1/implementation/1-schema", "kind": "branch"},
    {"path": "HOME-1/setup", "kind": "group"},
    {"path": "HOME-1/implementation", "kind": "group", "after": ["HOME-1/research"]},
]


class BatchTestCase(ShingiTestCase):
    def batch(self, *entries, **inp):
        """Run create-batch on `entries`, or on `inp` whole; return its exit status and envelope."""
        payload = inp if inp else {"units": list(entries)}
        return self.shingi("create-batch", "-i", "-", stdin=json.dumps(payload).encode())

    def made(self, *entries):
        status, out = self.batch(*entries)
        self.assertEqual(status, 0, out)
        return {unit["path"]: unit for unit in out["result"]["units"]}, out["warnings"]

    def refused(self, *entries, **inp):
        status, out = self.batch(*entries, **inp)
        self.assertEqual(status, 1, out)
        return out["error"]

    def create(self, *args):
        status, out = self.shingi("create", *args)
        self.assertEqual(status, 0, out)
        return out["result"]["unit"]

    def blocked_by(self, task):
        return self.koan_show(task["id"])["blocked_by"]


class CreateBatchTest(BatchTestCase):
    """create-batch: several units in one call, linked to one another and to the units already there."""

    def test_the_four_phase_story(self):
        units, warnings = self.made(*STORY)
        self.assertEqual(warnings, [])
        self.assertEqual(list(units), sorted(e["path"] for e in STORY))
        story, setup, research = units["HOME-1"], units["HOME-1/setup"], units["HOME-1/research"]
        implementation, review = units["HOME-1/implementation"], units["HOME-1/review"]
        schema, model = units["HOME-1/implementation/1-schema"], units["HOME-1/implementation/2-model"]
        start, done = lambda u: u["start"], lambda u: u["done"]
        ids = lambda *tasks: sorted(t["id"] for t in tasks)
        self.assertEqual(self.blocked_by(start(story)), [])
        self.assertEqual(self.blocked_by(start(setup)), ids(start(story)))
        self.assertEqual(self.blocked_by(start(research)), ids(start(story), done(setup)))
        self.assertEqual(self.blocked_by(start(implementation)), ids(start(story), done(research)))
        self.assertEqual(self.blocked_by(start(schema)), ids(start(implementation)))
        self.assertEqual(self.blocked_by(start(model)), ids(start(implementation), done(schema)))
        self.assertEqual(self.blocked_by(start(review)), ids(start(story), done(implementation)))
        self.assertEqual(self.blocked_by(done(implementation)), ids(start(implementation), done(schema), done(model)))
        self.assertEqual(
            self.blocked_by(done(story)),
            ids(start(story), done(setup), done(research), done(implementation), done(review)),
        )
        self.assertEqual(story["title"], "Payment retries")
        self.assertEqual((self.working / "HOME-1/uow.md").read_text(), "# Payment retries\n\nStory: retry payments.\n")
        self.assertEqual(setup["title"], "setup")
        self.assertEqual(start(setup)["readiness"], "blocked")
        self.assertEqual(units["HOME-1/implementation"]["children"], [
            {"path": "HOME-1/implementation/1-schema", "kind": "branch"},
            {"path": "HOME-1/implementation/2-model", "kind": "branch"},
        ])

    def test_the_order_made_follows_from_the_paths(self):
        units, _ = self.made(*STORY)
        roles = {}
        for path, unit in units.items():
            roles[unit["start"]["id"]] = (path, "start")
            roles[unit["done"]["id"]] = (path, "done")
        self.assertEqual([roles[i] for i in sorted(roles)], [
            ("HOME-1", "start"),
            ("HOME-1/setup", "start"), ("HOME-1/setup", "done"),
            ("HOME-1/research", "start"), ("HOME-1/research", "done"),
            ("HOME-1/implementation", "start"),
            ("HOME-1/implementation/1-schema", "start"), ("HOME-1/implementation/1-schema", "done"),
            ("HOME-1/implementation/2-model", "start"), ("HOME-1/implementation/2-model", "done"),
            ("HOME-1/implementation", "done"),
            ("HOME-1/review", "start"), ("HOME-1/review", "done"),
            ("HOME-1", "done"),
        ])

    def test_adding_to_units_already_there(self):
        story = self.create("HOME-1", "group")
        setup = self.create("HOME-1/setup", "group")
        other = self.create("HOME-2", "group")
        units, warnings = self.made(
            {"path": "HOME-1/research/x", "kind": "branch"},
            {"path": "HOME-1/research", "kind": "group", "after": ["HOME-1/setup", "HOME-2"]},
            {"path": "HOME-1/later", "kind": "group", "after": ["HOME-1/research"]},
        )
        self.assertEqual(warnings, [])
        research, x, later = units["HOME-1/research"], units["HOME-1/research/x"], units["HOME-1/later"]
        self.assertEqual(
            self.blocked_by(research["start"]),
            sorted([story["start"]["id"], setup["done"]["id"], other["done"]["id"]]),
        )
        self.assertEqual(self.blocked_by(x["start"]), [research["start"]["id"]])
        self.assertEqual(self.blocked_by(later["start"]), sorted([story["start"]["id"], research["done"]["id"]]))
        # One block on the parent already there, with its new children's done tasks; not x's.
        self.assertEqual(
            self.blocked_by(story["done"]),
            sorted([story["start"]["id"], setup["done"]["id"], research["done"]["id"], later["done"]["id"]]),
        )

    def test_an_empty_batch_does_nothing(self):
        self.fake_koan(list="error", create_batch="error", block="error")
        status, out = self.batch()
        self.assertEqual((status, out["result"], out["warnings"]), (0, {"units": []}, []))

    def test_takes_its_input_only_from_input(self):
        status, out = self.shingi("create-batch")
        self.assertEqual(status, 2, out)
        self.assertEqual(out["error"]["kind"], "usage")
        self.assertNotIn("argument", out["error"]["details"]["problems"][0])

    def test_takes_no_arguments(self):
        status, out = self.shingi("create-batch", "HOME-1")
        self.assertEqual(status, 2, out)
        self.assertEqual(out["error"]["kind"], "usage")
        self.assertEqual(out["error"]["details"]["problems"][0]["argument"], "HOME-1")

    def test_help(self):
        proc = subprocess.run([shutil.which("shingi"), "create-batch", "--help"], env=self.env, capture_output=True)
        self.assertEqual(proc.returncode, 0)
        self.assertTrue(proc.stdout.decode().startswith("Usage: shingi create-batch -i <file>\n\n"))

    def test_reading_back_fails_with_one_warning(self):
        self.fake_koan(list="error")  # nothing is already there, so only the read-back lists
        status, out = self.batch({"path": "A", "kind": "group"}, {"path": "A/b", "kind": "group"})
        self.assertEqual(status, 0, out)
        self.assertEqual([(w["kind"], w["unit"]) for w in out["warnings"]], [("koan-failed", None)])
        self.assertEqual([(u["start"], u["done"]) for u in out["result"]["units"]], [(None, None), (None, None)])
        self.assertTrue((self.working / "A/b/uow.json").is_file())


class BatchInputTest(BatchTestCase):
    def problems(self, **inp):
        error = self.refused(**inp)
        self.assertEqual(error["kind"], "invalid-input")
        return error["details"]["problems"]

    def test_units_is_an_array_of_at_most_500(self):
        self.assertEqual(self.problems(other=1), [
            {"field": "/other", "reason": "unknown field"}, {"field": "/units", "reason": "required"},
        ])
        self.assertEqual(self.problems(units={}), [{"field": "/units", "reason": "must be an array"}])
        units = [{"path": f"U{i}", "kind": "group"} for i in range(501)]
        self.assertEqual(self.problems(units=units), [{"field": "/units", "reason": "holds over 500 entries"}])

    def test_each_entry_is_checked_as_creates_input(self):
        self.assertEqual(self.problems(units=[{"path": "A", "kind": "group"}, 1, {"path": "B", "after": "A", "x": 1}]), [
            {"field": "/units/1", "reason": "must be an object"},
            {"field": "/units/2/after", "reason": "must be an array"},
            {"field": "/units/2/kind", "reason": "required"},
            {"field": "/units/2/x", "reason": "unknown field"},
        ])
        self.assertFalse((self.working / "A").exists())


class BatchRefusalTest(BatchTestCase):
    """Everything is checked before anything is made."""

    def tearDown(self):
        self.assertEqual(self.shingi("list")[1]["warnings"], [])  # no tasks were made

    def test_a_path_given_twice(self):
        error = self.refused({"path": "A", "kind": "group"}, {"path": "A", "kind": "group"})
        self.assertEqual(error["kind"], "duplicate-path")
        self.assertEqual(
            error["details"], {"fields": ["/units/0/path", "/units/1/path"], "paths": ["A", "A"], "reason": "same"}
        )

    def test_a_path_given_twice_in_another_case(self):
        error = self.refused(*({"path": p, "kind": "group"} for p in ("A", "b", "B", "a")))
        self.assertEqual(
            error["details"], {"fields": ["/units/1/path", "/units/2/path"], "paths": ["b", "B"], "reason": "case"}
        )

    def test_duplicates_come_before_names(self):
        error = self.refused({"path": "bad-", "kind": "group"}, {"path": "bad-", "kind": "group"})
        self.assertEqual(error["kind"], "duplicate-path")

    def test_the_first_entry_in_path_order_is_reported_with_its_field(self):
        error = self.refused({"path": "Z", "kind": "nope"}, {"path": "A/x", "kind": "group"})
        self.assertEqual(error["kind"], "parent-not-found")
        self.assertEqual(error["details"], {"field": "/units/1/path", "parent": "A", "missing": "A"})

    def test_each_kind_points_into_its_entry(self):
        self.create("HOME-1", "group")
        (self.working / "plain").mkdir()
        cases = [
            ({"path": "B", "kind": "group", "after": ["A", "bad-"]}, "invalid-name", "/units/1/after/1"),
            ({"path": "B", "kind": "story"}, "unknown-kind", "/units/1/kind"),
            ({"path": "HOME-1", "kind": "group"}, "unit-exists", "/units/1/path"),
            ({"path": "PLAIN", "kind": "group"}, "name-taken", "/units/1/path"),
            ({"path": "B", "kind": "group", "after": ["A", "C"]}, "after-not-found", "/units/1/after/1"),
        ]
        for entry, kind, field in cases:
            with self.subTest(kind):
                error = self.refused({"path": "A", "kind": "group"}, entry)
                self.assertEqual((error["kind"], error["details"]["field"]), (kind, field))
        self.assertFalse((self.working / "A").exists())

    def test_after_lineage_includes_a_path_beneath(self):
        for after, relation in (("A", "self"), ("A/b", "descendant"), ("A/b/c", "descendant")):
            with self.subTest(after):
                error = self.refused({"path": "A", "kind": "group", "after": [after]}, {"path": "A/b", "kind": "group"})
                self.assertEqual(error["kind"], "after-lineage")
                self.assertEqual(error["details"], {"field": "/units/0/after/0", "after": after, "relation": relation})
        error = self.refused({"path": "A", "kind": "group"}, {"path": "A/b", "kind": "group", "after": ["A"]})
        self.assertEqual(error["details"], {"field": "/units/1/after/0", "after": "A", "relation": "ancestor"})

    def test_missing_is_the_shortest_prefix_neither_in_the_batch_nor_there(self):
        self.create("HOME-1", "group")
        error = self.refused({"path": "A", "kind": "group"}, {"path": "A/b/c", "kind": "group"})
        self.assertEqual(error["details"]["missing"], "A/b")
        error = self.refused({"path": "B", "kind": "group", "after": ["HOME-1/x/y"]})
        self.assertEqual(error["details"], {"field": "/units/0/after/0", "after": "HOME-1/x/y", "missing": "HOME-1/x"})

    def test_a_cycle_of_afters(self):
        error = self.refused(
            {"path": "A", "kind": "group", "after": ["B"]}, {"path": "B", "kind": "group", "after": ["A"]}
        )
        self.assertEqual(error["kind"], "after-cycle")
        self.assertEqual(error["details"], {"cycle": ["A", "B"]})
        self.assertFalse((self.working / "A").exists())

    def test_a_cycle_through_a_child(self):
        # x waits on y's done task, which waits on y/c's, which waits on x's.
        error = self.refused(
            {"path": "y/c", "kind": "group", "after": ["x"]},
            {"path": "x", "kind": "group", "after": ["y"]},
            {"path": "y", "kind": "group"},
        )
        self.assertEqual(error["details"], {"cycle": ["x", "y", "y/c"]})

    def test_a_cycle_comes_after_every_entrys_checks(self):
        error = self.refused(
            {"path": "A", "kind": "group", "after": ["B"]},
            {"path": "B", "kind": "group", "after": ["A"]},
            {"path": "C/d", "kind": "group"},
        )
        self.assertEqual(error["kind"], "parent-not-found")


class BatchWarningTest(BatchTestCase):
    def test_links_to_units_already_there_that_cant_be_found(self):
        self.create("P", "group")
        self.create("Q", "group")
        (self.working / "P/uow.json").write_text("{")
        status, out = self.batch(
            {"path": "P/b", "kind": "group", "after": ["Q"]}, {"path": "P/a", "kind": "group"}
        )
        self.assertEqual(status, 0, out)
        q = self.shingi("where", "Q")[1]["result"]
        self.koan("delete", str(q["done"]["id"]))
        status, out2 = self.batch({"path": "R", "kind": "group", "after": ["Q"]})
        self.assertEqual(status, 0, out2)
        self.assertEqual([(w["kind"], w["unit"], w["details"]) for w in out["warnings"]], [
            ("parent-unlinked", "P/a", {"parent": "P", "role": "start", "reason": "unsupported-manifest"}),
            ("parent-unlinked", "P/a", {"parent": "P", "role": "done", "reason": "unsupported-manifest"}),
            ("parent-unlinked", "P/b", {"parent": "P", "role": "start", "reason": "unsupported-manifest"}),
            ("parent-unlinked", "P/b", {"parent": "P", "role": "done", "reason": "unsupported-manifest"}),
        ])
        self.assertEqual([(w["kind"], w["unit"], w["details"]) for w in out2["warnings"]], [
            ("after-unlinked", "R", {"after": "Q", "reason": "missing-task"}),
        ])

    def test_a_done_parent_warns_for_each_entry_under_it(self):
        parent = self.create("P", "group")
        self.koan("done", str(parent["start"]["id"]))
        self.koan("done", str(parent["done"]["id"]))
        units, warnings = self.made({"path": "P/a", "kind": "group"}, {"path": "P/b", "kind": "group"})
        self.assertEqual([(w["kind"], w["unit"], w["ids"]) for w in warnings], [
            ("parent-done", "P/a", [parent["done"]["id"]]), ("parent-done", "P/b", [parent["done"]["id"]]),
        ])
        self.assertEqual(self.blocked_by(parent["done"]), [parent["start"]["id"]])


class BatchHooksTest(BatchTestCase):
    """create-batch fires its own event, once for the batch."""

    def test_its_hook_is_given_the_batch(self):
        batch, create = self.recorder(), self.recorder()
        self.write_hooks(**{"create-batch": [{"command": batch[0]}], "create": [{"command": create[0]}]})
        entries = [{"path": "A/b", "kind": "branch", "title": "B"}, {"path": "A", "kind": "group"}]
        status, out = self.batch(*entries)
        self.assertEqual(status, 0, out)
        payload = json.loads(batch[1].read_text())
        self.assertEqual(payload["event"], "create-batch")
        self.assertEqual(payload["input"], {"units": entries})
        self.assertEqual(payload["result"], out["result"])
        self.assertEqual(payload["warnings"], [])
        self.assertFalse(create[1].exists())  # never create's, for each unit

    def test_an_empty_batch_fires_it_with_no_units(self):
        command, out = self.recorder()
        self.write_hooks(**{"create-batch": [{"command": command}]})
        self.made()
        self.assertEqual(json.loads(out.read_text())["result"], {"units": []})

    def test_a_failing_hook_is_a_warning_about_no_unit(self):
        self.write_hooks(**{"create-batch": [{"command": "exit 3"}]})
        units, warnings = self.made({"path": "A", "kind": "group"})
        self.assertEqual(list(units), ["A"])
        self.assertEqual([(w["kind"], w["unit"], w["details"]["exit"]) for w in warnings], [("hook-failed", None, 3)])

    def test_a_broken_hooks_file_comes_before_every_entrys_checks(self):
        self.write_hooks(**{"create-batch": [{"command": ""}]})
        error = self.refused({"path": "A", "kind": "group"}, {"path": "A", "kind": "group"})
        self.assertEqual(error["kind"], "invalid-hooks")
        self.assertFalse((self.working / "A").exists())

    def test_a_batch_that_fails_part_way_fires_nothing(self):
        command, out = self.recorder()
        self.write_hooks(**{"create-batch": [{"command": command}]})
        self.create("HOME-1", "group")
        self.fake_koan(block="error")
        error = self.refused({"path": "HOME-1/a", "kind": "group"})
        self.assertIn("partial", error)
        self.assertFalse(out.exists())


class BatchPartialTest(BatchTestCase):
    """A batch that fails part-way tells what it made, and which units exist."""

    def setUp(self):
        super().setUp()
        self.parent = self.create("HOME-1", "group")

    def tasks_in(self, *paths):
        return sorted(t["id"] for p in paths for t in self.koan("list", "--folder", f"/shingi/{p}")["tasks"])

    def test_koan_making_some_of_the_tasks(self):
        self.fake_koan(create_batch="partial")
        error = self.refused({"path": "HOME-1/a", "kind": "group"}, {"path": "HOME-1/b", "kind": "group"})
        self.assertEqual(error["kind"], "koan-failed")
        self.assertEqual(error["partial"], {
            "units": [], "koan_folders": [], "tasks": self.tasks_in("HOME-1/a", "HOME-1/b"), "blocked": [], "files": [],
        })

    def test_koan_failing_to_find_the_tasks_already_there(self):
        self.fake_koan(list="error")
        error = self.refused({"path": "HOME-1/a", "kind": "group"})
        self.assertEqual((error["kind"], error["details"]["call"]), ("koan-failed", "list"))
        self.assertNotIn("partial", error)
        del self.env["FAKE_KOAN_LIST"]
        self.assertEqual(self.tasks_in("HOME-1"), sorted([self.parent["start"]["id"], self.parent["done"]["id"]]))
        self.assertFalse((self.working / "HOME-1/a").exists())

    def test_none_when_koan_made_nothing(self):
        self.fake_koan(create_batch="error")
        error = self.refused({"path": "HOME-1/a", "kind": "group"})
        self.assertNotIn("partial", error)

    def test_a_cycle_through_a_unit_already_there_is_koans_to_refuse(self):
        self.create("HOME-1/implementation", "group")
        error = self.refused(
            {"path": "HOME-1/followup", "kind": "group", "after": ["HOME-1/implementation"]},
            {"path": "HOME-1/implementation/x", "kind": "branch", "after": ["HOME-1/followup"]},
        )
        self.assertEqual(error["kind"], "koan-failed")
        self.assertEqual(error["details"]["call"], "block")
        self.assertEqual(error["details"]["error"]["rule"], "cycle")
        partial = error["partial"]
        followup = self.tasks_in("HOME-1/followup")
        self.assertEqual(partial["units"], [])
        self.assertEqual(partial["koan_folders"], ["/shingi/HOME-1/followup", "/shingi/HOME-1/implementation/x"])
        self.assertEqual(partial["tasks"], sorted(followup + self.tasks_in("HOME-1/implementation/x")))
        self.assertEqual(partial["blocked"], [{"task": self.parent["done"]["id"], "added": [followup[1]]}])
        self.assertEqual(partial["files"], [])

    def test_something_in_the_way_of_a_folder(self):
        self.fake_koan(block_touch=self.working / "HOME-1" / "b")
        error = self.refused({"path": "HOME-1/b", "kind": "group"}, {"path": "HOME-1/a", "kind": "group"})
        self.assertEqual(error["kind"], "name-taken")
        self.assertEqual(error["details"], {"field": "/units/0/path", "entry": "b", "type": "file"})
        a, b = self.tasks_in("HOME-1/a"), self.tasks_in("HOME-1/b")
        folder = self.working / "HOME-1" / "a"
        self.assertEqual(error["partial"], {
            "units": [],
            "koan_folders": ["/shingi/HOME-1/a", "/shingi/HOME-1/b"],
            "tasks": sorted(a + b),
            "blocked": [{"task": self.parent["done"]["id"], "added": [a[1], b[1]]}],
            "files": [str(folder), str(folder / "uow.md")],
        })
        self.assertFalse((folder / "uow.json").exists())

    def run_in_process(self, payload, fail_at=None, patch=None):
        """Run create-batch in this process: its manifest for `fail_at` failing as a full disk, or
        with `patch`, a mock patcher, in place instead."""
        write_manifest = operations.write_manifest

        def failing(path, folder, manifest, at=None):
            if path == fail_at:
                raise operations.io_error(OSError(28, "No space left on device"), folder / "uow.json")
            return write_manifest(path, folder, manifest, at)

        file = self.working.parent / "batch.json"
        file.write_text(json.dumps(payload))
        with mock.patch.dict(os.environ, self.env, clear=True), \
                patch or mock.patch.object(operations, "write_manifest", failing):
            out, status = cli.run(["create-batch", "-i", str(file), "--config", str(self.config)])
        self.assertEqual(status, 1, out)
        return out["error"]

    def test_writing_a_manifest_then_running_the_rest(self):
        a = {"path": "HOME-1/a", "kind": "group"}
        b = {"path": "HOME-1/b", "kind": "group", "after": ["HOME-1/a/c"]}
        c = {"path": "HOME-1/a/c", "kind": "group"}
        error = self.run_in_process({"units": [b, c, a]}, fail_at="HOME-1/b")
        self.assertEqual(error["kind"], "io")
        partial = error["partial"]
        folder = self.working / "HOME-1" / "b"
        self.assertEqual(partial["units"], ["HOME-1/a", "HOME-1/a/c"])  # in the order made
        self.assertEqual(partial["koan_folders"], ["/shingi/HOME-1/b"])
        b_tasks = self.tasks_in("HOME-1/b")
        self.assertEqual(partial["tasks"], b_tasks)
        self.assertEqual(partial["blocked"], [{"task": self.parent["done"]["id"], "added": [b_tasks[1]]}])
        self.assertEqual(partial["files"], [str(folder), str(folder / "uow.md")])

        # Undo it, as the spec says, and run it again without the units made.
        for koan_folder in partial["koan_folders"]:
            self.koan("delete-folder", "-r", koan_folder)
        for path in reversed(partial["files"]):
            (os.rmdir if os.path.isdir(path) else os.remove)(path)
        units, warnings = self.made(b)
        self.assertEqual(warnings, [])
        c_done = self.shingi("where", "HOME-1/a/c")[1]["result"]["done"]["id"]
        self.assertEqual(self.blocked_by(units["HOME-1/b"]["start"]), sorted([self.parent["start"]["id"], c_done]))
        self.assertEqual(self.shingi("list")[1]["warnings"], [])

    def test_linking_the_second_parent_already_there_fails(self):
        other = self.create("HOME-2", "group")
        block, calls = operations.koan.block, []

        def failing(task, blockers):
            calls.append(task)
            return block(task, blockers + [999999] if len(calls) == 2 else blockers)  # koan refuses it

        error = self.run_in_process(
            {"units": [{"path": "HOME-2/a", "kind": "group"}, {"path": "HOME-1/a", "kind": "group"}]},
            patch=mock.patch.object(operations.koan, "block", failing),
        )
        self.assertEqual((error["kind"], error["details"]["call"]), ("koan-failed", "block"))
        self.assertEqual(calls, [self.parent["done"]["id"], other["done"]["id"]])
        one, two = self.tasks_in("HOME-1/a"), self.tasks_in("HOME-2/a")
        self.assertEqual(error["partial"], {
            "units": [],
            "koan_folders": ["/shingi/HOME-1/a", "/shingi/HOME-2/a"],
            "tasks": sorted(one + two),
            "blocked": [{"task": self.parent["done"]["id"], "added": [one[1]]}],
            "files": [],
        })

    def test_a_manifest_that_appears_meanwhile(self):
        write_manifest = operations.write_manifest

        def racing(path, folder, manifest, at=None):
            if path == "HOME-1/b":
                (folder / "uow.json").write_text("{}")
            return write_manifest(path, folder, manifest, at)

        error = self.run_in_process(
            {"units": [{"path": "HOME-1/b", "kind": "group"}, {"path": "HOME-1/a", "kind": "group"}]},
            patch=mock.patch.object(operations, "write_manifest", racing),
        )
        folder = self.working / "HOME-1" / "b"
        self.assertEqual(error["kind"], "unit-exists")
        self.assertEqual(error["details"], {"field": "/units/0/path", "manifest": str(folder / "uow.json")})
        b = self.tasks_in("HOME-1/b")
        self.assertEqual(error["partial"], {
            "units": ["HOME-1/a"],
            "koan_folders": ["/shingi/HOME-1/b"],
            "tasks": b,
            "blocked": [{"task": self.parent["done"]["id"], "added": [b[1]]}],
            "files": [str(folder), str(folder / "uow.md")],
        })

    def test_running_it_again_fails_on_the_first_entry_in_path_order(self):
        # b's manifest is written first, since a comes after it; then a's fails.
        a = {"path": "HOME-1/a", "kind": "group", "after": ["HOME-1/b"]}
        b = {"path": "HOME-1/b", "kind": "group"}
        error = self.run_in_process({"units": [a, b]}, fail_at="HOME-1/a")
        self.assertEqual(error["partial"]["units"], ["HOME-1/b"])
        error = self.refused(a, b)
        self.assertEqual(error["kind"], "name-taken")
        self.assertEqual(error["details"], {"field": "/units/0/path", "entry": "a", "type": "folder"})

    def test_running_it_again_as_it_stands(self):
        a = {"path": "HOME-1/a", "kind": "group"}
        b = {"path": "HOME-1/b", "kind": "group", "after": ["HOME-1/a"]}
        self.run_in_process({"units": [b, a]}, fail_at="HOME-1/b")
        error = self.refused(b, a)
        self.assertEqual((error["kind"], error["details"]["field"]), ("unit-exists", "/units/1/path"))


if __name__ == "__main__":
    unittest.main()
