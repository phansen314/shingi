"""The rules file, shingi.toml (see design-spec.md, The rules file)."""

import os
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

from shingi.envelope import OperationError


@dataclass
class Rules:
    koan_root: str
    working_root: Path
    kinds: dict


def default_path():
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        xdg = os.environ.get("XDG_CONFIG_HOME", "")
        base = Path(xdg) if os.path.isabs(xdg) else Path.home() / ".config"
    return base / "shingi" / "shingi.toml"


def invalid(path, reason, message, problems=()):
    return OperationError(
        "invalid-rules",
        message,
        {"path": str(path), "reason": reason, "problems": list(problems)},
    )


def load(config=None):
    path = Path(config).absolute() if config is not None else default_path()
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except FileNotFoundError:
        raise invalid(path, "missing", f"no rules file at {path}; see the design spec's example")
    except tomllib.TOMLDecodeError as exc:
        raise invalid(path, "syntax", f"{path}: {exc}")

    if data.get("schema") != 1:
        raise OperationError(
            "unsupported-format",
            f"{path}: unsupported schema {data.get('schema')!r}",
            {"path": str(path), "schema": data.get("schema"), "supported": [1]},
        )
    roots = data.get("roots", {})
    koan_root = roots.get("koan")
    working = roots.get("working")
    kinds = data.get("kind", {})
    problems = []
    if not isinstance(koan_root, str) or not koan_root.startswith("/") or koan_root == "/":
        problems.append({"field": "roots.koan", "reason": "must be a koan folder path other than /"})
    if not isinstance(working, str):
        problems.append({"field": "roots.working", "reason": "required"})
    else:
        working = Path(os.path.expanduser(working)) if working.startswith("~/") else Path(working)
        if not working.is_absolute() or not working.is_dir():
            problems.append({"field": "roots.working", "reason": "must be an existing absolute directory"})
    if not kinds:
        problems.append({"field": "kind", "reason": "at least one kind is required"})
    if problems:
        raise invalid(path, "invalid", f"{path}: invalid rules", problems)
    return Rules(koan_root=koan_root, working_root=working.resolve(), kinds=kinds)
