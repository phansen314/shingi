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
