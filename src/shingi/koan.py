"""Running koan through its CLI (see operations.md, Running koan)."""

import json
import subprocess

from shingi.envelope import OperationError


def failed(call, exit_code, error, message):
    return OperationError("koan-failed", message, {"call": call, "exit": exit_code, "error": error})


def run(call, payload):
    """Run `koan <call> -i -`; return its envelope."""
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
    if proc.returncode not in (0, 1, 2) or not isinstance(envelope, dict):
        raise failed(call, proc.returncode, None, f"koan {call} exited {proc.returncode} without an envelope")
    return envelope


def list_tasks(folder, recursive):
    """Every task tagged `shingi` in `folder`; none when the folder doesn't exist yet."""
    envelope = run(
        "list",
        {"folder": folder, "recursive": recursive, "readiness": ["ready", "blocked", "done"], "tags_all": ["shingi"]},
    )
    if envelope["ok"]:
        return envelope["result"]["tasks"]
    error = envelope["error"]
    if error["kind"] == "not-found" and any(
        folder == f or folder.startswith(f + "/") for f in error["details"].get("folders", [])
    ):
        return []
    raise failed("list", 1, error, f"koan list failed: {error['message']}")


def write(call, payload):
    envelope = run(call, payload)
    if not envelope["ok"]:
        error = envelope["error"]
        raise failed(call, 1, error, f"koan {call} failed: {error['message']}")
    return envelope["result"]


def create_batch(payload):
    return write("create-batch", payload)


def block(task_id, blockers):
    return write("block", {"id": task_id, "blockers": blockers})
