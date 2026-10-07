"""The shingi command line (see cli-spec.md)."""

import errno
import json
import os
import signal
import sys

from shingi import operations
from shingi.envelope import OperationError, encode, failure, success

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2
EXIT_UNKNOWN = 3

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


# Each command's help: its synopsis and what it does.
HELP = {
    "where": ("shingi where [<unit>]", "Everything about one unit: the one named, or the one the current directory is in."),
    "context": ("shingi context [<unit>]", "Everything an agent needs to start work on one unit."),
    "list": ("shingi list [<unit>]", "A unit and every unit beneath it, or every unit."),
    "kinds": ("shingi kinds", "Every kind the rules define."),
    "version": ("shingi version", "shingi's own version."),
    "create": (
        "shingi create <path> <kind> [--title <text>] [--notes <text> | --notes-file <file>]",
        "Make one unit: its start and done tasks in koan, its working folder, uow.md, and manifest.",
    ),
    "adopt": ("shingi adopt <path> <kind> [--title <text>]", "Make an existing folder a unit, leaving what is in it."),
}

GLOBAL_OPTIONS = """\
Options:
  -i, --input <file>  read the operation's input, one JSON object, from <file> (- for stdin)
  --config <file>     read the rules from <file> instead of the usual shingi.toml
  -h, --help          print this help

Output is one line of JSON: {"ok", "result" or "error", "warnings"}.
Exit 0 success, 1 operation error, 2 usage error, 3 or other: outcome unknown.
"""


class Help(Exception):
    """--help was given: print `text` and exit 0."""

    def __init__(self, text):
        self.text = text


def help_text(command=None):
    if command is None:
        width = max(map(len, HELP))
        lines = [f"  {name:<{width}}  {summary}" for name, (_, summary) in HELP.items()]
        return "Usage: shingi <command> [options and arguments]\n\nCommands:\n" + "\n".join(lines) + "\n\n" + GLOBAL_OPTIONS
    synopsis, summary = HELP[command]
    return f"Usage: {synopsis}\n       shingi {command} -i <file>\n\n{summary}\n\n{GLOBAL_OPTIONS}"


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
    if command in ("-h", "--help"):
        raise Help(help_text())
    if command not in COMMANDS:
        raise usage_error(f"unknown command {command!r}", command)
    operation, positional, options = COMMANDS[command]
    options = {**options, "--config": None, "--input": "@input", "-i": "@input"}
    inp, config, args, files, set_by, input_file = {}, None, [], {}, {}, None
    tokens = iter(rest)
    for token in tokens:
        if token == "--":
            args += tokens
            break
        if token in ("-h", "--help"):
            raise Help(help_text(command))
        if token.startswith("-i") and len(token) > 2:  # -ivalue
            name, eq, value = "-i", "=", token[2:]
        else:
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
            if field == "@input":
                input_file = value
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
    if input_file is not None:
        if args or set_by:
            clash = args[0] if args else next(iter(set_by.values()))
            raise usage_error(f"--input can't be given with {clash!r}", clash)
        return operation, read_input(input_file), config
    required = [name for name in positional if not name.endswith("?")]
    if len(args) < len(required):
        raise usage_error(f"missing <{required[len(args)]}>")
    inp.update(zip((name.rstrip("?") for name in positional), args))
    for field, file in files.items():
        inp[field] = read_text(file)
    if command in ("where", "context") and "unit" not in inp:
        inp["cwd"] = current_directory()
    return operation, inp, config


def read_bytes(file):
    """The contents of `file` ("-" is stdin), exactly."""
    try:
        if file == "-":
            return sys.stdin.buffer.read()
        with open(file, "rb") as f:
            return f.read()
    except OSError as exc:
        raise OperationError("io", f"{file}: {exc.strerror}", {
            "path": os.path.abspath(file), "code": errno.errorcode.get(exc.errno),
        })


def read_text(file):
    """The contents of `file` as text; bytes that aren't UTF-8 become lone surrogates, which the
    operation reports as invalid-input, as it does a command-line value's."""
    return read_bytes(file).decode("utf-8", "surrogateescape")


def read_input(file):
    """--input's file: exactly one JSON object, in UTF-8."""
    data = read_bytes(file)
    if data.startswith(b"\xef\xbb\xbf"):
        raise bad_input("starts with a byte-order mark")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise bad_input("not valid UTF-8")
    try:
        value = json.loads(text, object_pairs_hook=no_duplicate_keys, parse_constant=not_json)
    except ValueError as exc:
        raise bad_input(f"not one JSON value: {exc}")
    if not isinstance(value, dict):
        raise bad_input("not a JSON object")
    return value


def bad_input(reason):
    return OperationError("invalid-input", f"invalid input: {reason}", {
        "problems": [{"field": "", "reason": reason}],
    })


def no_duplicate_keys(pairs):
    keys = [key for key, _ in pairs]
    duplicates = sorted({key for key in keys if keys.count(key) > 1})
    if duplicates:
        raise ValueError(f"duplicate key {duplicates[0]!r}")
    return dict(pairs)


def not_json(constant):
    raise ValueError(f"{constant} is not JSON")


def current_directory():
    try:
        return os.getcwd()
    except OSError as exc:
        raise OperationError("io", f"the current directory can't be read: {exc.strerror}", {
            "path": ".", "code": errno.errorcode.get(exc.errno),
        })


def run(argv):
    """Run one command; return what to write to stdout and the exit status."""
    try:
        operation, inp, config = parse(argv)
    except Help as help:
        return help.text, EXIT_OK
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
    # An interrupt is a crash: no envelope, no traceback, exit 128+n (cli-spec.md, Exit codes).
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    output, status = run(sys.argv[1:] if argv is None else argv)
    text = output if isinstance(output, str) else encode(output)
    if sys.stdout is None:  # fd 1 was closed before shingi started
        notice("shingi: the output could not be written (stdout is closed); the outcome is unknown")
        return EXIT_UNKNOWN
    try:
        sys.stdout.buffer.write(text.encode("utf-8"))
        sys.stdout.flush()
    except OSError as exc:
        # Keep Python from failing again flushing stdout at exit.
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        notice(f"shingi: the output could not be written ({exc.strerror}); the outcome is unknown")
        return EXIT_UNKNOWN
    if isinstance(output, str):
        return status
    if not output["ok"]:
        error = output["error"]
        notice(f"shingi: {error['kind']}: {error['message']}")
    elif output["warnings"]:
        count = len(output["warnings"])
        notice(f"shingi: {count} warning{'s' * (count != 1)} (see .warnings in the output)")
    return status


def notice(line):
    """Write one line to stderr, its control characters escaped; a failure is ignored."""
    line = "".join(
        c.encode("unicode_escape").decode("ascii") if ord(c) < 0x20 or 0x7F <= ord(c) < 0xA0 or c in "\u2028\u2029" else c
        for c in line
    )
    try:
        print(line, file=sys.stderr, flush=True)
    except (OSError, ValueError):
        pass
