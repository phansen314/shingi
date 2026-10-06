"""The shingi command line (see cli-spec.md)."""

import sys

from shingi import operations
from shingi.envelope import OperationError, encode, failure, success

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2

COMMANDS = {
    "version": operations.version,
}


def usage_error(reason, argument=None):
    problem = {"reason": reason}
    if argument is not None:
        problem["argument"] = argument
    return OperationError("usage", reason, {"problems": [problem]})


def parse(argv):
    """Return the operation to run, or raise a usage error."""
    if not argv:
        raise usage_error("missing command")
    command, *rest = argv
    if command not in COMMANDS:
        raise usage_error(f"unknown command {command!r}", command)
    if rest:
        raise usage_error(f"unexpected argument {rest[0]!r}", rest[0])
    return COMMANDS[command]


def run(argv):
    """Run one command; return its envelope and exit status."""
    try:
        operation = parse(argv)
    except OperationError as error:
        return failure(error), EXIT_USAGE
    try:
        return success(operation()), EXIT_OK
    except OperationError as error:
        return failure(error), EXIT_ERROR
    except Exception as exc:
        error = OperationError("internal", f"unexpected {type(exc).__name__}: {exc}")
        return failure(error), EXIT_ERROR


def main(argv=None):
    envelope, status = run(sys.argv[1:] if argv is None else argv)
    sys.stdout.buffer.write(encode(envelope).encode("utf-8"))
    sys.stdout.flush()
    if not envelope["ok"]:
        error = envelope["error"]
        print(f"shingi: {error['kind']}: {error['message']}", file=sys.stderr)
    return status
