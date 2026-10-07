import unittest

from support import ShingiTestCase

KOAN_WARNING = {"kind": "unusable-file", "message": "bad task file", "paths": ["/x/9.json"], "ids": [9], "reason": "corrupt"}


class KoanFailedOnReadTest(ShingiTestCase):
    def setUp(self):
        super().setUp()
        for path in ("HOME-1", "HOME-1/a"):
            status, out = self.shingi("create", path, "group")
            self.assertEqual(status, 0, out)

    def assert_tasks_null(self, unit):
        for field in ("start", "done", "state"):
            self.assertIsNone(unit[field], field)

    def test_where_still_reports_the_unit(self):
        self.fake_koan(list="error")
        status, out = self.shingi("where", "HOME-1")
        self.assertEqual(status, 0, out)
        unit = out["result"]
        self.assert_tasks_null(unit)
        self.assertEqual(unit["kind"], "group")
        self.assertEqual(unit["children"], [{"path": "HOME-1/a", "kind": "group"}])
        self.assertEqual(out["warnings"], [{
            "kind": "koan-failed",
            "message": out["warnings"][0]["message"],
            "unit": "HOME-1",
            "ids": [],
            "details": {"call": "list", "exit": 1, "error": {"kind": "io", "message": "disk on fire", "details": {}}},
        }])

    def test_koan_without_an_envelope(self):
        for mode, exit_code in (("garbage", 0), ("crash", 137)):
            with self.subTest(mode):
                self.fake_koan(list=mode)
                status, out = self.shingi("where", "HOME-1")
                self.assertEqual(status, 0, out)
                self.assertEqual(out["warnings"][0]["details"], {"call": "list", "exit": exit_code, "error": None})

    def test_koan_not_on_path(self):
        self.env["PATH"] = "/nonexistent"
        status, out = self.shingi("where", "HOME-1")
        self.assertEqual(status, 0, out)
        self.assertEqual(out["warnings"][0]["details"], {"call": "list", "exit": None, "error": None})

    def test_list_reports_every_unit_and_no_orphans_or_missing_tasks(self):
        self.fake_koan(list="error")
        status, out = self.shingi("list")
        self.assertEqual(status, 0, out)
        self.assertEqual([u["path"] for u in out["result"]["units"]], ["HOME-1", "HOME-1/a"])
        for unit in out["result"]["units"]:
            self.assert_tasks_null(unit)
        self.assertEqual([(w["kind"], w["unit"]) for w in out["warnings"]], [("koan-failed", None)])

    def test_create_fails_when_the_parents_tasks_cant_be_read(self):
        self.fake_koan(list="error")
        status, out = self.shingi("create", "HOME-1/b", "group")
        self.assertEqual(status, 1)
        self.assertEqual(out["error"]["kind"], "koan-failed")
        self.assertEqual(out["error"]["details"]["call"], "list")
        self.assertNotIn("partial", out["error"])
        self.assertFalse((self.working / "HOME-1" / "b").exists())


class KoanWarningTest(ShingiTestCase):
    def setUp(self):
        super().setUp()
        status, out = self.shingi("create", "HOME-1", "group")
        self.assertEqual(status, 0, out)

    def test_where_passes_koans_warnings_on(self):
        self.fake_koan(list="warn")
        status, out = self.shingi("where", "HOME-1")
        self.assertEqual(status, 0, out)
        self.assertEqual(out["warnings"], [{
            "kind": "koan-warning",
            "message": out["warnings"][0]["message"],
            "unit": None,
            "ids": [9],
            "details": {"call": "list", "warning": KOAN_WARNING},
        }])

    def test_list_passes_them_on(self):
        self.fake_koan(list="warn")
        _, out = self.shingi("list")
        self.assertEqual([w["kind"] for w in out["warnings"]], ["koan-warning"])

    def test_create_passes_on_every_calls_warnings(self):
        self.fake_koan(create_batch="warn", block="warn")
        status, out = self.shingi("create", "HOME-1/a", "group")
        self.assertEqual(status, 0, out)
        self.assertEqual(
            [(w["kind"], w["details"]["call"]) for w in out["warnings"]],
            [("koan-warning", "create-batch"), ("koan-warning", "block")],
        )

    def test_a_failed_calls_warnings_come_with_the_error(self):
        self.fake_koan(list="warn-error")
        status, out = self.shingi("create", "HOME-1/a", "group")
        self.assertEqual(status, 1)
        self.assertEqual(out["error"]["kind"], "koan-failed")
        self.assertEqual([w["kind"] for w in out["warnings"]], ["koan-warning"])

    def test_a_failed_reads_warnings_come_with_koan_failed(self):
        self.fake_koan(list="warn-error")
        _, out = self.shingi("where", "HOME-1")
        self.assertEqual([w["kind"] for w in out["warnings"]], ["koan-failed", "koan-warning"])

if __name__ == "__main__":
    unittest.main()
