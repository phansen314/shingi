"""The shingi command line (see cli-spec.md)."""

import sys

from shingi import operations
from shingi.envelope import OperationError, encode, failure, success

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2

# Each command: its operation, its positional arguments' fields, and its options' fields.
COMMANDS = {
    "version": (operations.version, [], {}),
    "create": (operations.create, ["path", "kind"], {"--title": "title"}),
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
    inp, config, args = {}, None, []
    tokens = iter(rest)
    for token in tokens:
        name, eq, value = token.partition("=")
        if name in options:
            if not eq:
                value = next(tokens, None)
                if value is None:
                    raise usage_error(f"{name} needs a value", token)
            if options[name] is None:
                config = value
            else:
                inp[options[name]] = value
        elif token.startswith("-") and token != "-":
            raise usage_error(f"unknown option {token!r}", token)
        else:
            args.append(token)
    if len(args) > len(positional):
        raise usage_error(f"unexpected argument {args[len(positional)]!r}", args[len(positional)])
    if len(args) < len(positional):
        raise usage_error(f"missing <{positional[len(args)]}>")
    inp.update(zip(positional, args))
    return operation, inp, config


def run(argv):
    """Run one command; return its envelope and exit status."""
    try:
        operation, inp, config = parse(argv)
    except OperationError as error:
        return failure(error), EXIT_USAGE
    try:
        return success(operation(inp, config)), EXIT_OK
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
