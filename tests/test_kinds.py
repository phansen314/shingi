import unittest

from support import ShingiTestCase


class KindsTest(ShingiTestCase):
    def test_reports_every_kind_in_name_order(self):
        status, out = self.shingi("kinds")
        self.assertEqual(status, 0, out)
        self.assertEqual(out["result"], {"kinds": [
            {"name": "branch", "description": "Work on one branch of one repository.", "suggests": []},
            {"name": "group", "description": "Work gathered under one name.", "suggests": ["group", "branch"]},
        ]})

    def test_a_missing_rules_file_is_invalid_rules(self):
        self.config.unlink()
        status, out = self.shingi("kinds")
        self.assertEqual(status, 1)
        self.assertEqual(out["error"]["kind"], "invalid-rules")
        self.assertEqual(out["error"]["details"]["reason"], "missing")


if __name__ == "__main__":
    unittest.main()
