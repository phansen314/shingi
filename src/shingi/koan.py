"""Running koan through its CLI (see operations.md, Running koan).

Every call returns koan's warnings as koan-warning warnings beside its result, and a koan
failure carries them too.
"""

import json
import subprocess

from shingi.envelope import OperationError


def failed(call, exit_code, error, message, warnings=()):
    return OperationError(
        "koan-failed", message, {"call": call, "exit": exit_code, "error": error}, warnings=warnings
    )


def koan_warnings(call, envelope):
    return [
        {
            "kind": "koan-warning",
            "message": f"koan {call} warned: {w.get('message', '')}",
            "unit": None,
            "ids": sorted(w.get("ids", [])),
            "details": {"call": call, "warning": w},
        }
        for w in envelope.get("warnings", [])
    ]


def run(call, payload):
    """Run `koan <call> -i -`; return its envelope and its warnings."""
    try:
        proc = subprocess.run(
            ["koan", call, "-i", "-"],
            input=json.dumps(payload).encode("utf-8"),
            capture_output=True,
        )
    except OSError as exc:
        raise failed(call, None, None, f"koan could not be run: {exc}")
    try:
        envelope = json.loads(proc.stdout)
    except ValueError:
        envelope = None
    if proc.returncode not in (0, 1, 2) or not isinstance(envelope, dict) or "ok" not in envelope:
        raise failed(call, proc.returncode, None, f"koan {call} exited {proc.returncode} without an envelope")
    return envelope, koan_warnings(call, envelope)


def list_tasks(folder, recursive, tags=("shingi",)):
    """Every task in `folder` with all of `tags`, none when the folder doesn't exist yet, and koan's
    warnings."""
    payload = {"folder": folder, "recursive": recursive, "readiness": ["ready", "blocked", "done"]}
    if tags:
        payload["tags_all"] = list(tags)
    envelope, warnings = run("list", payload)
    if envelope["ok"]:
        return envelope["result"]["tasks"], warnings
    error = envelope["error"]
    if error["kind"] == "not-found" and any(
        folder == f or folder.startswith(f + "/") for f in error["details"].get("folders", [])
    ):
        return [], warnings
    raise failed("list", 1, error, f"koan list failed: {error['message']}", warnings)


def write(call, payload):
    """Run a koan write; return its result and koan's warnings."""
    envelope, warnings = run(call, payload)
    if not envelope["ok"]:
        error = envelope["error"]
        raise failed(call, 1, error, f"koan {call} failed: {error['message']}", warnings)
    return envelope["result"], warnings


def create_batch(payload):
    return write("create-batch", payload)


def block(task_id, blockers):
    return write("block", {"id": task_id, "blockers": blockers})
