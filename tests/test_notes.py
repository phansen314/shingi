import unittest

from support import ShingiTestCase


class NotesTest(ShingiTestCase):
    def notes(self, path="HOME-1"):
        return (self.working / path / "uow.md").read_text()

    def test_notes_follow_the_title(self):
        status, out = self.shingi("create", "HOME-1", "group", "--title", "Payment retries", "--notes", "Retry failed payments.")
        self.assertEqual(status, 0, out)
        self.assertEqual(self.notes(), "# Payment retries\n\nRetry failed payments.\n")
        self.assertEqual(out["result"]["unit"]["title"], "Payment retries")

    def test_a_trailing_newline_isnt_doubled(self):
        self.shingi("create", "HOME-1", "group", "--notes", "one\ntwo\n")
        self.assertEqual(self.notes(), "# HOME-1\n\none\ntwo\n")

    def test_empty_notes_are_no_notes(self):
        self.shingi("create", "HOME-1", "group", "--notes", "")
        self.assertEqual(self.notes(), "# HOME-1\n")

    def test_notes_from_stdin(self):
        status, out = self.shingi("create", "HOME-1", "group", "--notes-file", "-", stdin="Story: retry.\nü\n".encode())
        self.assertEqual(status, 0, out)
        self.assertEqual(self.notes(), "# HOME-1\n\nStory: retry.\nü\n")

    def test_notes_from_a_file(self):
        file = self.working.parent / "notes.md"
        file.write_text("## Context\n\nfrom a file")
        self.shingi("create", "HOME-1", "group", f"--notes-file={file}")
        self.assertEqual(self.notes(), "# HOME-1\n\n## Context\n\nfrom a file\n")

    def test_both_options_are_a_usage_error(self):
        status, out = self.shingi("create", "HOME-1", "group", "--notes", "a", "--notes-file", "-")
        self.assertEqual(status, 2)
        self.assertEqual(out["error"]["kind"], "usage")
        self.assertFalse((self.working / "HOME-1").exists())

    def test_a_missing_file_is_io(self):
        status, out = self.shingi("create", "HOME-1", "group", "--notes-file", "/nonexistent/notes.md")
        self.assertEqual(status, 1)
        self.assertEqual(out["error"]["kind"], "io")
        self.assertEqual(out["error"]["details"], {"path": "/nonexistent/notes.md", "code": "ENOENT"})
        self.assertFalse((self.working / "HOME-1").exists())

    def test_invalid_utf8_is_invalid_input(self):
        status, out = self.shingi("create", "HOME-1", "group", "--notes-file", "-", stdin=b"bad \xff")
        self.assertEqual(status, 1)
        self.assertEqual(out["error"]["kind"], "invalid-input")
        self.assertEqual(out["error"]["details"]["problems"][0]["field"], "/notes")

    def test_adopt_takes_no_notes(self):
        (self.working / "HOME-1").mkdir()
        status, out = self.shingi("adopt", "HOME-1", "group", "--notes", "x")
        self.assertEqual(status, 2)
        self.assertEqual(out["error"]["kind"], "usage")


if __name__ == "__main__":
    unittest.main()
