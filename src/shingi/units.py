"""Units on disk and their tasks in koan (see operations.md, Shared rules)."""

import json
import os
import re
from pathlib import Path

from shingi import koan
from shingi.envelope import OperationError

NAME = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,62}[A-Za-z0-9])?"
UNIT_PATH = re.compile(rf"{NAME}(?:/{NAME})*")
MANIFEST = "uow.json"
NOTES = "uow.md"


def check_path(path):
    if not UNIT_PATH.fullmatch(path):
        raise OperationError("invalid-name", f"invalid unit path {path!r}", {"path": path})


def resolve(rules, path):
    """Raise not-found unless every folder on `path` exists, by its exact name, and holds a manifest."""
    folder = rules.working_root
    segments = path.split("/")
    for i, segment in enumerate(segments):
        folder = folder / segment
        exact = segment in os.listdir(folder.parent)
        if not (exact and folder.is_dir() and (folder / MANIFEST).is_file()):
            missing = "/".join(segments[: i + 1])
            raise OperationError(
                "not-found",
                f"{path} is not a unit: {missing} is not",
                {"unit": path, "missing": missing, "cwd": None, "reason": "not-a-unit"},
            )


def path_key(path):
    """Sorts paths in path order: segment by segment, each by its bytes."""
    return [segment.encode() for segment in path.split("/")]


def resolve_directory(rules, cwd):
    """The path of the unit `cwd` is in: the deepest folder along it reached through units alone."""
    real = Path(cwd).resolve()
    if real != rules.working_root and rules.working_root not in real.parents:
        raise no_unit(cwd, "outside-root", f"{cwd} is outside the working root")
    folder, segments = rules.working_root, []
    for segment in real.relative_to(rules.working_root).parts:
        folder = folder / segment
        if not (folder / MANIFEST).is_file():
            break
        segments.append(segment)
    if not segments:
        raise no_unit(cwd, "no-unit", f"{cwd} is in no unit")
    return "/".join(segments)


def no_unit(cwd, reason, message):
    return OperationError("not-found", message, {"unit": None, "missing": None, "cwd": cwd, "reason": reason})


def koan_folder(rules, path):
    return f"{rules.koan_root}/{path}"


def working_folder(rules, path):
    return rules.working_root / path


def read_manifest(folder):
    with open(folder / MANIFEST, encoding="utf-8") as f:
        return json.load(f)


def read_title(folder):
    try:
        text = (folder / NOTES).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    for line in text.splitlines():
        if line.strip():
            return line[2:].strip() if line.startswith("# ") else ""
    return ""


def child_folders(folder):
    """The unit folders directly in `folder`, in path order."""
    return [
        entry for entry in sorted(folder.iterdir(), key=lambda e: e.name.encode())
        if not entry.name.startswith(".") and (entry / MANIFEST).is_file()
    ]


def children(rules, path):
    return [
        {"path": f"{path}/{entry.name}", "kind": read_manifest(entry)["kind"]}
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
    """The unit's start and done tasks, as koan reports them, each None when not found."""
    kfolder = koan_folder(rules, path)
    tasks = koan.list_tasks(kfolder, recursive=False)
    return match(tasks, kfolder, unit_id, "shingi-start"), match(tasks, kfolder, unit_id, "shingi-done")


def parent_of(path):
    return path.rpartition("/")[0] or None


def read_unit(rules, path):
    """The unit object, as where reports it."""
    manifest = read_manifest(working_folder(rules, path))
    return build_unit(rules, path, manifest, *find_tasks(rules, path, manifest["id"]))


def build_unit(rules, path, manifest, start, done):
    """The unit object, from its manifest and its start and done tasks as koan reports them."""
    folder = working_folder(rules, path)
    start, done = task_ref(start), task_ref(done)
    return {
        "path": path,
        "id": manifest["id"],
        "kind": manifest["kind"],
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
