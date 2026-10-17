"""Units on disk and their tasks in koan (see operations.md, Shared rules)."""

import errno
import json
import os
import re
from pathlib import Path

from shingi import koan
from shingi.envelope import OperationError

NAME = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,62}[A-Za-z0-9])?"
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
MANIFEST = "uow.json"
NOTES = "uow.md"
SCHEMAS = (1,)
MARKER_DIR = ".shingi"  # a bound folder's marker (see design-spec.md, Markers)
MARKER = "unit.json"
IGNORE = ".gitignore"


class Unusable(Exception):
    """A uow.json or marker shingi can't use; `reason` is unreadable, unsupported-format, or corrupt."""

    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def warning(kind, message, unit, ids=(), details=None):
    return {"kind": kind, "message": message, "unit": unit, "ids": list(ids), "details": details or {}}


MAX_PATH = 193  # so a start task's title, "Start: <path>", fits koan's 200


def check_path(path, field, creating=False):
    """Raise invalid-name, naming the first bad segment, unless `path` is a unit path; and when
    `creating`, unless it is at most MAX_PATH characters. `field` is a JSON Pointer to the input
    field the path came from."""
    for index, segment in enumerate(path.split("/")):
        reason = segment_problem(segment)
        if reason is not None:
            raise OperationError("invalid-name", f"invalid unit path {path!r}: segment {index} is {reason}", {
                "field": field, "path": path, "index": index, "segment": segment, "reason": reason,
            })
    if creating and len(path) > MAX_PATH:
        raise OperationError(
            "invalid-name",
            f"{path!r} is over {MAX_PATH} characters",
            {"field": field, "path": path, "index": None, "segment": None, "reason": "path-length"},
        )


def segment_problem(segment):
    if segment == "":
        return "empty"
    if not re.fullmatch(r"[A-Za-z0-9-]+", segment):
        return "characters"
    if len(segment) > 64:
        return "length"
    if segment.startswith("-") or segment.endswith("-"):
        return "hyphen"
    return None


def resolve(rules, path):
    """Raise not-found unless every folder on `path` exists, by its exact name, and holds a manifest."""
    segments = path.split("/")
    depth = unit_depth(rules, path)
    if depth < len(segments):
        missing = "/".join(segments[: depth + 1])
        raise OperationError(
            "not-found",
            f"{path} is not a unit: {missing} is not",
            {"unit": path, "missing": missing, "cwd": None, "reason": "not-a-unit", "marker": None},
        )


def unit_depth(rules, path):
    """How many of `path`'s leading segments are units: each folder down to there exists, by its
    exact name, and holds a manifest."""
    folder = rules.working_root
    segments = path.split("/")
    for i, segment in enumerate(segments):
        folder = folder / segment
        # The working root may not exist yet: then nothing is a unit.
        exact = folder.parent.is_dir() and segment in os.listdir(folder.parent)
        if not (exact and folder.is_dir() and (folder / MANIFEST).is_file()):
            return i
    return len(segments)


def path_key(path):
    """Sorts paths in path order: segment by segment, each by its bytes."""
    return [segment.encode() for segment in path.split("/")]


def in_root(rules, real):
    return real == rules.working_root or rules.working_root in real.parents


def resolve_directory(rules, cwd):
    """The path of the unit `cwd` is in, the warnings finding it gave, and the marker it was found by,
    or None: in the working root, the deepest folder along it reached through units alone; outside
    it, the unit its nearest marker binds."""
    real = Path(cwd).resolve()
    if not in_root(rules, real):
        return resolve_marker(rules, real, cwd)
    folder, segments = rules.working_root, []
    for segment in real.relative_to(rules.working_root).parts:
        folder = folder / segment
        if not (folder / MANIFEST).is_file():
            break
        segments.append(segment)
    if not segments:
        raise no_unit(cwd, "no-unit", f"{cwd} is in no unit")
    return "/".join(segments), [], None


def no_unit(cwd, reason, message, marker=None, warnings=()):
    return OperationError(
        "not-found", message,
        {"unit": None, "missing": None, "cwd": cwd, "reason": reason, "marker": marker},
        warnings=warnings,
    )


def nearest_marker(real):
    """The nearest folder at or above `real` holding .shingi/unit.json, or None."""
    for folder in (real, *real.parents):
        try:
            os.lstat(folder / MARKER_DIR / MARKER)
        except (FileNotFoundError, NotADirectoryError):
            continue
        except OSError as exc:
            raise OperationError("io", f"{folder}: {exc.strerror}", {
                "path": str(folder / MARKER_DIR / MARKER), "code": errno.errorcode.get(exc.errno),
            })
        return folder
    return None


