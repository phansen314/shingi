import json
import shutil
import subprocess
import unittest
from pathlib import Path

from support import ShingiTestCase


class RulesTest(ShingiTestCase):
    """Every operation but version reads and checks shingi.toml first."""

    def rules(self, text):
        self.config.write_text(text)
        status, out = self.shingi("kinds")
        self.assertEqual(status, 1, out)
        return out["error"]

    def problems(self, text):
        error = self.rules(text)
        self.assertEqual((error["kind"], error["details"]["reason"]), ("invalid-rules", "invalid"), error)
        return [(p["field"], p["reason"]) for p in error["details"]["problems"]]

    def test_every_problem_sorted_by_field(self):
        self.assertEqual(self.problems(
            'schema = 1\ncolour = "red"\n[roots]\nkoan = "/work"\n'
            '[kind.Group]\n[kind.branch]\nsugests = []\ndescription = 5\nsuggests = ["group", 3]\n'
            '[kind.group]\nsuggests = ["story"]\n'
        ), [
            ("colour", "unknown field"),
            ("kind.Group", "a kind name is lowercase letters, digits, and -, as a koan tag"),
            ("kind.branch.description", "must be a string"),
            ("kind.branch.sugests", "unknown field"),
            ("kind.branch.suggests", "must be an array of strings"),
            ("kind.group.suggests", "'story' is not a defined kind"),
            ("roots", "unknown field"),
        ])

    def test_wrong_shapes(self):
        self.assertEqual(self.problems("schema = 1\nkind = 5\n"), [("kind", "at least one kind is required")])
        self.assertEqual(self.problems("schema = 1\n[kind]\ng = 1\n"), [("kind.g", "must be a table")])

    def test_schema(self):
        for schema in ("", 'schema = "1"\n', "schema = true\n"):
            with self.subTest(schema):
                self.assertEqual(self.problems(schema + '[kind.g]\n'), [("schema", "required: an integer")])
        error = self.rules("schema = 2\n")
        self.assertEqual(error["kind"], "unsupported-format")
        self.assertEqual(error["details"], {"path": str(self.config), "schema": 2, "supported": [1]})

    def test_unreadable(self):
        self.config.unlink()
        self.config.mkdir()
        status, out = self.shingi("kinds")  # a directory can't be read as a file
        self.assertEqual(out["error"]["details"]["reason"], "unreadable")
        self.assertEqual(out["error"]["details"]["code"], "EISDIR")

    def test_not_utf8_is_syntax(self):
        self.config.write_bytes(b'schema = 1\n# \xff\n')
        status, out = self.shingi("kinds")
        self.assertEqual(out["error"]["details"]["reason"], "syntax")

    def test_version_doesnt_read_it(self):
        self.config.write_text("nonsense")
        self.assertEqual(self.shingi("version")[0], 0)


class NoRulesFileTest(ShingiTestCase):
    """With no shingi.toml, the kinds are the built-in two; --config's file must exist."""

    def shingi(self, *args, **kwargs):
        proc = subprocess.run([shutil.which("shingi"), *args], env=self.env, capture_output=True, **kwargs)
        return proc.returncode, json.loads(proc.stdout)

    def test_the_built_in_kinds(self):
        status, out = self.shingi("kinds")
        self.assertEqual(status, 0, out)
        self.assertEqual([(k["name"], k["suggests"]) for k in out["result"]["kinds"]],
                         [("branch", []), ("group", ["group", "branch"])])

    def test_a_rules_file_replaces_them(self):
        rules = self.hooks_file.with_name("shingi.toml")  # where shingi looks, on this platform
        rules.parent.mkdir(parents=True)
        rules.write_text("schema = 1\n[kind.story]\n")
        self.assertEqual([k["name"] for k in self.shingi("kinds")[1]["result"]["kinds"]], ["story"])
        rules.write_text("nonsense")
        self.assertEqual(self.shingi("kinds")[1]["error"]["details"]["reason"], "syntax")

    def test_a_missing_config_file_is_an_error(self):
        status, out = self.shingi("kinds", "--config", str(self.working / "nope.toml"))
        self.assertEqual(out["error"]["details"]["reason"], "missing")


class RootsTest(ShingiTestCase):
    """The tree is at ~/shingi-root and /shingi; the first create makes the working root."""

    def setUp(self):
        super().setUp()
        self.working.rmdir()

    def test_reads_find_nothing_before_the_first_create(self):
        self.assertEqual(self.shingi("list"), (0, {"ok": True, "result": {"root": None, "units": []}, "warnings": []}))
        for args, cwd in ((["where", "HOME-1"], None), (["where"], self.working.parent), (["adopt", "HOME-1", "group"], None)):
            with self.subTest(args):
                status, out = self.shingi(*args, cwd=cwd)
                self.assertEqual((status, out["error"]["kind"]), (1, "not-found"), out)

    def test_create_makes_it(self):
        status, out = self.shingi("create", "HOME-1", "group")
        self.assertEqual(status, 0, out)
        unit = out["result"]["unit"]
        self.assertEqual(unit["working_folder"], str(self.working / "HOME-1"))
        self.assertEqual(unit["koan_folder"], "/shingi/HOME-1")

    def test_a_symlink_keeps_it_elsewhere(self):
        elsewhere = self.working.parent / "elsewhere"
        elsewhere.mkdir()
        self.working.symlink_to(elsewhere)
        status, out = self.shingi("create", "HOME-1", "group")
        self.assertEqual(out["result"]["unit"]["working_folder"], str(elsewhere / "HOME-1"))

    def test_not_a_directory_is_io(self):
        self.working.write_text("")
        status, out = self.shingi("list")
        self.assertEqual((status, out["error"]["kind"], out["error"]["details"]),
                         (1, "io", {"path": str(self.working), "code": "ENOTDIR"}))


if __name__ == "__main__":
    unittest.main()
