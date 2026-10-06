"""Units on disk and their tasks in koan (see operations.md, Shared rules)."""

import json
import re

from shingi import koan
from shingi.envelope import OperationError

NAME = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,62}[A-Za-z0-9])?"
UNIT_PATH = re.compile(rf"{NAME}(?:/{NAME})*")
MANIFEST = "uow.json"
NOTES = "uow.md"


def check_path(path):
    if not UNIT_PATH.fullmatch(path):
        raise OperationError("invalid-name", f"invalid unit path {path!r}", {"path": path})


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


def children(rules, path):
    folder = working_folder(rules, path)
    found = []
    for entry in sorted(folder.iterdir(), key=lambda e: e.name.encode()):
        if not entry.name.startswith(".") and (entry / MANIFEST).is_file():
            found.append({"path": f"{path}/{entry.name}", "kind": read_manifest(entry)["kind"]})
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


def read_unit(rules, path):
    """The unit object, as where reports it."""
    folder = working_folder(rules, path)
    manifest = read_manifest(folder)
    kfolder = koan_folder(rules, path)
    tasks = koan.list_tasks(kfolder, recursive=False)
    start = task_ref(match(tasks, kfolder, manifest["id"], "shingi-start"))
    done = task_ref(match(tasks, kfolder, manifest["id"], "shingi-done"))
    parent = path.rpartition("/")[0] or None
    return {
        "path": path,
        "id": manifest["id"],
        "kind": manifest["kind"],
        "title": read_title(folder),
        "state": state(start, done),
        "parent": parent,
        "children": children(rules, path),
        "koan_folder": kfolder,
        "working_folder": str(folder),
        "notes_path": str(folder / NOTES),
        "start": start,
        "done": done,
    }
