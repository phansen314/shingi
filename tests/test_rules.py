import unittest

from support import ShingiTestCase


class RulesTest(ShingiTestCase):
    """Every operation but version reads and checks shingi.toml first."""

    def rules(self, text):
        self.config.write_text(text.format(working=self.working))
        status, out = self.shingi("kinds")
        self.assertEqual(status, 1, out)
        return out["error"]

    def problems(self, text):
        error = self.rules(text)
        self.assertEqual((error["kind"], error["details"]["reason"]), ("invalid-rules", "invalid"), error)
        return [(p["field"], p["reason"]) for p in error["details"]["problems"]]

    VALID = 'schema = 1\n[roots]\nkoan = "/work"\nworking = "{working}"\n'

    def test_every_problem_sorted_by_field(self):
        self.assertEqual(self.problems(
            'schema = 1\ncolour = "red"\n[roots]\nkoan = "/work/"\nworking = "rel"\nextra = 1\n'
            '[kind.Group]\n[kind.branch]\nsugests = []\ndescription = 5\nsuggests = ["group", 3]\n'
            '[kind.group]\nsuggests = ["story"]\n'
        ), [
            ("colour", "unknown field"),
            ("kind.Group", "a kind name is lowercase letters, digits, and -, as a koan tag"),
            ("kind.branch.description", "must be a string"),
            ("kind.branch.sugests", "unknown field"),
            ("kind.branch.suggests", "must be an array of strings"),
            ("kind.group.suggests", "'story' is not a defined kind"),
            ("roots.extra", "unknown field"),
            ("roots.koan", "required: a koan folder path other than /, such as /work"),
            ("roots.working", "must be an existing absolute directory"),
        ])

    def test_koan_root_is_a_koan_folder_path(self):
        for root in ("/", "work", "/a//b", "/a b", "/-a", "/a/"):
            with self.subTest(root):
                fields = [f for f, _ in self.problems(f'schema = 1\n[roots]\nkoan = "{root}"\nworking = "{{working}}"\n[kind.g]\n')]
                self.assertEqual(fields, ["roots.koan"])
        self.config.write_text(f'schema = 1\n[roots]\nkoan = "/Work/HOME-1"\nworking = "{self.working}"\n[kind.g]\n')
        self.assertEqual(self.shingi("kinds")[0], 0)

    def test_wrong_shapes(self):
        self.assertEqual(self.problems('schema = 1\nroots = "x"\nkind = 5\n'),
                         [("kind", "at least one kind is required"), ("roots", "required: a table")])
        self.assertEqual(self.problems(self.VALID + "[kind]\ng = 1\n"), [("kind.g", "must be a table")])

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


if __name__ == "__main__":
    unittest.main()
