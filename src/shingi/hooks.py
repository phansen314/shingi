"""The hooks file, hooks.json, and running an event's hooks (see hooks-spec.md)."""

import errno
import math
import os
import signal
import subprocess
import tempfile
from dataclasses import dataclass
from importlib.metadata import version as package_version
from pathlib import Path

from shingi import envelope, rules, units
from shingi.envelope import OperationError

EVENTS = ("create", "adopt", "delete")
HOOK = {"command", "timeout", "description", "disabled"}
DEFAULT_TIMEOUT = 10
STDERR_TAIL = 2048
INTERRUPTS = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)

running = None  # the running hook's process ID, which is also its process group's


@dataclass
class Hook:
    command: str
    timeout: float = float(DEFAULT_TIMEOUT)
    timeout_given: float = DEFAULT_TIMEOUT
    description: str | None = None
    disabled: bool = False


def default_path():
    return rules.default_path().with_name("hooks.json")


def invalid(path, reason, message, problems=(), code=None):
    details = {"path": str(path), "reason": reason, "problems": sorted(problems, key=lambda p: p["field"])}
    if code is not None:
        details["code"] = code
    return OperationError("invalid-hooks", message, details)


def load():
    """The hooks by event, every event present, disabled hooks included; or with no hooks file,
    every event empty (hooks-spec.md, When it is read)."""
    path = default_path()
    try:
        with open(path, "rb") as f:
            data = f.read()
    except FileNotFoundError:
        return {event: [] for event in EVENTS}
    except OSError as exc:
        raise invalid(path, "unreadable", f"{path}: {exc.strerror}", code=errno.errorcode.get(exc.errno))
    try:
        value = envelope.decode(data)
    except ValueError as exc:
        raise invalid(path, "syntax", f"{path}: {exc}")
    if not isinstance(value, dict):
        raise invalid(path, "syntax", f"{path}: not a JSON object")

    schema = value.get("schema")
    if not rules.is_int(schema):
        raise invalid(path, "invalid", f"{path}: invalid hooks", [rules.problem("/schema", "required: an integer")])
    if schema != 1:
        raise OperationError(
            "unsupported-format",
            f"{path}: unsupported schema {schema}",
            {"path": str(path), "schema": schema, "supported": [1]},
        )

    problems, hooks = [], {event: [] for event in EVENTS}
    for key in value:
        if key not in ("schema", "hooks"):
            problems.append(rules.problem(pointer(key), "unknown field"))
    events = value.get("hooks", {})
    if not isinstance(events, dict):
        problems.append(rules.problem("/hooks", "must be an object"))
        events = {}
    for event, listed in events.items():
        field = pointer("hooks", event)
        if event not in EVENTS:
            problems.append(rules.problem(field, "unknown event"))
        elif not isinstance(listed, list):
            problems.append(rules.problem(field, "must be an array"))
        else:
            for n, hook in enumerate(listed):
                hooks[event].append(check_hook(hook, f"{field}/{n}", problems))
    if problems:
        raise invalid(path, "invalid", f"{path}: invalid hooks: " + "; ".join(
            f"{p['field']}: {p['reason']}" for p in sorted(problems, key=lambda p: p["field"])
        ), problems)
    return hooks


def check_hook(hook, field, problems):
    """The Hook `hook` describes, adding each problem found to `problems`; with any, it isn't used."""
    if not isinstance(hook, dict):
        problems.append(rules.problem(field, "must be an object"))
        return None
    for key in hook:
        if key not in HOOK:
            problems.append(rules.problem(f"{field}/{pointer(key)[1:]}", "unknown field"))
    command = hook.get("command")
    if not isinstance(command, str) or command == "" or "\0" in command:
        problems.append(rules.problem(field + "/command", "required: a non-empty string with no NUL"))
    given = hook.get("timeout", DEFAULT_TIMEOUT)
    timeout = timeout_seconds(given)
    if timeout is None:
        problems.append(rules.problem(field + "/timeout", "must be a finite number above 0"))
    description = hook.get("description")
    if "description" in hook and not isinstance(description, str):
        problems.append(rules.problem(field + "/description", "must be a string"))
    disabled = hook.get("disabled", False)
    if not isinstance(disabled, bool):
        problems.append(rules.problem(field + "/disabled", "must be a boolean"))
    return Hook(command, timeout, given, description, disabled)


