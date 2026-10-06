import json
import unittest

from support import ShingiTestCase

UUID = "3f6c2a9e-8b1d-4e47-9c05-7a2d41e6b0f3"

CORRUPT = {
    "not JSON": b"{",
    "not an object": b"[]",
    "a missing field": json.dumps({"schema": 1, "id": UUID}).encode(),
    "an extra field": json.dumps({"schema": 1, "id": UUID, "kind": "group", "x": 1}).encode(),
    "a string schema": json.dumps({"schema": "1", "id": UUID, "kind": "group"}).encode(),
    "a boolean schema": json.dumps({"schema": True, "id": UUID, "kind": "group"}).encode(),
    "an uppercase id": json.dumps({"schema": 1, "id": UUID.upper(), "kind": "group"}).encode(),
    "a non-string kind": json.dumps({"schema": 1, "id": UUID, "kind": 5}).encode(),
    "a duplicate key": b'{"schema": 1, "id": "%s", "kind": "group", "kind": "branch"}' % UUID.encode(),
    "invalid UTF-8": b'{"schema": 1, "id": "%s", "kind": "gr\xffoup"}' % UUID.encode(),
}


class ManifestTest(ShingiTestCase):
    def create(self, path, kind="group"):
        status, out = self.shingi("create", path, kind)
        self.assertEqual(status, 0, out)
        return out["result"]["unit"]

    def break_manifest(self, path, content):
        (self.working / path / "uow.json").write_bytes(content)

    def assert_unusable(self, path, reason):
        status, out = self.shingi("where", path)
        self.assertEqual(status, 0, out)
        unit = out["result"]
        for field in ("id", "kind", "state", "start", "done"):
            self.assertIsNone(unit[field], field)
        self.assertEqual(out["warnings"], [{
            "kind": "unsupported-manifest",
            "message": out["warnings"][0]["message"],
            "unit": path,
            "ids": [],
            "details": {"path": str(self.working.resolve() / path / "uow.json"), "reason": reason},
        }])

    def test_corrupt_manifests(self):
        self.create("HOME-1")
        for name, content in CORRUPT.items():
            with self.subTest(name):
                self.break_manifest("HOME-1", content)
                self.assert_unusable("HOME-1", "corrupt")

    def test_an_unsupported_schema(self):
        self.create("HOME-1")
        self.break_manifest("HOME-1", json.dumps({"schema": 2, "id": UUID, "kind": "group"}).encode())
        self.assert_unusable("HOME-1", "unsupported-format")

    def test_an_unreadable_manifest(self):
        self.create("HOME-1")
        manifest = self.working / "HOME-1" / "uow.json"
        manifest.chmod(0)
        self.addCleanup(manifest.chmod, 0o644)
        self.assert_unusable("HOME-1", "unreadable")

    def test_where_still_reports_what_fixing_it_needs(self):
        self.create("HOME-1", "group")
        self.create("HOME-1/a", "branch")
        self.break_manifest("HOME-1", b"{")
        _, out = self.shingi("where", "HOME-1")
        unit = out["result"]
        self.assertEqual(unit["title"], "HOME-1")
        self.assertEqual(unit["children"], [{"path": "HOME-1/a", "kind": "branch"}])
        self.assertEqual(unit["working_folder"], str(self.working.resolve() / "HOME-1"))

    def test_a_childs_unusable_manifest_is_a_null_kind_not_a_warning(self):
        self.create("HOME-1")
        self.create("HOME-1/a")
        self.break_manifest("HOME-1/a", b"{")
        _, out = self.shingi("where", "HOME-1")
        self.assertEqual(out["result"]["children"], [{"path": "HOME-1/a", "kind": None}])
        self.assertEqual(out["warnings"], [])

    def test_list_goes_on_past_it(self):
        self.create("HOME-1")
        broken = self.create("HOME-1/a")
        self.create("HOME-1/a/x")
        self.create("HOME-2")
        self.break_manifest("HOME-1/a", b"{")
        status, out = self.shingi("list")
        self.assertEqual(status, 0, out)
        self.assertEqual([u["path"] for u in out["result"]["units"]], ["HOME-1", "HOME-1/a", "HOME-1/a/x", "HOME-2"])
        self.assertIsNone(out["result"]["units"][1]["id"])
        self.assertEqual(out["result"]["units"][2]["state"], "not-started")
        # Its tasks can't be matched, so they are orphans too; orphan-task sorts first.
        self.assertEqual(
            [(w["kind"], w["unit"], w["ids"]) for w in out["warnings"]],
            [
                ("orphan-task", None, [broken["start"]["id"]]),
                ("orphan-task", None, [broken["done"]["id"]]),
                ("unsupported-manifest", "HOME-1/a", []),
            ],
        )

    def test_create_under_it_leaves_both_links_out(self):
        self.create("HOME-1")
        self.break_manifest("HOME-1", b"{")
        status, out = self.shingi("create", "HOME-1/a", "group")
        self.assertEqual(status, 0, out)
        child = out["result"]["unit"]
        self.assertEqual(self.koan_show(child["start"]["id"])["blocked_by"], [])
        self.assertEqual(
            [(w["kind"], w["unit"], w["details"]) for w in out["warnings"]],
            [
                ("parent-unlinked", "HOME-1/a", {"parent": "HOME-1", "role": "start", "reason": "unsupported-manifest"}),
                ("parent-unlinked", "HOME-1/a", {"parent": "HOME-1", "role": "done", "reason": "unsupported-manifest"}),
            ],
        )


if __name__ == "__main__":
    unittest.main()
