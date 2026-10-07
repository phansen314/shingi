"""Operations: the domain layer (see operations.md).

Each operation takes its input and the --config file, and returns its result and its warnings.
"""

import errno
import json
import os
import uuid
from importlib.metadata import version as package_version

from shingi import inputs, koan, rules as rules_file, units
from shingi.envelope import OperationError


def version(inp, config):
    inputs.check("version", inp)
    return {"version": package_version("shingi")}, []


def kinds(inp, config):
    inputs.check("kinds", inp)
    rules = rules_file.load(config)
    return {
        "kinds": [
            {"name": name, "description": kind.get("description", ""), "suggests": kind.get("suggests", [])}
            for name, kind in sorted(rules.kinds.items(), key=lambda item: item[0].encode())
        ]
    }, []


def where(inp, config):
    inputs.check("where", inp)
    rules = rules_file.load(config)
    return units.read_unit(rules, named_unit(rules, inp))


def named_unit(rules, inp):
    """The path of the unit `where` and `context` report: `unit`, or the one `cwd` is in."""
    if "cwd" in inp:
        return units.resolve_directory(rules, inp["cwd"])
    path = inp["unit"]
    units.check_path(path)
    units.resolve(rules, path)
    return path


def context(inp, config):
    inputs.check("context", inp)
    rules = rules_file.load(config)
    path = named_unit(rules, inp)
    manifest, warnings = units.check_manifest(rules, path)
    start = done = tasks = None
    if manifest is not None:
        kfolder = units.koan_folder(rules, path)
        try:
            found, koan_warnings = koan.list_tasks(kfolder, recursive=False, tags=())
        except OperationError as error:
            if error.kind != "koan-failed":
                raise
            warnings += units.koan_failed(error, path)
        else:
            start = units.match(found, kfolder, manifest["id"], "shingi-start")
            done = units.match(found, kfolder, manifest["id"], "shingi-done")
            warnings += units.missing_tasks(path, start, done) + koan_warnings
            tasks = [
                {k: t[k] for k in ("id", "title", "readiness", "blocking", "tags", "notes_path")}
                for t in sorted(found, key=lambda t: t["id"])
                if t["folder"] == kfolder and t["readiness"] != "done"
            ]
    parent = units.parent_of(path)
    segments = path.split("/")
    ancestors = []
    for i in range(1, len(segments)):
        ancestor = "/".join(segments[:i])
        folder = units.working_folder(rules, ancestor)
        try:
            ancestor_manifest = units.read_manifest(folder)
        except units.UnusableManifest:
            ancestor_manifest = None
        ancestors.append({
            "path": ancestor,
            "id": ancestor_manifest and ancestor_manifest["id"],
            "kind": ancestor_manifest and ancestor_manifest["kind"],
            "title": units.read_title(folder),
        })
    return {
        "unit": units.build_unit(rules, path, manifest, start, done),
        "ancestors": ancestors,
        "notes": units.read_notes(units.working_folder(rules, path)),
        "parent_notes": None if parent is None else units.read_notes(units.working_folder(rules, parent)),
        "tasks": tasks,
    }, units.sort_warnings(warnings)


def list_units(inp, config):
    inputs.check("list", inp)
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
    try:
        tasks, koan_warnings = koan.list_tasks(folder, recursive=True)
    except OperationError as error:
        if error.kind != "koan-failed":
            raise
        tasks, koan_warnings = None, units.koan_failed(error, None)
    warnings += koan_warnings
    found = []
    for path, manifest in manifests.items():
        start = done = None
        if manifest is not None and tasks is not None:
            kfolder = units.koan_folder(rules, path)
            start = units.match(tasks, kfolder, manifest["id"], "shingi-start")
            done = units.match(tasks, kfolder, manifest["id"], "shingi-done")
            warnings += units.missing_tasks(path, start, done)
        found.append(units.build_unit(rules, path, manifest, start, done))

    warnings += [orphan_task(rules, task, by_id) for task in tasks or [] if not claimed(rules, task, by_id)]
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
    inputs.check("create", inp)
    return make_unit(inp, config, adopting=False)


