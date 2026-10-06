import unittest

from support import ShingiTestCase


class WhereTest(ShingiTestCase):
    def test_reports_the_unit_create_made(self):
        _, created = self.shingi("create", "HOME-1", "group", "--title", "Payment retries")
        status, out = self.shingi("where", "HOME-1")
        self.assertEqual(status, 0, out)
        self.assertEqual(out["result"], created["result"]["unit"])

    def test_state_follows_the_tasks(self):
        _, created = self.shingi("create", "HOME-1", "group")
        unit = created["result"]["unit"]

        self.koan("done", str(unit["start"]["id"]))
        _, out = self.shingi("where", "HOME-1")
        self.assertEqual(out["result"]["state"], "started")
        self.assertEqual(out["result"]["done"]["readiness"], "ready")

        self.koan("done", str(unit["done"]["id"]))
        _, out = self.shingi("where", "HOME-1")
        self.assertEqual(out["result"]["state"], "done")
        self.assertIsNotNone(out["result"]["done"]["completed_at"])

    def test_title_follows_the_notes(self):
        self.shingi("create", "HOME-1", "group")
        (self.working / "HOME-1" / "uow.md").write_text("\n# Renamed\n\nnotes\n")
        _, out = self.shingi("where", "HOME-1")
        self.assertEqual(out["result"]["title"], "Renamed")

    def test_a_missing_unit_is_not_found(self):
        status, out = self.shingi("where", "HOME-1")
        self.assertEqual(status, 1)
        self.assertEqual(out["error"]["kind"], "not-found")
        self.assertEqual(out["error"]["details"]["missing"], "HOME-1")

    def test_a_folder_without_a_manifest_is_not_found(self):
        (self.working / "scratch").mkdir()
        status, out = self.shingi("where", "scratch")
        self.assertEqual(status, 1)
        self.assertEqual(out["error"]["kind"], "not-found")

    def test_a_bad_path_is_invalid_name(self):
        status, out = self.shingi("where", "../etc")
        self.assertEqual(status, 1)
        self.assertEqual(out["error"]["kind"], "invalid-name")


if __name__ == "__main__":
    unittest.main()