def resolve_marker(rules, real, cwd):
    """The unit the nearest marker above `real` binds, its warnings, and the marker's path; a marker
    that can't be used is never passed for one further up (see operations.md, Resolving a directory)."""
    outside = f"{cwd} is outside the working root"
    folder = nearest_marker(real)
    if folder is None:
        raise no_unit(cwd, "outside-root", outside + ", with no marker above it")
    path = folder / MARKER_DIR / MARKER
    try:
        marker = read_marker(folder)
    except Unusable as exc:
        raise no_unit(cwd, "outside-root", outside + f"; its marker {path} is {exc.reason}", warnings=[warning(
            "unsupported-marker", f"{path} is {exc.reason}; bind the folder again",
            None, details={"path": str(path), "reason": exc.reason},
        )])
    if marker["dir"] != str(folder):
        raise no_unit(cwd, "outside-root", outside + f"; its marker {path} is foreign", warnings=[warning(
            "foreign-marker", f"{path} names {marker['dir']}, not its own folder; bind the folder again",
            None, details={"path": str(path), "dir": marker["dir"]},
        )])
    if unit_depth(rules, marker["path"]) == len(marker["path"].split("/")) and manifest_id(rules, marker["path"]) == marker["id"]:
        return marker["path"], [], str(path)
    for found in walk(rules):
        if manifest_id(rules, found) == marker["id"]:
            return found, [warning(
                "stale-marker", f"{path} names {marker['path']}, but its unit is at {found}; bind the folder again",
                found, details={"path": str(path), "stale": marker["path"]},
            )], str(path)
    raise no_unit(cwd, "unit-deleted", f"the unit {path} binds, {marker['path']}, was deleted", marker=str(path))


def manifest_id(rules, path):
    try:
        return read_manifest(working_folder(rules, path))["id"]
    except Unusable:
        return None


def koan_folder(rules, path):
    return f"{rules.koan_root}/{path}"


def working_folder(rules, path):
    return rules.working_root / path


def read_record(file, fields):
    """The JSON object in `file`, with exactly `fields`, a supported `schema`, and a canonical
    `id`; or raise Unusable."""
    try:
        data = file.read_bytes()
    except OSError:
        raise Unusable("unreadable")
    try:
        record = json.loads(data.decode("utf-8"), object_pairs_hook=no_duplicate_keys)
    except ValueError:  # invalid UTF-8 or JSON, or a duplicate key
        raise Unusable("corrupt")
    if not isinstance(record, dict) or record.keys() != fields:
        raise Unusable("corrupt")
    if type(record["schema"]) is not int:
        raise Unusable("corrupt")
    if record["schema"] not in SCHEMAS:
        raise Unusable("unsupported-format")
    if not isinstance(record["id"], str) or not UUID.fullmatch(record["id"]):
        raise Unusable("corrupt")
    return record


def read_manifest(folder):
    """The manifest in `folder`, or raise Unusable (see operations.md, Reading a unit)."""
    manifest = read_record(folder / MANIFEST, {"schema", "id", "kind"})
    if not isinstance(manifest["kind"], str):
        raise Unusable("corrupt")
    return manifest


def read_marker(folder):
    """The marker in `folder`'s .shingi, or raise Unusable (see operations.md, Reading a marker)."""
    marker = read_record(folder / MARKER_DIR / MARKER, {"schema", "id", "path", "dir"})
    path = marker["path"]
    if not isinstance(path, str) or any(segment_problem(s) for s in path.split("/")):
        raise Unusable("corrupt")
    if not isinstance(marker["dir"], str):
        raise Unusable("corrupt")
    return marker


def no_duplicate_keys(pairs):
    keys = [key for key, _ in pairs]
    if len(set(keys)) != len(keys):
        raise ValueError("duplicate key")
    return dict(pairs)


def check_manifest(rules, path):
    """The unit's manifest and its warnings: None and unsupported-manifest when it is unusable,
    undefined-kind when its kind is no longer in the rules."""
    folder = working_folder(rules, path)
    try:
        manifest = read_manifest(folder)
    except Unusable as exc:
        return None, [warning(
            "unsupported-manifest",
            f"{path}: {MANIFEST} is {exc.reason}",
            path,
            details={"path": str(folder / MANIFEST), "reason": exc.reason},
        )]
    if manifest["kind"] not in rules.kinds:
        return manifest, [warning(
            "undefined-kind",
            f"{path}: kind {manifest['kind']!r} is not defined in the rules",
            path,
            details={"kind": manifest["kind"]},
        )]
    return manifest, []


def kind_of(folder):
    """A child's kind, or None when its manifest is unusable."""
    try:
        return read_manifest(folder)["kind"]
    except Unusable:
        return None


def read_notes(folder):
    """The folder's uow.md, whole; "" when it is missing or unreadable."""
    try:
        return (folder / NOTES).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def read_title(folder):
    for line in read_notes(folder).splitlines():
        if line.strip():
            return line[2:].strip() if line.startswith("# ") else ""
    return ""


