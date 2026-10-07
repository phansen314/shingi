"""The rules file, shingi.toml (see design-spec.md, The rules file)."""

import errno
import os
import re
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

from shingi.envelope import OperationError
from shingi.units import NAME


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


KOAN_FOLDER = re.compile(rf"(?:/{NAME})+")
KIND_NAME = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?")
FIELDS = {"schema", "roots", "kind"}
ROOTS = {"koan", "working"}
KIND = {"description", "suggests"}


def invalid(path, reason, message, problems=(), code=None):
    details = {"path": str(path), "reason": reason, "problems": sorted(problems, key=lambda p: p["field"])}
    if code is not None:
        details["code"] = code
    return OperationError("invalid-rules", message, details)


def load(config=None):
    """Read and check the rules file (operations.md, Reading the rules)."""
    path = Path(config).absolute() if config is not None else default_path()
    try:
        with open(path, "rb") as f:
            data = tomllib.loads(f.read().decode("utf-8"))
    except FileNotFoundError:
        raise invalid(path, "missing", f"no rules file at {path}; see \"The rules file\" in shingi's README for an example")
    except OSError as exc:
        raise invalid(path, "unreadable", f"{path}: {exc.strerror}", code=errno.errorcode.get(exc.errno))
    except UnicodeDecodeError:
        raise invalid(path, "syntax", f"{path}: not valid UTF-8")
    except tomllib.TOMLDecodeError as exc:
        raise invalid(path, "syntax", f"{path}: {exc}")

    schema = data.get("schema")
    if not is_int(schema):
        raise invalid(path, "invalid", f"{path}: invalid rules", [problem("schema", "required: an integer")])
    if schema != 1:
        raise OperationError(
            "unsupported-format",
            f"{path}: unsupported schema {schema}",
            {"path": str(path), "schema": schema, "supported": [1]},
        )

    problems = unknown(data, FIELDS, "")
    roots = data.get("roots")
    koan_root = working = None
    if not isinstance(roots, dict):
        problems.append(problem("roots", "required: a table"))
    else:
        problems += unknown(roots, ROOTS, "roots.")
        koan_root = roots.get("koan")
        if not isinstance(koan_root, str) or not KOAN_FOLDER.fullmatch(koan_root):
            problems.append(problem("roots.koan", "required: a koan folder path other than /, such as /work"))
        working = roots.get("working")
        if not isinstance(working, str):
            problems.append(problem("roots.working", "required: a string"))
        else:
            working = Path(os.path.expanduser(working)) if working.startswith("~/") else Path(working)
            if not working.is_absolute() or not working.is_dir():
                problems.append(problem("roots.working", "must be an existing absolute directory"))

    kinds = data.get("kind")
    if not isinstance(kinds, dict) or not kinds:
        problems.append(problem("kind", "at least one kind is required"))
        kinds = {}
    for name, kind in kinds.items():
        field = f"kind.{name}"
        if not KIND_NAME.fullmatch(name):
            problems.append(problem(field, "a kind name is lowercase letters, digits, and -, as a koan tag"))
        if not isinstance(kind, dict):
            problems.append(problem(field, "must be a table"))
            continue
        problems += unknown(kind, KIND, field + ".")
        if not isinstance(kind.get("description", ""), str):
            problems.append(problem(field + ".description", "must be a string"))
        suggests = kind.get("suggests", [])
        if not isinstance(suggests, list) or not all(isinstance(s, str) for s in suggests):
            problems.append(problem(field + ".suggests", "must be an array of strings"))
        else:
            for s in suggests:
                if s not in kinds:
                    problems.append(problem(field + ".suggests", f"{s!r} is not a defined kind"))
    if problems:
        raise invalid(path, "invalid", f"{path}: invalid rules: " + "; ".join(
            f"{p['field']}: {p['reason']}" for p in sorted(problems, key=lambda p: p["field"])
        ), problems)
    return Rules(koan_root=koan_root, working_root=working.resolve(), kinds=kinds)


def is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def problem(field, reason):
    return {"field": field, "reason": reason}


def unknown(table, known, prefix):
    return [problem(prefix + key, "unknown field") for key in table if key not in known]
