import json
import unittest

from support import ShingiTestCase


class InputTest(ShingiTestCase):
    """-i / --input: an operation's input as one JSON object, from a file or stdin."""

    def run_input(self, command, data, *args):
        if not isinstance(data, bytes):
            data = json.dumps(data).encode()
        return self.shingi(command, "-i", "-", *args, stdin=data)

    def problems(self, command, data):
        status, out = self.run_input(command, data)
        self.assertEqual(status, 1, out)
        self.assertEqual(out["error"]["kind"], "invalid-input", out)
        return out["error"]["details"]["problems"]

    def test_create_from_stdin(self):
        status, out = self.run_input("create", {"path": "HOME-1", "kind": "group", "title": "Payment retries",
                                                "notes": "It's \"quoted\" and $costly\n"})
        self.assertEqual(status, 0, out)
        self.assertEqual((self.working / "HOME-1" / "uow.md").read_text(),
                         "# Payment retries\n\nIt's \"quoted\" and $costly\n")

    def test_every_option_form(self):
        path = self.config.parent / "input.json"
        path.write_text('{"path": "HOME-1", "kind": "group"}')
        for i, form in enumerate((["-i", str(path)], [f"-i{path}"], ["--input", str(path)], [f"--input={path}"])):
            with self.subTest(form):
                self.assertEqual(self.shingi("kinds", *form)[1]["error"]["kind"], "invalid-input")
        status, out = self.shingi("create", "--input", str(path))
        self.assertEqual(status, 0, out)

    def test_where_gets_no_cwd(self):
        self.shingi("create", "HOME-1", "group")
        self.assertEqual(self.problems("where", {}), [{"field": "", "reason": "exactly one of unit and cwd is required"}])
        status, out = self.run_input("where", {"cwd": str(self.working / "HOME-1")})
        self.assertEqual(status, 0, out)
        self.assertEqual(out["result"]["path"], "HOME-1")

    def test_kinds_and_version_take_only_an_empty_object(self):
        for command in ("kinds", "version"):
            with self.subTest(command):
                self.assertEqual(self.run_input(command, {})[0], 0)
                self.assertEqual(self.problems(command, {"x": 1}), [{"field": "/x", "reason": "unknown field"}])

    def test_every_problem_sorted(self):
        self.assertEqual(self.problems("create", {"kind": 5, "title": "a\nb", "notes": "x\0y", "extra": True}), [
            {"field": "/extra", "reason": "unknown field"},
            {"field": "/kind", "reason": "must be a string"},
            {"field": "/notes", "reason": "holds a NUL"},
            {"field": "/path", "reason": "required"},
            {"field": "/title", "reason": "holds a line break"},
        ])

    def test_adopt_takes_no_notes(self):
        self.assertEqual(self.problems("adopt", {"path": "a", "kind": "group", "notes": "x"}),
                         [{"field": "/notes", "reason": "unknown field"}])

    def test_where_and_context_checks(self):
        for command in ("where", "context"):
            with self.subTest(command):
                self.assertEqual(self.problems(command, {"unit": "a", "cwd": "rel"}), [
                    {"field": "", "reason": "exactly one of unit and cwd is required"},
                    {"field": "/cwd", "reason": "must be absolute"},
                ])

    def test_list_unit_must_be_a_string(self):
        self.assertEqual(self.problems("list", {"unit": None}), [{"field": "/unit", "reason": "must be a string"}])

    def test_not_one_json_object(self):
        for data in (b"", b"[]", b'"x"', b"{} {}", b'{"a": 1, "a": 2}', b"\xef\xbb\xbf{}", b'{"a": "\xff"}',
                     b'{"a": NaN}', b"{"):
            with self.subTest(data):
                problems = self.problems("kinds", data)
                self.assertEqual([p["field"] for p in problems], [""])

    def test_with_field_arguments_is_a_usage_error(self):
        for args in (["create", "HOME-1", "group"], ["create", "--title", "x"], ["where", "HOME-1"]):
            with self.subTest(args):
                status, out = self.shingi(*args, "-i", "-", stdin=b"{}")
                self.assertEqual(status, 2, out)
                self.assertEqual(out["error"]["kind"], "usage")

    def test_config_goes_with_it(self):
        status, out = self.run_input("kinds", {})  # shingi() always passes --config
        self.assertEqual(status, 0, out)

    def test_an_unreadable_file_is_io(self):
        status, out = self.shingi("kinds", "-i", str(self.working / "nope.json"))
        self.assertEqual(status, 1)
        self.assertEqual(out["error"]["details"], {"path": str(self.working / "nope.json"), "code": "ENOENT"})


class FieldChecksTest(ShingiTestCase):
    """The operation's checks hold on the command line too."""

    def test_an_empty_title(self):
        status, out = self.shingi("create", "HOME-1", "group", "--title", "")
        self.assertEqual(status, 1)
        self.assertEqual(out["error"]["details"]["problems"], [{"field": "/title", "reason": "must not be empty"}])

    def test_a_title_with_a_line_break(self):
        status, out = self.shingi("adopt", "HOME-1", "group", "--title", "a\rb")
        self.assertEqual(out["error"]["details"]["problems"], [{"field": "/title", "reason": "holds a line break"}])

    def test_bad_notes_file_reported_with_the_rest(self):
        notes = self.working / "notes.md"
        notes.write_bytes(b"\xff")
        status, out = self.shingi("create", "HOME-1", "group", "--title", "", "--notes-file", str(notes))
        self.assertEqual(out["error"]["details"]["problems"], [
            {"field": "/notes", "reason": "not valid UTF-8"},
            {"field": "/title", "reason": "must not be empty"},
        ])


if __name__ == "__main__":
    unittest.main()
