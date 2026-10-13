"""The output envelope, as koan's (see operations.md, Output envelope)."""

import json


class OperationError(Exception):
    """An error an operation reports in the envelope, with the warnings gathered before it, and
    for create and adopt, what it made before failing."""

    def __init__(self, kind, message, details=None, warnings=(), partial=None):
        super().__init__(message)
        self.kind = kind
        self.message = message
        self.details = details if details is not None else {}
        self.warnings = list(warnings)
        self.partial = partial


def success(result, warnings=()):
    return {"ok": True, "result": result, "warnings": list(warnings)}


def failure(error):
    body = {"kind": error.kind, "message": error.message, "details": error.details}
    if error.partial is not None:
        body["partial"] = error.partial
    return {"ok": False, "error": body, "warnings": error.warnings}


def encode(envelope):
    """One compact line of UTF-8 JSON with koan's escaping: only `"`, `\\`,
    U+0000-U+001F, U+2028, and U+2029 are escaped."""
    text = json.dumps(envelope, ensure_ascii=False, separators=(",", ":"))
    return text.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029") + "\n"


def decode(data):
    """The one JSON value in `data`, bytes, strictly: UTF-8, no key repeated in any object, and no
    `NaN`, `Infinity`, or `-Infinity`. Raises ValueError with a reason for people."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError("not valid UTF-8")
    try:
        return json.loads(text, object_pairs_hook=no_duplicate_keys, parse_constant=not_json)
    except ValueError as exc:
        raise ValueError(f"not one JSON value: {exc}")
    except RecursionError:
        raise ValueError("not one JSON value: nested too deeply")


def no_duplicate_keys(pairs):
    keys = [key for key, _ in pairs]
    duplicates = sorted({key for key in keys if keys.count(key) > 1})
    if duplicates:
        raise ValueError(f"duplicate key {duplicates[0]!r}")
    return dict(pairs)


def not_json(constant):
    raise ValueError(f"{constant} is not JSON")
