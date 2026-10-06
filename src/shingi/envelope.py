"""The output envelope, as koan's (see operations.md, Output envelope)."""

import json


class OperationError(Exception):
    """An error an operation reports in the envelope."""

    def __init__(self, kind, message, details=None):
        super().__init__(message)
        self.kind = kind
        self.message = message
        self.details = details if details is not None else {}


def success(result, warnings=()):
    return {"ok": True, "result": result, "warnings": list(warnings)}


def failure(error, warnings=()):
    return {
        "ok": False,
        "error": {"kind": error.kind, "message": error.message, "details": error.details},
        "warnings": list(warnings),
    }


def encode(envelope):
    """One compact line of UTF-8 JSON with koan's escaping: only `"`, `\\`,
    U+0000-U+001F, U+2028, and U+2029 are escaped."""
    text = json.dumps(envelope, ensure_ascii=False, separators=(",", ":"))
    return text.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029") + "\n"
