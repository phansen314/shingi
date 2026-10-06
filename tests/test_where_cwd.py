import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from support import ShingiTestCase


class WhereFromDirectoryTest(ShingiTestCase):
    def setUp(self):
        super().setUp()
        for path in ("HOME-1", "HOME-1/foo-split", "HOME-1/foo-split/1-schema"):
            status, out = self.shingi("create", path, "group")
            self.assertEqual(status, 0, out)
        self.unit = self.working / "HOME-1" / "foo-split" / "1-schema"

    def where_in(self, directory):
        return self.shingi("where", cwd=directory)

    def test_names_the_unit_of_its_working_folder(self):
        status, out = self.where_in(self.unit)
        self.assertEqual(status, 0, out)
        self.assertEqual(out["result"]["path"], "HOME-1/foo-split/1-schema")

    def test_names_a_parent_unit_too(self):
        _, out = self.where_in(self.working / "HOME-1")
        self.assertEqual(out["result"]["path"], "HOME-1")

    def test_working_material_belongs_to_its_unit(self):
        material = self.unit / "logs" / "2026"
        material.mkdir(parents=True)
        (self.unit / "logs" / "2026" / "uow.json").write_text("{}")  # below material, never looked at
        _, out = self.where_in(material)
        self.assertEqual(out["result"]["path"], "HOME-1/foo-split/1-schema")

    def test_follows_symlinks(self):
        link = Path(tempfile.mkdtemp()) / "here"
        self.addCleanup(shutil.rmtree, link.parent)
        link.symlink_to(self.unit)
        _, out = self.where_in(link)
        self.assertEqual(out["result"]["path"], "HOME-1/foo-split/1-schema")

    def test_the_working_root_is_in_no_unit(self):
        status, out = self.where_in(self.working)
        self.assertEqual(status, 1)
        self.assertEqual(out["error"]["kind"], "not-found")
        self.assertEqual(out["error"]["details"]["reason"], "no-unit")
        self.assertEqual(out["error"]["details"]["cwd"], str(self.working))

    def test_a_plain_folder_is_in_no_unit(self):
        plain = self.working / "scratch" / "HOME-1"
        plain.mkdir(parents=True)
        _, out = self.where_in(plain)
        self.assertEqual(out["error"]["details"]["reason"], "no-unit")

    def test_outside_the_working_root(self):
        outside = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, outside)
        status, out = self.where_in(outside)
        self.assertEqual(status, 1)
        self.assertEqual(out["error"]["details"]["reason"], "outside-root")

    def test_a_removed_directory_is_io(self):
        gone = self.unit / "gone"
        gone.mkdir()
        proc = subprocess.run(
            ["sh", "-c", 'cd "$1" && rmdir "$1" && exec "$2" where --config "$3"', "sh",
             str(gone), shutil.which("shingi"), str(self.config)],
            env=self.env, capture_output=True,
        )
        out = json.loads(proc.stdout)
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(out["error"]["kind"], "io")
        self.assertEqual(out["error"]["details"]["path"], ".")


if __name__ == "__main__":
    unittest.main()
