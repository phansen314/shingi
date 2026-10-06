"""Operations: the domain layer (see operations.md)."""

import json
import os
import uuid
from importlib.metadata import version as package_version

from shingi import koan, rules as rules_file, units
from shingi.envelope import OperationError


def version(inp, config):
    return {"version": package_version("shingi")}


def where(inp, config):
    rules = rules_file.load(config)
    path = inp["unit"]
    units.check_path(path)
    units.resolve(rules, path)
    return units.read_unit(rules, path)


def create(inp, config):
    rules = rules_file.load(config)
    path, kind = inp["path"], inp["kind"]
    units.check_path(path)
    if kind not in rules.kinds:
        raise OperationError(
            "unknown-kind", f"kind {kind!r} is not defined", {"kind": kind, "defined": sorted(rules.kinds)}
        )
    parent = units.parent_of(path)
    parent_start = parent_done = None
    if parent is not None:
        try:
            units.resolve(rules, parent)
        except OperationError as error:
            raise OperationError(
                "parent-not-found",
                f"parent {parent} is not a unit",
                {"parent": parent, "missing": error.details["missing"]},
            )
    folder = units.working_folder(rules, path)
    if (folder / units.MANIFEST).exists():
        raise OperationError("unit-exists", f"{path} already exists", {"manifest": str(folder / units.MANIFEST)})
    if parent is not None:
        parent_id = units.read_manifest(units.working_folder(rules, parent))["id"]
        parent_start, parent_done = units.find_tasks(rules, parent, parent_id)

    unit_id = str(uuid.uuid4())
    made = koan.create_batch({
        "folder": units.koan_folder(rules, path),
        "tasks": [
            {
                "ref": "start",
                "title": f"Start: {path}",
                "tags": ["shingi", "shingi-start"],
                "extra": {"source": "shingi-start", "shingi-unit": unit_id},
                "blocked_by": [parent_start["id"]] if parent_start else [],
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
    if parent_done and parent_done["readiness"] != "done":
        koan.block(parent_done["id"], [made["refs"]["done"]])

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