def child_folders(folder):
    """The unit folders directly in `folder`, in path order: none in a working root not yet made."""
    if not folder.exists():
        return []
    return [
        entry for entry in sorted(folder.iterdir(), key=lambda e: e.name.encode())
        if not entry.name.startswith(".") and (entry / MANIFEST).is_file()
    ]


def children(rules, path):
    return [
        {"path": f"{path}/{entry.name}", "kind": kind_of(entry)}
        for entry in child_folders(working_folder(rules, path))
    ]


def walk(rules, path=None):
    """`path` and every unit beneath it, or every unit, in path order."""
    found = [] if path is None else [path]
    folder = rules.working_root if path is None else working_folder(rules, path)
    for entry in child_folders(folder):
        found += walk(rules, entry.name if path is None else f"{path}/{entry.name}")
    return found


def task_ref(task):
    if task is None:
        return None
    return {k: task[k] for k in ("id", "readiness", "created_at", "completed_at")}


def match(tasks, folder, unit_id, source):
    found = [
        t for t in tasks
        if t["folder"] == folder and t["extra"].get("shingi-unit") == unit_id and t["extra"].get("source") == source
    ]
    return min(found, key=lambda t: t["id"]) if found else None


def state(start, done):
    if start is None or done is None:
        return None
    if done["readiness"] == "done":
        return "done"
    if start["readiness"] == "done":
        return "started"
    return "not-started"


def find_tasks(rules, path, unit_id):
    """The unit's start and done tasks, as koan reports them, each None when not found, and koan's
    warnings. Raises koan-failed."""
    kfolder = koan_folder(rules, path)
    tasks, warnings = koan.list_tasks(kfolder, recursive=False)
    return match(tasks, kfolder, unit_id, "shingi-start"), match(tasks, kfolder, unit_id, "shingi-done"), warnings


def koan_failed(error, unit):
    """The koan-failed warning for a read that koan failed: every task it would have found is null."""
    return [warning("koan-failed", error.message, unit, details=error.details)] + error.warnings


def sort_warnings(warnings):
    """In the spec's order: by kind, unit in path order (null first), ids, role, then `after`."""
    roles = {"start": 0, "done": 1}
    return sorted(warnings, key=lambda w: (
        w["kind"],
        w["unit"] is not None,
        path_key(w["unit"] or ""),
        w["ids"],
        roles.get(w["details"].get("role"), -1),
        path_key(w["details"].get("after") or "") if w["kind"] == "after-unlinked" else [],
    ))


def parent_of(path):
    return path.rpartition("/")[0] or None


def read_unit(rules, path):
    """The unit object, as where reports it, and its warnings."""
    manifest, warnings = check_manifest(rules, path)
    start = done = None
    if manifest is not None:
        try:
            start, done, koan_warnings = find_tasks(rules, path, manifest["id"])
        except OperationError as error:
            if error.kind != "koan-failed":
                raise
            warnings += koan_failed(error, path)
        else:
            warnings += missing_tasks(path, start, done) + koan_warnings
    return build_unit(rules, path, manifest, start, done), sort_warnings(warnings)


def unit_from(rules, path, manifest, tasks):
    """The unit object and its missing-task warnings, its tasks matched from `tasks`, a recursive
    koan list of a folder that holds it, or None when koan failed."""
    start = done = None
    warnings = []
    if manifest is not None and tasks is not None:
        kfolder = koan_folder(rules, path)
        start = match(tasks, kfolder, manifest["id"], "shingi-start")
        done = match(tasks, kfolder, manifest["id"], "shingi-done")
        warnings = missing_tasks(path, start, done)
    return build_unit(rules, path, manifest, start, done), warnings


def missing_tasks(path, start, done):
    """A missing-task warning for each of the unit's start and done tasks that wasn't found."""
    return [
        warning("missing-task", f"{path}: no {role} task in its koan folder carries its id", path,
                details={"role": role})
        for role, task in (("start", start), ("done", done))
        if task is None
    ]


def build_unit(rules, path, manifest, start, done):
    """The unit object, from its manifest, or None when it is unusable, and its start and done
    tasks as koan reports them."""
    folder = working_folder(rules, path)
    start, done = task_ref(start), task_ref(done)
    return {
        "path": path,
        "id": manifest and manifest["id"],
        "kind": manifest and manifest["kind"],
        "title": read_title(folder),
        "state": state(start, done),
        "parent": parent_of(path),
        "children": children(rules, path),
        "koan_folder": koan_folder(rules, path),
        "working_folder": str(folder),
        "notes_path": str(folder / NOTES),
        "start": start,
        "done": done,
    }
