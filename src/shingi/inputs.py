"""Checking an operation's input against its input schema and additional validation (see
operations.md: each operation's Input schema and Additional validation).

Every problem is reported, not just the first, as one invalid-input.
"""

import os

from shingi.envelope import OperationError

# Each operation's fields: name -> required.
FIELDS = {
    "version": {},
    "kinds": {},
    "where": {"unit": False, "cwd": False},
    "context": {"unit": False, "cwd": False},
    "list": {"unit": False},
    "create": {"path": True, "kind": True, "title": False, "notes": False, "after": False},
    "adopt": {"path": True, "kind": True, "title": False},
    "delete": {"unit": True},
}


def invalid(problems):
    problems = sorted(problems, key=lambda p: (p["field"], p["reason"]))
    message = "; ".join(f"{p['field'] or 'input'}: {p['reason']}" for p in problems)
    return OperationError("invalid-input", f"invalid input: {message}", {"problems": problems})


def utf8(text):
    """Whether `text` is valid UTF-8: the CLI decodes bytes that aren't to lone surrogates."""
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def string_problems(operation, field, value):
    if not isinstance(value, str):
        return [{"field": field, "reason": "must be a string"}]
    if not utf8(value):
        return [{"field": field, "reason": "not valid UTF-8"}]
    if operation in ("create", "adopt") and "\0" in value:
        return [{"field": field, "reason": "holds a NUL"}]
    return []


def after_problems(after):
    """The problems in create's `after`: it is an array of strings, no two the same."""
    if not isinstance(after, list):
        return [{"field": "/after", "reason": "must be an array"}]
    problems = []
    for index, entry in enumerate(after):
        found = string_problems("create", f"/after/{index}", entry)
        if not found and entry in after[:index]:
            found = [{"field": f"/after/{index}", "reason": "names a path already given"}]
        problems += found
    return problems


def check(operation, inp):
    """Raise invalid-input with every problem in `inp`, `operation`'s input."""
    fields = FIELDS[operation]
    problems = []
    for name, value in sorted(inp.items()):
        field = f"/{name}"
        if name not in fields:
            problems.append({"field": field, "reason": "unknown field"})
        elif name == "after":
            problems += after_problems(value)
        else:
            problems += string_problems(operation, field, value)
    for name, required in fields.items():
        if required and name not in inp:
            problems.append({"field": f"/{name}", "reason": "required"})

    title = inp.get("title")
    if isinstance(title, str):
        if title == "":
            problems.append({"field": "/title", "reason": "must not be empty"})
        if "\n" in title or "\r" in title:
            problems.append({"field": "/title", "reason": "holds a line break"})
    if operation in ("where", "context"):
        if ("unit" in inp) == ("cwd" in inp):
            problems.append({"field": "", "reason": "exactly one of unit and cwd is required"})
        cwd = inp.get("cwd")
        if isinstance(cwd, str) and not os.path.isabs(cwd):
            problems.append({"field": "/cwd", "reason": "must be absolute"})
    if problems:
        raise invalid(problems)
