"""Operations: the domain layer (see operations.md).

Each operation takes its input and the --config file, and returns its result and its warnings.
"""

import json
import os
import uuid
from importlib.metadata import version as package_version

from shingi import koan, rules as rules_file, units
from shingi.envelope import OperationError


def version(inp, config):
    return {"version": package_version("shingi")}, []


def kinds(inp, config):
    rules = rules_file.load(config)
    return {
        "kinds": [
            {"name": name, "description": kind.get("description", ""), "suggests": kind.get("suggests", [])}
            for name, kind in sorted(rules.kinds.items(), key=lambda item: item[0].encode())
        ]
    }, []


def where(inp, config):
    rules = rules_file.load(config)
    if "cwd" in inp:
        path = units.resolve_directory(rules, inp["cwd"])
    else:
        path = inp["unit"]
        units.check_path(path)
        units.resolve(rules, path)
    return units.read_unit(rules, path)


def list_units(inp, config):
    rules = rules_file.load(config)
    root = inp.get("unit")
    if root is not None:
        units.check_path(root)
        units.resolve(rules, root)
    manifests, warnings = {}, []
    for path in units.walk(rules, root):
        manifests[path], problems = units.check_manifest(rules, path)
        warnings += problems
    by_id = {m["id"]: path for path, m in manifests.items() if m is not None}

    folder = rules.koan_root if root is None else units.koan_folder(rules, root)
    tasks = koan.list_tasks(folder, recursive=True)
    found = []
    for path, manifest in manifests.items():
        start = done = None
        if manifest is not None:
            kfolder = units.koan_folder(rules, path)
            start = units.match(tasks, kfolder, manifest["id"], "shingi-start")
            done = units.match(tasks, kfolder, manifest["id"], "shingi-done")
            warnings += units.missing_tasks(path, start, done)
        found.append(units.build_unit(rules, path, manifest, start, done))

    warnings += [orphan_task(rules, task, by_id) for task in tasks if not claimed(rules, task, by_id)]
    return {"root": root, "units": found}, units.sort_warnings(warnings)


def claimed(rules, task, by_id):
    """Whether `task` is a start or done task of a unit list found, in that unit's koan folder."""
    path = by_id.get(task["extra"].get("shingi-unit"))
    return (
        path is not None
        and task["folder"] == units.koan_folder(rules, path)
        and task["extra"].get("source") in ("shingi-start", "shingi-done")
    )


def orphan_task(rules, task, by_id):
    extra = task["extra"]
    source, unit_id = extra.get("source"), extra.get("shingi-unit")
    return {
        "kind": "orphan-task",
        "message": f"task {task['id']} in {task['folder']} matches no unit",
        "unit": by_id.get(unit_id),
        "ids": [task["id"]],
        "details": {
            "folder": task["folder"],
            "source": source if isinstance(source, str) else None,
            "shingi_unit": unit_id if isinstance(unit_id, str) else None,
        },
    }


def create(inp, config):
    return make_unit(inp, config, adopting=False)


def adopt(inp, config):
    return make_unit(inp, config, adopting=True)


def make_unit(inp, config, adopting):
    """create, or with `adopting`, adopt: they differ only in the working folder."""
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
    check_entry(folder, path, adopting)
    warnings = []
    if parent is not None:
        parent_manifest, _ = units.check_manifest(rules, parent)
        if parent_manifest is None:
            reason = "unsupported-manifest"
        else:
            reason = "missing-task"
            parent_start, parent_done = units.find_tasks(rules, parent, parent_manifest["id"])
        for role, task in (("start", parent_start), ("done", parent_done)):
            if task is None:
                warnings.append(units.warning(
                    "parent-unlinked",
                    f"{parent}'s {role} task wasn't found, so {path} isn't linked to it",
                    path,
                    details={"parent": parent, "role": role, "reason": reason},
                ))

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
    if parent_done and parent_done["readiness"] == "done":
        warnings.append(units.warning(
            "parent-done",
            f"{parent}'s done task {parent_done['id']} is already done, so {path} doesn't block it",
            path,
            [parent_done["id"]],
            {"parent": parent},
        ))
    elif parent_done:
        koan.block(parent_done["id"], [made["refs"]["done"]])

    if not adopting:
        try:
            folder.mkdir()
        except FileExistsError:
            raise name_taken(path, folder.name, "folder")
    title = inp.get("title") or path.rpartition("/")[2]
    try:
        with open(folder / units.NOTES, "x", encoding="utf-8") as f:
            f.write(f"# {title}\n")
    except FileExistsError:
        pass
    write_manifest(folder, {"schema": 1, "id": unit_id, "kind": kind})
    unit, read_warnings = units.read_unit(rules, path)
    return {"unit": unit}, units.sort_warnings(warnings + read_warnings)


def check_entry(folder, path, adopting):
    """Check what is at the new unit's name in its parent's folder (operations.md, create step 1.4)."""
    name = folder.name
    if (folder / units.MANIFEST).is_file():
        raise OperationError("unit-exists", f"{path} already exists", {"manifest": str(folder / units.MANIFEST)})
    for entry in sorted(folder.parent.iterdir(), key=lambda e: e.name.encode()):
        if entry.name.encode().lower() != name.encode().lower():  # ASCII case only
            continue
        # Only adopt may find something at the name: a folder with exactly it.
        if entry.name != name or not adopting or not entry.is_dir():
            raise name_taken(path, entry.name, entry_type(entry))
    if adopting and not folder.is_dir():
        raise OperationError(
            "not-found",
            f"there is no folder {path} to adopt",
            {"unit": path, "missing": path, "cwd": None, "reason": "no-folder"},
        )


def entry_type(entry):
    if not entry.is_dir():
        return "file"
    return "unit" if (entry / units.MANIFEST).is_file() else "folder"


def name_taken(path, entry, kind):
    return OperationError("name-taken", f"{entry} is in the way of {path}", {"entry": entry, "type": kind})


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