def timeout_seconds(value):
    """`value` as the seconds to wait, or None unless it is a finite number above 0."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        seconds = float(value)  # an integer too large for a float raises OverflowError
    except OverflowError:
        return None
    return seconds if math.isfinite(seconds) and seconds > 0 else None


def pointer(*keys):
    """A JSON Pointer to `keys`."""
    return "".join("/" + str(key).replace("~", "~0").replace("/", "~1") for key in keys)


def run(hooks, event, inp, result, warnings, unit):
    """Run `event`'s enabled hooks, in order, each given the payload; the warnings of those that
    fail, in the order they ran (hooks-spec.md, Running a hook)."""
    enabled = [(index, hook) for index, hook in enumerate(hooks[event]) if not hook.disabled]
    if not enabled:
        return []
    payload = envelope.encode({
        "schema": 1,
        "tool": "shingi",
        "version": package_version("shingi"),
        "event": event,
        "input": inp,
        "result": result,
        "warnings": warnings,
    })
    found = []
    with tempfile.TemporaryDirectory(prefix="shingi-hooks-") as directory:
        temp = Path(directory)
        (temp / "payload.json").write_text(payload, encoding="utf-8")
        before = {signum: signal.signal(signum, interrupted) for signum in INTERRUPTS}
        try:
            for index, hook in enabled:
                problem = run_hook(hook, temp, index)
                if problem is not None:
                    found.append(hook_warning(problem, event, index, hook, unit))
        finally:
            for signum, handler in before.items():
                signal.signal(signum, handler)
    return found


def interrupted(signum, frame):
    """Kill the running hook's process group, then die of `signum` with no envelope (hooks-spec.md,
    Running a hook). The temp directory is left behind."""
    if running is not None:
        try:
            os.killpg(running, signal.SIGKILL)
        except ProcessLookupError:
            pass
    signal.signal(signum, signal.SIG_DFL)
    os.kill(os.getpid(), signum)


def run_hook(hook, temp, index):
    """Run one hook; None when it exited 0, otherwise `(kind, exit, stderr, reason)`: the warning's
    kind, `exit` None when it couldn't be started or ran out of time."""
    global running
    stderr_path = temp / f"stderr-{index}"
    with open(temp / "payload.json", "rb") as stdin, open(stderr_path, "wb") as stderr:
        try:
            proc = subprocess.Popen(
                ["/bin/sh", "-c", hook.command],
                stdin=stdin, stdout=subprocess.DEVNULL, stderr=stderr, start_new_session=True,
            )
        except OSError as exc:
            return "hook-failed", None, "", exc.strerror
    running = proc.pid
    try:
        status = proc.wait(timeout=hook.timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.wait()
        return "hook-timeout", None, stderr_tail(stderr_path), None
    finally:
        running = None
    if status == 0:
        return None
    return "hook-failed", (status if status > 0 else 128 - status), stderr_tail(stderr_path), None


def stderr_tail(path):
    with open(path, "rb") as f:
        f.seek(0, os.SEEK_END)
        f.seek(max(0, f.tell() - STDERR_TAIL))
        return f.read().decode("utf-8", errors="replace")


def hook_warning(problem, event, index, hook, unit):
    kind, status, stderr, reason = problem
    details = {"event": event, "index": index, "command": hook.command, "description": hook.description}
    if kind == "hook-timeout":
        details.update(timeout=hook.timeout_given, stderr=stderr)
        message = f"{event} hook {index} was still running after {hook.timeout_given} seconds, and was killed"
    else:
        details.update(exit=status, stderr=stderr)
        if reason is not None:
            message = f"{event} hook {index} couldn't be started: {reason}"
        else:
            message = f"{event} hook {index} exited {status}"
    return units.warning(kind, message, unit, details=details)
