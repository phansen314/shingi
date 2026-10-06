# shingi CLI spec

The `shingi` command-line interface: how each command maps to the [operations](operations.md), how input gets in, and what comes out. The CLI adds no behavior of its own beyond parsing arguments, reading `--notes-file`, passing `where` the current directory, and passing `--config` on to the rules; everything about the data is specified by the operations and the [design spec](design-spec.md).

The global rules follow koan's CLI spec almost word for word, so one habit covers koan, sesshin, and shingi. Where shingi differs, this document says so: its subject is optional for `where` and `list`, `create` takes two, and it has a `--config` option.

## Global behavior

### Output

- **JSON only.** Every invocation that exits `0`, `1`, or `2` writes exactly one [output envelope](operations.md#output-envelope) to stdout, whether it succeeds or fails. `--help` is the exception. There is no human-readable output mode: `jq` does the pretty-printing.
- **Passthrough.** Every command runs one operation and writes its envelope unchanged.
- **Compact.** The envelope is written on a single line, followed by a newline, whether or not stdout is a terminal. A complete envelope always ends in that newline.
- **Encoding.** Output is UTF-8, whatever the locale, with koan's string escaping: only `"`, `\`, U+0000–U+001F, U+2028, and U+2029 are escaped; everything else is raw UTF-8.
- **Delivered before exit.** Exit `0`, `1`, or `2` is reported only once the whole envelope has been written. On any other exit status, stdout may hold nothing or an incomplete line (see [Exit codes](#exit-codes)).
- **stderr** gets at most one line from shingi, written after the envelope has been delivered, so a failure stays visible when stdout goes into a pipeline (e.g. `shingi where X | jq -r .result.working_folder`):
  - Exit `1` or `2`: `shingi: <kind>: <message>`, even when the envelope also has warnings.
  - Exit `0` with warnings: `shingi: N warnings (see .warnings in the output)`, or `1 warning` for one. The warnings themselves are never listed.
  - Exit `0` without warnings, and `--help`: nothing.
  - Exit `3`: only its notice.

  The line is human-readable and not part of the contract. Control characters in it are escaped, so it stays one line. Callers read the envelope. A failure to write it is ignored and never changes the exit status.
- **No traceback, ever.** An unexpected exception is an `internal` envelope, exit `1`; an interrupt is a [crash](#exit-codes), with no envelope and no traceback.
- **Exception:** `--help` writes plain-text usage to stdout. It is not an operation.

### Input

- **Arguments and options** supply operation input for everyday use.
- **`-i, --input <file>`** supplies operation input read from `<file>`, where `-` means stdin. Every command accepts it.
- **stdin is read only when a value names it:** `--input -`, or `create`'s `--notes-file -`. shingi never reads stdin on its own, so it is safe inside loops that feed stdin to something else.
- **Any readable path.** `<file>` may be any path that can be read to the end, including process substitution and named pipes. A file literally named `-` is given as `./-`.
- **Exactly one JSON object, in UTF-8.** Empty input, a value that is not an object, a second value, trailing bytes, a duplicate key, a byte-order mark, or invalid UTF-8 is `invalid-input` (`field`: `""`).
- **Operation rules apply.** The input is held to the operation's input schema and additional validation; violations are `invalid-input`.
- **Unreadable input.** A missing or unreadable `<file>`, or a directory, is `io`.
- **Either `--input` or field arguments, not both.** Giving `--input` together with any argument or option that sets an input field is a [usage error](#usage-errors). `--config` sets no input field, so it goes with either.
- **`--input` is taken as-is.** In particular, `where -i` gets no `cwd` from the CLI: the input names the unit or the directory itself.

```sh
jq -n '{path: "HOME-12345", kind: "group", title: "Payment retries"}' | shingi create -i -
jq -n --arg d "$PWD" '{cwd: $d}' | shingi where -i -
```

### Command line

The command line is parsed in the GNU style, with koan's rules:

- **Command names are operation names:** `where`, `list`, `kinds`, `version`, `create`. There are no aliases.
- **Option names are field names,** in kebab-case. `--notes-file` and `--config` are the exceptions: neither sets a field under its own name.
- **Arguments are for required subjects,** with two departures from koan. `where` and `list` take their unit as an optional argument, since a unit is a path and no option could be confused with one; and `create` takes two, its path and its kind, in that order. Everything else is an option, so a bare token always has one meaning.
- **Paths are exact.** A unit path is taken exactly as given: never completed, normalized, case-folded, or derived from the working directory (but see [`where`](#where)). `HOME-12345/` and `/HOME-12345` reach the operation as given, which rejects them as `invalid-name`.
- **Options and arguments follow the command,** in any order: `shingi <command> [options and arguments]`. `--help` may also be given with no command.
- **`--`** ends options; everything after it is an argument. A lone `-` is an ordinary argument.
- **Option values** may be given as `--flag value` or `--flag=value`, and `-i` as `-i value` or `-ivalue`. An option that takes a value always consumes the next token, even one starting with `-`.
- **Exact names.** Commands and options are matched exactly: no abbreviations and no other case.
- **Empty values are values:** `--title ''` sets the empty string, which the operation rejects as `invalid-input`; `--notes ''` is no notes.
- **Arguments are single tokens.** A value with spaces, such as a title, is one argument, quoted for the shell.
- **Encoding.** Every value is UTF-8; one that is not is `invalid-input` at its field, reported in the operation's own `invalid-input` together with any other problems in the input.
- **The CLI rejects only what it cannot build:** two different options that set one field (`--notes` with `--notes-file`), or `--input` with a field argument or option. Everything else reaches the operation.
- **A repeated option** that takes one value: the last one wins.
- **Bare `shingi`**, with no command, is a usage error.
- **`--help`** (or `-h`) writes help text and exits `0`, running no operation. Help text is for people and not part of the contract.
- **No `help`, `completion`, or `init` command.** Each is a usage error, like any unknown command.

### Usage errors

A usage error is a problem with the command line itself: an unknown command or option, a missing or extra argument, an option missing its value, two different options that set one field, `--input` together with field arguments or options. It is reported as an envelope with error kind `usage`, and exits `2`. A token in the right place whose value is unacceptable is `invalid-input` or `invalid-name`, from the operation, the same error whether it arrives as an argument or through `--input`.

`usage` is the CLI's only error kind of its own: no operation raises it. `details` reports the first problem found, as koan's does:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "usage-details",
  "type": "object",
  "required": ["problems"],
  "properties": {
    "problems": {
      "type": "array",
      "minItems": 1,
      "items": {
        "type": "object",
        "required": ["reason"],
        "properties": {
          "argument": { "type": "string", "description": "The offending command-line token, when there is one. Absent when something is missing." },
          "reason": { "type": "string", "description": "Human-readable." }
        },
        "additionalProperties": false
      }
    }
  },
  "additionalProperties": false
}
```

### Exit codes

| Code | Meaning |
|---|---|
| `0` | Success (`ok: true`), with or without warnings. Also `--help`. |
| `1` | Operation error. The kind is in the envelope. |
| `2` | Usage error. |
| `3` | Outcome unknown: the envelope could not be written to stdout. |
| any other | Outcome unknown: shingi was terminated before it finished (e.g. `128+n` for signal `n`). Handle like `3`. |

- **One code for all operation errors.** Callers branch on the envelope's `kind`, not the exit code.
- **Outcome unknown.** On `3` or any status outside `0`–`2`, the operation may already have taken effect. The caller follows the operation's **Retry safety** for a crash. For a read, rerunning is always safe; for [`create`](operations.md#create), it is not, as it stands.
- **Unwritable stdout.** When stdout cannot be written (a closed pipe, a full disk behind a redirect), shingi exits `3` with a notice on stderr. This applies even when nothing was run, e.g. a usage error with stdout closed.
- **Interrupts are crashes.** An interrupt or termination signal (Ctrl-C, `kill`, a harness's timeout) ends shingi as the signal's default would: no envelope, no traceback, exit `128+n`. A koan call it was waiting on is koan's to finish or not.

### Global options

| Option | Meaning |
|---|---|
| `-i, --input <file>` | Read operation input from `<file>` (`-` for stdin). See [Input](#input). |
| `--config <file>` | Read the rules from `<file>` instead of their [location](design-spec.md#locations), for tests and trials. Relative to the current directory; `~` is the shell's to expand. A missing or unreadable file is [`invalid-rules`](operations.md#error-kinds), as at the usual location, its `details.path` the file's absolute path. `version`, which reads no rules, accepts and ignores it. |
| `-h, --help` | Print plain-text usage. |

## Command template

Every command is specified with these parts, in this order. Every part is always present. An empty part is written `**Part:** none.`

| Part | Content |
|---|---|
| **Summary** | Unlabeled first paragraph: what the command does, and the operation it runs, linked. |
| **Synopsis** | The usage line(s). |
| **Operation** | The operation the command runs. |
| **Arguments** | Table of positional arguments and the input field each sets. |
| **Options** | Table of command-specific options (not the [global options](#global-options)), the input field each sets, and its default. |
| **Input** | Anything about input beyond the Arguments and Options mapping. |
| **Output** | `Passthrough.`, or how the output differs from the operation's. |
| **Errors** | Errors the CLI adds beyond the operation's. Usually none. |
| **Examples** | `sh` examples, with the `jq` side where it helps. |

Exit codes are not a part: they follow from the envelope and the [Exit codes](#exit-codes) table.

## Commands

### where

Everything about one unit: the unit named, or the one the current directory is in. Runs [`where`](operations.md#where).

**Synopsis:** `shingi where [<unit>]`, or `shingi where -i <file>`.

**Operation:** [`where`](operations.md#where).

**Arguments:**

| Argument | Field | Notes |
|---|---|---|
| `<unit>` | `/unit` | Optional. The unit's path, exact. |

**Options:** none.

**Input:** with no `<unit>` and no `--input`, the CLI sets `cwd` to the process's current directory, so `shingi where` in a unit's working folder, or anywhere in its working material, names that unit. A current directory that no longer exists is `io`. With `--input`, the input is taken as-is: exactly one of `unit` and `cwd`.

**Output:** Passthrough: the [unit](operations.md#unit).

**Errors:**

| Kind | When |
|---|---|
| `io` | With no unit, the current directory can't be read, e.g. it was removed. `details.path` is `"."`. |

**Examples:**

```sh
shingi where | jq -r .result.path                                  # which unit am I in?
cd "$(shingi where HOME-12345/foo-1-schema | jq -r .result.working_folder)"
shingi where HOME-12345 | jq -r '.result.children[].path'
shingi where HOME-12345/foo-1-schema | jq '.result | {state, start: .start.id, done: .done.id}'
```

### list

A unit and every unit beneath it, at any depth, or every unit under the working root. Runs [`list`](operations.md#list).

**Synopsis:** `shingi list [<unit>]`, or `shingi list -i <file>`.

**Operation:** [`list`](operations.md#list).

**Arguments:**

| Argument | Field | Notes |
|---|---|---|
| `<unit>` | `/unit` | Optional. The root unit's path, exact. Absent: every unit. |

**Options:** none. Filtering, such as leaving out what's done, is `jq`'s for now (see [Not included](#not-included)).

**Input:** none beyond the Arguments mapping. Unlike `where`, `list` never looks at the current directory.

**Output:** Passthrough. `result.units` is in [path order](design-spec.md#terms), the root first.

**Errors:** none beyond the operation's.

**Examples:**

```sh
shingi list | jq -r '.result.units[] | select(.state != "done") | .path'      # what's left
shingi list HOME-12345 | jq -r '.result.units[] | "\(.state)\t\(.path)\t\(.title)"'
shingi list | jq '[.warnings[] | select(.kind == "orphan-task")]'             # what a crash left
```

### kinds

Every kind the rules define, for a front end to offer. Runs [`kinds`](operations.md#kinds).

**Synopsis:** `shingi kinds`, or `shingi kinds -i <file>`.

**Operation:** [`kinds`](operations.md#kinds).

**Arguments:** none.

**Options:** none.

**Input:** none. With `--input`, the only valid input is `{}`.

**Output:** Passthrough.

**Errors:** none beyond the operation's.

**Examples:**

```sh
shingi kinds | jq -r '.result.kinds[] | "\(.name)\t\(.description)"'
shingi kinds | jq -r '.result.kinds[] | select(.name == "group") | .suggests[]'
```

### version

shingi's own version. Runs [`version`](operations.md#version).

**Synopsis:** `shingi version`, or `shingi version -i <file>`.

**Operation:** [`version`](operations.md#version).

**Arguments:** none.

**Options:** none.

**Input:** none. With `--input`, the only valid input is `{}`.

**Output:** Passthrough.

**Errors:** none beyond the operation's.

**Examples:**

```sh
shingi version | jq -r .result.version
```

### create

Make one unit: its start and done tasks in koan, its working folder, `uow.md`, and manifest. Runs [`create`](operations.md#create).

**Synopsis:** `shingi create <path> <kind> [--title <text>] [--notes <text> | --notes-file <file>]`, or `shingi create -i <file>`.

**Operation:** [`create`](operations.md#create).

**Arguments:**

| Argument | Field | Notes |
|---|---|---|
| `<path>` | `/path` | Required unless `--input` is given. The new unit's path, exact. |
| `<kind>` | `/kind` | Required unless `--input` is given. A kind the rules define. |

**Options:**

| Option | Field | Default |
|---|---|---|
| `--title <text>` | `/title` | The unit's name. One line. |
| `--notes <text>` | `/notes` | No notes. Mutually exclusive with `--notes-file`. |
| `--notes-file <file>` | `/notes` | No notes. Reads the notes from `<file>`; `-` is stdin. Mutually exclusive with `--notes`. |

**Input:** `--notes-file` reads the file's contents exactly as they are, trailing newline included, into `notes`; `create` adds a final newline only when they lack one. It accepts any readable path, as [`--input`](#input) does. Since `--input` excludes field options, `--notes-file -` and `--input -` never both read stdin.

- **`--notes`** suits a line or two.
- **`--notes-file -`** suits notes another command produces: no shell escaping, no argument size limit.

**Output:** Passthrough: `{ "unit" }`, the new unit.

**Errors:**

| Kind | When |
|---|---|
| `io` | The `--notes-file` file is missing, unreadable, or a directory. |
| `invalid-input` | (`/notes`) The `--notes-file` contents are not valid UTF-8. |

**Examples:**

```sh
shingi create HOME-12345 group --title 'Payment retries'
shingi create HOME-12345/foo-split group --title 'foo: seven stacked MRs'
shingi create HOME-12345/foo-split/1-schema branch --title 'foo: schema changes' | jq -r .result.unit.start.id
printf 'Story: retry failed payments.\n' | shingi create HOME-12345 group --notes-file -
shingi create HOME-12345/research group 2>/dev/null | jq -e .ok >/dev/null || echo 'create failed'
```

## Not included

- **Environment overrides.** No `SHINGI_*` variable sets a location or a rule (see [Locations](design-spec.md#locations)); `--config` is the one override, for one command.
- **`init`.** A missing rules file is `invalid-rules`, whose message points to the example in the design spec's [The rules file](design-spec.md#example).
- **Filtering `list`.** `--open` is [future work](design-spec.md#filtering-list); until then, `jq`.
- **Human-readable output and tree views.** The CLI is JSON only.
- **Shell completion.**
