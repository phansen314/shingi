import json
import unittest

from support import RULES as RULES_TEXT, ShingiTestCase


class HooksFileTest(ShingiTestCase):
    def create(self, name="HOME-1"):
        return self.shingi("create", name, "group")

    def write_raw(self, text):
        self.hooks_file.parent.mkdir(parents=True, exist_ok=True)
        self.hooks_file.write_text(text)

    def write_file(self, value):
        self.write_raw(json.dumps(value))

    def assert_untouched(self):
        self.assertEqual(list(self.working.iterdir()), [])
        self.assertEqual(self.koan("list", "--readiness", "ready,blocked,done")["tasks"], [])

    def assert_invalid(self, expected, **file):
        """`create` is invalid-hooks with exactly these problems, and changed nothing."""
        self.write_file({"schema": 1, **file})
        status, out = self.create()
        self.assertEqual(status, 1, out)
        self.assertEqual(out["error"]["kind"], "invalid-hooks")
        details = out["error"]["details"]
        self.assertEqual(details["reason"], "invalid")
        self.assertEqual(details["path"], str(self.hooks_file))
        self.assertEqual(details["problems"], [{"field": f, "reason": r} for f, r in expected])
        self.assert_untouched()

    def test_no_hooks_file_changes_nothing(self):
        status, out = self.create()
        self.assertEqual(status, 0, out)
        self.assertEqual(out["warnings"], [])

    def test_each_problem_is_invalid_with_its_field(self):
        for name, file, field in [
            ("top-level key", {"extra": 1}, "/extra"),
            ("event", {"hooks": {"save": []}}, "/hooks/save"),
            ("hooks not an object", {"hooks": []}, "/hooks"),
            ("event not an array", {"hooks": {"create": {}}}, "/hooks/create"),
            ("hook not an object", {"hooks": {"create": ["x"]}}, "/hooks/create/0"),
            ("hook field", {"hooks": {"create": [{"command": "true", "nope": 1}]}}, "/hooks/create/0/nope"),
            ("missing command", {"hooks": {"create": [{}]}}, "/hooks/create/0/command"),
            ("empty command", {"hooks": {"create": [{"command": ""}]}}, "/hooks/create/0/command"),
            ("command with NUL", {"hooks": {"create": [{"command": "a\0b"}]}}, "/hooks/create/0/command"),
            ("command not a string", {"hooks": {"create": [{"command": 1}]}}, "/hooks/create/0/command"),
            ("timeout 0", {"hooks": {"create": [{"command": "true", "timeout": 0}]}}, "/hooks/create/0/timeout"),
            ("timeout negative", {"hooks": {"create": [{"command": "true", "timeout": -1}]}}, "/hooks/create/0/timeout"),
            ("timeout true", {"hooks": {"create": [{"command": "true", "timeout": True}]}}, "/hooks/create/0/timeout"),
            ("timeout string", {"hooks": {"create": [{"command": "true", "timeout": "10"}]}}, "/hooks/create/0/timeout"),
            ("description", {"hooks": {"create": [{"command": "true", "description": 1}]}}, "/hooks/create/0/description"),
            ("disabled", {"hooks": {"create": [{"command": "true", "disabled": "yes"}]}}, "/hooks/create/0/disabled"),
        ]:
            with self.subTest(name):
                self.write_file({"schema": 1, **file})
                status, out = self.create()
                self.assertEqual(out["error"]["kind"], "invalid-hooks", out)
                self.assertEqual([p["field"] for p in out["error"]["details"]["problems"]], [field])
                self.assert_untouched()

    def test_a_timeout_that_reads_as_infinite(self):
        for text in ("1e999", "1" + "0" * 400):
            with self.subTest(text):
                self.write_raw('{"schema":1,"hooks":{"create":[{"command":"true","timeout":%s}]}}' % text)
                status, out = self.create()
                self.assertEqual(out["error"]["kind"], "invalid-hooks", out)
                self.assertEqual(out["error"]["details"]["problems"][0]["field"], "/hooks/create/0/timeout")

    def test_a_pointer_escapes_its_keys(self):
        self.assert_invalid([("/a~1b~0c", "unknown field")], **{"a/b~c": 1})

    def test_several_problems_are_reported_together_sorted(self):
        self.assert_invalid(
            [
                ("/hooks/create/0/command", "required: a non-empty string with no NUL"),
                ("/hooks/create/0/timeout", "must be a finite number above 0"),
                ("/hooks/create/1/nope", "unknown field"),
                ("/hooks/save", "unknown event"),
                ("/zzz", "unknown field"),
            ],
            zzz=1,
            hooks={"save": [], "create": [{"command": "", "timeout": 0}, {"command": "true", "nope": 1}]},
        )

    def test_a_file_that_is_not_json_is_syntax(self):
        for name, text in [
            ("not JSON", "{"),
            ("not an object", "[]"),
            ("repeated key", '{"schema":1,"schema":1}'),
            ("nested repeated key", '{"schema":1,"hooks":{"create":[{"command":"a","command":"b"}]}}'),
            ("NaN", '{"schema":1,"hooks":{"create":[{"command":"a","timeout":NaN}]}}'),
            ("Infinity", '{"schema":1,"hooks":{"create":[{"command":"a","timeout":Infinity}]}}'),
        ]:
            with self.subTest(name):
                self.write_raw(text)
                status, out = self.create()
                self.assertEqual(status, 1, out)
                self.assertEqual(out["error"]["kind"], "invalid-hooks")
                self.assertEqual(out["error"]["details"]["reason"], "syntax")
                self.assertEqual(out["error"]["details"]["problems"], [])
                self.assert_untouched()

    def test_a_file_that_is_not_utf8_is_syntax(self):
        self.hooks_file.parent.mkdir(parents=True)
        self.hooks_file.write_bytes(b'{"schema":1,"x":"\xff"}')
        status, out = self.create()
        self.assertEqual(out["error"]["details"]["reason"], "syntax")

    def test_a_schema_that_is_missing_or_not_an_integer_is_invalid(self):
        for name, text in [("missing", "{}"), ("string", '{"schema":"1"}'), ("boolean", '{"schema":true}'), ("float", '{"schema":1.0}')]:
            with self.subTest(name):
                self.write_raw(text)
                status, out = self.create()
                self.assertEqual(out["error"]["kind"], "invalid-hooks", out)
                self.assertEqual(out["error"]["details"]["reason"], "invalid")
                self.assertEqual([p["field"] for p in out["error"]["details"]["problems"]], ["/schema"])

    def test_a_hooks_file_that_is_a_directory_is_unreadable(self):
        self.hooks_file.mkdir(parents=True)
        status, out = self.create()
        self.assertEqual(out["error"]["kind"], "invalid-hooks")
        details = out["error"]["details"]
        self.assertEqual(details["reason"], "unreadable")
        self.assertEqual(details["code"], "EISDIR")
        self.assertEqual(details["path"], str(self.hooks_file))
        self.assert_untouched()

    def test_an_unsupported_schema(self):
        for extra in ({}, {"junk": 1, "hooks": {"save": 1}}):
            with self.subTest(extra=extra):
                self.write_file({"schema": 2, **extra})
                status, out = self.create()
                self.assertEqual(status, 1, out)
                self.assertEqual(out["error"]["kind"], "unsupported-format")
                self.assertEqual(out["error"]["details"], {"path": str(self.hooks_file), "schema": 2, "supported": [1]})
                self.assert_untouched()

    def test_a_problem_in_a_disabled_hook_or_another_event_stops_the_command(self):
        for name, hooks in [
            ("disabled", {"create": [{"command": "true", "disabled": True, "timeout": 0}]}),
            ("other event", {"delete": [{"command": ""}]}),
        ]:
            with self.subTest(name):
                self.write_file({"schema": 1, "hooks": hooks})
                status, out = self.create()
                self.assertEqual(out["error"]["kind"], "invalid-hooks", out)
                self.assert_untouched()

    def test_a_broken_hooks_file_leaves_the_reads_working(self):
        self.shingi("create", "HOME-1", "group")
        self.write_raw("{")
        for args in (["where", "HOME-1"], ["context", "HOME-1"], ["list"], ["kinds"], ["version"]):  # bind and unbind: test_bind.py
            with self.subTest(args):
                status, out = self.shingi(*args)
                self.assertEqual(status, 0, out)

    def test_a_broken_rules_file_wins_over_a_broken_hooks_file(self):
        self.write_raw("{")
        self.config.write_text("not toml [")
        status, out = self.create()
        self.assertEqual(out["error"]["kind"], "invalid-rules")

    def test_config_does_not_move_the_hooks_file(self):
        elsewhere = self.tmp / "elsewhere" / "hooks.json"
        elsewhere.parent.mkdir()
        elsewhere.write_text("{")  # beside the rules file named by --config, and ignored
        self.config = elsewhere.with_name("shingi.toml")
        self.config.write_text(RULES_TEXT)
        marker = self.tmp / "ran"
        self.write_hooks(create=[{"command": f"touch {marker}"}])
        status, out = self.create()
        self.assertEqual(status, 0, out)
        self.assertTrue(marker.exists())

    def test_a_disabled_hook_is_skipped(self):
        log = self.tmp / "log"
        self.write_hooks(create=[
            {"command": f"echo one >> {log}", "disabled": True},
            {"command": f"echo two >> {log}", "disabled": False},
        ])
        status, out = self.create()
        self.assertEqual(status, 0, out)
        self.assertEqual(log.read_text(), "two\n")

    def test_index_counts_a_disabled_hook_before_it(self):
        self.write_hooks(create=[{"command": "true", "disabled": True}, {"command": "exit 1", "description": "d"}])
        status, out = self.create()
        (warning,) = out["warnings"]
        self.assertEqual(warning["details"]["index"], 1)
        self.assertEqual(warning["details"]["description"], "d")


    def test_adopt_and_delete_behave_as_before_with_no_hooks_file(self):
        (self.working / "HOME-1").mkdir()
        status, out = self.shingi("adopt", "HOME-1", "group")
        self.assertEqual((status, out["warnings"]), (0, []))
        status, out = self.shingi("delete", "HOME-1")
        self.assertEqual((status, out["warnings"]), (0, []))

    def test_create_batch_behaves_as_before_with_no_hooks_file(self):
        batch = {"units": [{"path": "HOME-1", "kind": "group"}]}
        status, out = self.shingi("create-batch", "-i", "-", stdin=json.dumps(batch).encode())
        self.assertEqual((status, out["warnings"]), (0, []))

    def test_a_broken_hooks_file_stops_adopt_and_delete_before_any_change(self):
        (self.working / "HOME-1").mkdir()
        self.shingi("create", "HOME-2", "group")
        self.write_raw("{")
        status, out = self.shingi("adopt", "HOME-1", "group")
        self.assertEqual(out["error"]["kind"], "invalid-hooks")
        self.assertFalse((self.working / "HOME-1" / "uow.json").exists())
        status, out = self.shingi("delete", "HOME-2")
        self.assertEqual(out["error"]["kind"], "invalid-hooks")
        self.assertTrue((self.working / "HOME-2" / "uow.json").exists())
        self.write_file({"schema": 2})
        self.assertEqual(self.shingi("delete", "HOME-2")[1]["error"]["kind"], "unsupported-format")


    def test_invalid_input_comes_before_a_broken_hooks_file(self):
        self.write_raw("{")
        status, out = self.shingi("create", "HOME-1")
        self.assertIn(out["error"]["kind"], ("usage",))
        status, out = self.shingi("create", "-i", "-", stdin=b'{"path": "HOME-1"}')
        self.assertEqual(out["error"]["kind"], "invalid-input")

    def test_the_hooks_file_comes_before_the_commands_own_checks(self):
        self.shingi("create", "HOME-1", "group")
        self.write_raw("{")
        for name, args in [
            ("invalid-name", ["create", "bad-", "group"]),
            ("unknown-kind", ["create", "HOME-2", "story"]),
            ("unit-exists", ["create", "HOME-1", "group"]),
            ("delete not-found", ["delete", "HOME-9"]),
            ("adopt not-found", ["adopt", "HOME-9", "group"]),
        ]:
            with self.subTest(name):
                status, out = self.shingi(*args)
                self.assertEqual(out["error"]["kind"], "invalid-hooks", out)

    def test_a_hook_field_key_is_escaped_in_its_pointer(self):
        self.assert_invalid(
            [("/hooks/create/0/a~1b~0c", "unknown field")], hooks={"create": [{"command": "true", "a/b~c": 1}]},
        )

    def test_a_deeply_nested_file_is_syntax(self):
        self.write_raw("[" * 200000)
        status, out = self.create()
        self.assertEqual(out["error"]["kind"], "invalid-hooks", out)
        self.assertEqual(out["error"]["details"]["reason"], "syntax")


if __name__ == "__main__":
    unittest.main()
