import unittest

from support import ShingiTestCase


class InvalidNameTest(ShingiTestCase):
    """A bad path is invalid-name, naming its first bad segment and why."""

    def details(self, *args):
        status, out = self.shingi(*args)
        self.assertEqual(status, 1, out)
        self.assertEqual(out["error"]["kind"], "invalid-name", out)
        return out["error"]["details"]

    def test_each_reason(self):
        for path, index, segment, reason in (
            ("", 0, "", "empty"),
            ("/HOME-1", 0, "", "empty"),
            ("HOME-1/", 1, "", "empty"),
            ("HOME-1//a", 1, "", "empty"),
            ("HOME-1/a b", 1, "a b", "characters"),
            ("HOME-1/é", 1, "é", "characters"),
            ("x" * 65, 0, "x" * 65, "length"),
            ("HOME-1/-a", 1, "-a", "hyphen"),
            ("a-/b c", 0, "a-", "hyphen"),
        ):
            with self.subTest(path):
                self.assertEqual(self.details("where", path),
                                 {"path": path, "index": index, "segment": segment, "reason": reason})

    def test_create_and_adopt_limit_the_whole_path(self):
        path = "x" * 64 + "/" + "x" * 64 + "/" + "x" * 64  # 194 characters
        self.assertEqual(len(path), 194)
        for command in ("create", "adopt"):
            with self.subTest(command):
                self.assertEqual(self.details(command, path, "group"),
                                 {"path": path, "index": None, "segment": None, "reason": "path-length"})

    def test_193_characters_is_fine(self):
        path = "x" * 64 + "/" + "x" * 64 + "/" + "x" * 63
        self.assertEqual(len(path), 193)
        parts = path.split("/")
        for i in range(1, len(parts) + 1):
            status, out = self.shingi("create", "/".join(parts[:i]), "group")
            self.assertEqual(status, 0, out)

    def test_where_has_no_length_limit(self):
        path = "/".join(["x" * 64] * 4)
        self.assertEqual(self.details("where", path + "/-")["reason"], "hyphen")
        status, out = self.shingi("where", path)
        self.assertEqual(out["error"]["kind"], "not-found")


if __name__ == "__main__":
    unittest.main()
