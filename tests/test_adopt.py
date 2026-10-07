import unittest

from support import ShingiTestCase


class AdoptTest(ShingiTestCase):
    def setUp(self):
        super().setUp()
        self.folder = self.working / "HOME-1"
        (self.folder / "drafts").mkdir(parents=True)
        (self.folder / "drafts" / "plan.txt").write_text("the plan\n")

    def test_adopts_a_folder_and_keeps_its_contents(self):
        status, out = self.shingi("adopt", "HOME-1", "group", "--title", "Payment retries")
        self.assertEqual(status, 0, out)
        self.assertEqual(out["warnings"], [])
        unit = out["result"]["unit"]
        self.assertEqual(unit["title"], "Payment retries")
        self.assertEqual(unit["state"], "not-started")
        self.assertEqual((self.folder / "drafts" / "plan.txt").read_text(), "the plan\n")
        self.assertEqual(sorted(p.name for p in self.folder.iterdir()), ["drafts", "uow.json", "uow.md"])

    def test_keeps_existing_notes_without_a_warning(self):
        (self.folder / "uow.md").write_text("# What I had\n\nnotes\n")
        status, out = self.shingi("adopt", "HOME-1", "group", "--title", "Payment retries")
        self.assertEqual(status, 0, out)
        self.assertEqual((self.folder / "uow.md").read_text(), "# What I had\n\nnotes\n")
        self.assertEqual(out["result"]["unit"]["title"], "What I had")
        self.assertEqual(out["warnings"], [])

    def test_kept_notes_without_a_heading_have_the_empty_title(self):
        (self.folder / "uow.md").write_text("just notes\n")
        _, out = self.shingi("adopt", "HOME-1", "group")
        self.assertEqual(out["result"]["unit"]["title"], "")

    def test_links_to_its_parent(self):
        _, out = self.shingi("adopt", "HOME-1", "group")
        parent = out["result"]["unit"]
        (self.folder / "spike").mkdir()
        status, out = self.shingi("adopt", "HOME-1/spike", "branch")
        self.assertEqual(status, 0, out)
        child = out["result"]["unit"]
        self.assertEqual(self.koan_show(child["start"]["id"])["blocked_by"], [parent["start"]["id"]])
        self.assertIn(child["done"]["id"], self.koan_show(parent["done"]["id"])["blocked_by"])

    def test_a_missing_folder_is_not_found(self):
        status, out = self.shingi("adopt", "HOME-2", "group")
        self.assertEqual(status, 1)
        self.assertEqual(out["error"]["kind"], "not-found")
        self.assertEqual(out["error"]["details"], {"unit": "HOME-2", "missing": "HOME-2", "cwd": None, "reason": "no-folder"})
        self.assertFalse((self.working / "HOME-2").exists())

    def test_a_unit_is_unit_exists(self):
        self.shingi("adopt", "HOME-1", "group")
        status, out = self.shingi("adopt", "HOME-1", "group")
        self.assertEqual(status, 1)
        self.assertEqual(out["error"]["kind"], "unit-exists")

    def test_a_file_is_name_taken(self):
        (self.working / "HOME-2").write_text("")
        _, out = self.shingi("adopt", "HOME-2", "group")
        self.assertEqual(out["error"]["kind"], "name-taken")
        self.assertEqual(out["error"]["details"], {"entry": "HOME-2", "type": "file"})

    def test_another_case_is_name_taken(self):
        status, out = self.shingi("adopt", "home-1", "group")
        self.assertEqual(status, 1)
        self.assertEqual(out["error"]["details"], {"entry": "HOME-1", "type": "folder"})


class CreateRefusesWhatIsThereTest(ShingiTestCase):
    def test_an_existing_folder_is_name_taken(self):
        (self.working / "HOME-1").mkdir()
        status, out = self.shingi("create", "HOME-1", "group")
        self.assertEqual(status, 1)
        self.assertEqual(out["error"]["kind"], "name-taken")
        self.assertEqual(out["error"]["details"], {"entry": "HOME-1", "type": "folder"})
        self.assertEqual(self.koan("list", "--readiness", "ready,blocked,done")["tasks"], [])

    def test_a_file_is_name_taken(self):
        (self.working / "HOME-1").write_text("")
        _, out = self.shingi("create", "HOME-1", "group")
        self.assertEqual(out["error"]["details"], {"entry": "HOME-1", "type": "file"})

    def test_a_unit_in_another_case_is_name_taken(self):
        self.shingi("create", "HOME-1", "group")
        _, out = self.shingi("create", "home-1", "group")
        self.assertEqual(out["error"]["details"], {"entry": "HOME-1", "type": "unit"})


if __name__ == "__main__":
    unittest.main()
