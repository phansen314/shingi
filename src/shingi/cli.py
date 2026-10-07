"""The shingi command line (see cli-spec.md)."""

import errno
import os
import sys

from shingi import operations
from shingi.envelope import OperationError, encode, failure, success

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2

# Each command: its operation, its positional arguments' fields, and its options' fields.
# A field ending in "@file" is read from the file the option names ("-" is stdin).
COMMANDS = {
    "version": (operations.version, [], {}),
    "kinds": (operations.kinds, [], {}),
    "where": (operations.where, ["unit?"], {}),
    "context": (operations.context, ["unit?"], {}),
    "list": (operations.list_units, ["unit?"], {}),
    "create": (
        operations.create,
        ["path", "kind"],
        {"--title": "title", "--notes": "notes", "--notes-file": "notes@file"},
    ),
    "adopt": (operations.adopt, ["path", "kind"], {"--title": "title"}),
}


def usage_error(reason, argument=None):
    problem = {"reason": reason}
    if argument is not None:
        problem["argument"] = argument
    return OperationError("usage", reason, {"problems": [problem]})


def parse(argv):
    """Return the operation, its input, and --config; or raise a usage error."""
    if not argv:
        raise usage_error("missing command")
    command, *rest = argv
    if command not in COMMANDS:
        raise usage_error(f"unknown command {command!r}", command)
    operation, positional, options = COMMANDS[command]
    options = {**options, "--config": None}
    inp, config, args, files, set_by = {}, None, [], {}, {}
    tokens = iter(rest)
    for token in tokens:
        name, eq, value = token.partition("=")
        if name in options:
            if not eq:
                value = next(tokens, None)
                if value is None:
                    raise usage_error(f"{name} needs a value", token)
            field = options[name]
            if field is None:
                config = value
                continue
            field, _, source = field.partition("@")
            if set_by.setdefault(field, name) != name:
                raise usage_error(f"{set_by[field]} and {name} can't be given together", token)
            if source == "file":
                files[field] = value
            else:
                inp[field] = value
        elif token.startswith("-") and token != "-":
            raise usage_error(f"unknown option {token!r}", token)
        else:
            args.append(token)
    if len(args) > len(positional):
        raise usage_error(f"unexpected argument {args[len(positional)]!r}", args[len(positional)])
    required = [name for name in positional if not name.endswith("?")]
    if len(args) < len(required):
        raise usage_error(f"missing <{required[len(args)]}>")
    inp.update(zip((name.rstrip("?") for name in positional), args))
    for field, file in files.items():
        inp[field] = read_text(file, field)
    if command in ("where", "context") and "unit" not in inp:
        inp["cwd"] = current_directory()
    return operation, inp, config


def read_text(file, field):
    """The contents of `file` ("-" is stdin), exactly, as UTF-8."""
    try:
        if file == "-":
            data = sys.stdin.buffer.read()
        else:
            with open(file, "rb") as f:
                data = f.read()
    except OSError as exc:
        raise OperationError("io", f"{file}: {exc.strerror}", {
            "path": os.path.abspath(file), "code": errno.errorcode.get(exc.errno),
        })
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        raise OperationError("invalid-input", f"{file} is not valid UTF-8", {
            "problems": [{"field": f"/{field}", "reason": "not valid UTF-8"}],
        })


def current_directory():
    try:
        return os.getcwd()
    except OSError as exc:
        raise OperationError("io", f"the current directory can't be read: {exc.strerror}", {
            "path": ".", "code": errno.errorcode.get(exc.errno),
        })


def run(argv):
    """Run one command; return its envelope and exit status."""
    try:
        operation, inp, config = parse(argv)
    except OperationError as error:
        return failure(error), EXIT_USAGE if error.kind == "usage" else EXIT_ERROR
    try:
        result, warnings = operation(inp, config)
        return success(result, warnings), EXIT_OK
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
    elif envelope["warnings"]:
        count = len(envelope["warnings"])
        print(f"shingi: {count} warning{'s' * (count != 1)} (see .warnings in the output)", file=sys.stderr)
    return status
