"""Operations: the domain layer (see operations.md)."""

import json
import os
import uuid
from importlib.metadata import version as package_version

from shingi import koan, rules as rules_file, units
from shingi.envelope import OperationError


def version(inp, config):
    return {"version": package_version("shingi")}


def create(inp, config):
    rules = rules_file.load(config)
    path, kind = inp["path"], inp["kind"]
    units.check_path(path)
    if kind not in rules.kinds:
        raise OperationError(
            "unknown-kind", f"kind {kind!r} is not defined", {"kind": kind, "defined": sorted(rules.kinds)}
        )
    if "/" in path:
        # Nested units are the next slice.
        raise OperationError("internal", "nested units are not built yet")
    folder = units.working_folder(rules, path)
    if (folder / units.MANIFEST).exists():
        raise OperationError("unit-exists", f"{path} already exists", {"manifest": str(folder / units.MANIFEST)})

    unit_id = str(uuid.uuid4())
    koan.create_batch({
        "folder": units.koan_folder(rules, path),
        "tasks": [
            {
                "ref": "start",
                "title": f"Start: {path}",
                "tags": ["shingi", "shingi-start"],
                "extra": {"source": "shingi-start", "shingi-unit": unit_id},
            },
            {
                "ref": "done",
                "title": f"Done: {path}",
                "tags": ["shingi", "shingi-done"],
                "extra": {"source": "shingi-done", "shingi-unit": unit_id},
                "blocked_by": ["start"],
            },
        ],
    })

    folder.mkdir(exist_ok=True)
    title = inp.get("title") or path.rpartition("/")[2]
    try:
        with open(folder / units.NOTES, "x", encoding="utf-8") as f:
            f.write(f"# {title}\n")
    except FileExistsError:
        pass
    write_manifest(folder, {"schema": 1, "id": unit_id, "kind": kind})
    return {"unit": units.read_unit(rules, path)}


def write_manifest(folder, manifest):
    """Write uow.json once: a hidden temp file, flushed, then hard-linked into place."""
    temp = folder / f".{units.MANIFEST}.{uuid.uuid4().hex}.tmp"
    with open(temp, "x", encoding="utf-8") as f:
        f.write(json.dumps(manifest, indent=2) + "\n")
        f.flush()
        os.fsync(f.fileno())
    try:
        os.link(temp, folder / units.MANIFEST)
    finally:
        temp.unlink()