def adopt(inp, config):
    inputs.check("adopt", inp)
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
            parent_start, parent_done, koan_warnings = units.find_tasks(rules, parent, parent_manifest["id"])
            warnings += koan_warnings
        for role, task in (("start", parent_start), ("done", parent_done)):
            if task is None:
                warnings.append(units.warning(
                    "parent-unlinked",
                    f"{parent}'s {role} task wasn't found, so {path} isn't linked to it",
                    path,
                    details={"parent": parent, "role": role, "reason": reason},
                ))

    unit_id = str(uuid.uuid4())
    made = {"koan_folders": [], "tasks": [], "blocked": None, "files": []}
    try:
        write_unit(rules, inp, path, kind, unit_id, adopting, parent, parent_start, parent_done, made, warnings)
    except Exception as exc:
        raise with_partial(exc, made, warnings)
    unit, read_warnings = units.read_unit(rules, path)
    return {"unit": unit}, units.sort_warnings(warnings + read_warnings)


def write_unit(rules, inp, path, kind, unit_id, adopting, parent, parent_start, parent_done, made, warnings):
    """create's steps 3 to 5: make the tasks, link the parent, write the files, recording in
    `made` what each step made."""
    try:
        batch, koan_warnings = koan.create_batch({
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
    except OperationError as error:
        koan_partial = (error.details.get("error") or {}).get("partial") or {}
        made["koan_folders"] = list(koan_partial.get("folders_created", []))
        made["tasks"] = list(koan_partial.get("ids", []))
        raise
    made["koan_folders"] = list(batch["folders_created"])
    made["tasks"] = [batch["refs"]["start"], batch["refs"]["done"]]
    warnings += koan_warnings

    if parent_done and parent_done["readiness"] == "done":
        warnings.append(units.warning(
            "parent-done",
            f"{parent}'s done task {parent_done['id']} is already done, so {path} doesn't block it",
            path,
            [parent_done["id"]],
            {"parent": parent},
        ))
    elif parent_done:
        added = [batch["refs"]["done"]]
        _, koan_warnings = koan.block(parent_done["id"], added)
        made["blocked"] = {"task": parent_done["id"], "added": added}
        warnings += koan_warnings

    folder = units.working_folder(rules, path)
    if not adopting:
        try:
            folder.mkdir()
        except FileExistsError:
            raise name_taken(path, folder.name, entry_type(folder))
        except OSError as exc:
            raise io_error(exc, folder)
        made["files"].append(str(folder))
    title = inp.get("title") or path.rpartition("/")[2]
    notes = folder / units.NOTES
    try:
        with open(notes, "x", encoding="utf-8") as f:
            made["files"].append(str(notes))
            f.write(notes_text(title, inp.get("notes", "")))
    except FileExistsError:
        pass
    except OSError as exc:
        raise io_error(exc, notes)
    write_manifest(path, folder, {"schema": 1, "id": unit_id, "kind": kind})


def with_partial(exc, made, warnings):
    """`exc` as the error to report, with the warnings gathered before it and, when anything was
    made, `made` as its partial."""
    error = exc if isinstance(exc, OperationError) else OperationError(
        "internal", f"unexpected {type(exc).__name__}: {exc}"
    )
    error.warnings = units.sort_warnings(warnings + error.warnings)
    if made["koan_folders"] or made["tasks"] or made["blocked"] or made["files"]:
        error.partial = made
    return error


def io_error(exc, path):
    return OperationError("io", f"{path}: {exc.strerror}", {"path": str(path), "code": errno.errorcode.get(exc.errno)})


def notes_text(title, notes):
    """uow.md as create writes it: the title, then, after a blank line, the notes, ending in a newline."""
    text = f"# {title}\n"
    if notes:
        text += "\n" + notes + ("" if notes.endswith("\n") else "\n")
    return text


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


def write_manifest(path, folder, manifest):
    """Write uow.json once: a hidden temp file, flushed, then hard-linked into place. A temp file
    that can't be removed is left: it is hidden."""
    temp = folder / f".{units.MANIFEST}.{uuid.uuid4().hex}.tmp"
    target = folder / units.MANIFEST
    writing = temp
    try:
        with open(temp, "x", encoding="utf-8") as f:
            f.write(json.dumps(manifest, indent=2) + "\n")
            f.flush()
            os.fsync(f.fileno())
        writing = target
        os.link(temp, target)
    except FileExistsError:
        raise OperationError("unit-exists", f"{path} already exists", {"manifest": str(target)})
    except OSError as exc:
        raise io_error(exc, writing)
    finally:
        try:
            temp.unlink()
        except OSError:
            pass
