# shingi operations

An operation is a single query of, or change to, what the [design spec](design-spec.md) defines. Operations are the domain layer, small and orthogonal. They are not CLI commands, though each command runs exactly one: the design spec's [Commands](design-spec.md#commands) give each command's arguments, and cli-spec.md, once written, maps them onto the input fields here.

The operations are the three that read the tree, [`where`](#where), [`list`](#list), and [`kinds`](#kinds); [`version`](#version); and [`create`](#create), the only one that changes anything.

Terms follow the design spec's [Terms](design-spec.md#terms).

## Conventions

- **JSON in, JSON out.** Input and output are JSON with published schemas, so an agent can build requests and parse results without scraping text. Every result is wrapped in the [output envelope](#output-envelope).
- **Schema identifiers.** Shared schemas have short `$id`s (`envelope`, `error`, `warning`, `unit-path`, `unit`, `task-ref`, `create-partial`). Each operation's are `<op>-input` and `<op>-output`.
- **Referring to operations and kinds.** Operation names, error kinds, and warning kinds are written in code (`create`, `not-found`), linked on their first mention in a section.
- **Parameters.** An operation takes a parameter only if it changes the meaning of the result or the work done.
- **Follow koan.** Where this document is silent on something koan's operations spec covers — the envelope, error precedence, what `io` reports — shingi does what koan does.

## Operation kinds

- ***read*** — Changes nothing and takes no lock: [`where`](#where), [`list`](#list), [`kinds`](#kinds), and [`version`](#version).
- ***write*** — Changes koan's tree and the working root: [`create`](#create). It takes no lock of its own; koan serializes its own writes, and the manifest's exclusive create settles a race (see [Concurrency](design-spec.md#concurrency)).

## Operation template

Every operation is specified with the same parts, in this order. Every part is always present except **Order**, which appears only for operations that return a collection, and **Partial**, which appears only for [`create`](#create). An empty part is written `**Part:** none.`

| Part | Content |
|---|---|
| **Summary** | Unlabeled first paragraph: what the operation does, in one or two sentences. |
| **Kind** | One of the [operation kinds](#operation-kinds). |
| **Input schema** | JSON Schema (draft 2020-12), `$id` `<op>-input`. |
| **Additional validation** | Input rules the schema can't express. All raise `invalid-input`. |
| **Preconditions** | State that must hold beforehand; the matching errors are under Errors. |
| **Effects** | What the operation reads and, for `create`, makes, step by step. |
| **Output schema** | JSON Schema of `result`, `$id` `<op>-output`. |
| **Order** | Collections only: the order of the items. |
| **Errors** | Table of [error kinds](#error-kinds) and when each is raised, in [precedence](#precedence) order. `io` and `internal` are omitted: any operation can raise `internal`, and any but `version` can raise `io`. |
| **Warnings** | Table of [warning kinds](#warning-kinds) and when each is reported. |
| **Partial** | `create` only: what an error reports `create` made. |
| **Retry safety** | Whether running it again after an error, a crash, or an unclear outcome is safe, and with what result. |

## Output envelope

Every operation returns one of two shapes:

```text
{ "ok": true,  "result": { }, "warnings": [ ] }
{ "ok": false, "error":  { }, "warnings": [ ] }
```

- **`result`** — the operation's output, per its Output schema.
- **`error`** — why it failed, per the [error schema](#error-schema). An error means the operation changed nothing, except a `create` whose error carries a `partial`.
- **`warnings`** — problems that did not stop it, per the [warning schema](#warning-schema). Present, possibly empty, on success and failure alike.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "envelope",
  "oneOf": [
    {
      "type": "object",
      "required": ["ok", "result", "warnings"],
      "properties": {
        "ok": { "const": true },
        "result": { "type": "object" },
        "warnings": { "type": "array", "items": { "$ref": "warning" } }
      },
      "additionalProperties": false
    },
    {
      "type": "object",
      "required": ["ok", "error", "warnings"],
      "properties": {
        "ok": { "const": false },
        "error": { "$ref": "error" },
        "warnings": { "type": "array", "items": { "$ref": "warning" } }
      },
      "additionalProperties": false
    }
  ]
}
```

## Errors

`kind` and `details` are the contract; `message` is for people and may change between releases. A caller treats an unknown kind as a generic failure.

### Error kinds

| Kind | Meaning | `details` |
|---|---|---|
| `invalid-input` | The input failed its schema or its additional validation. Reports every problem, not just the first. | `problems`: `{field, reason}` list, `field` a JSON Pointer into the input, `reason` for people; sorted by `field`, then `reason`. |
| `invalid-rules` | The rules file is missing, unreadable, not TOML, or breaks the design spec's [Fields](design-spec.md#fields). A working root that isn't an existing directory is one of these. | `path`: the rules file; `reason`: `missing`, `unreadable`, `syntax`, or `invalid`; `problems`: for `invalid`, a `{field, reason}` list, `field` the dotted TOML key (`roots.working`, `kind.branch.suggests`), sorted by `field`; otherwise empty. `code`: the symbolic OS error, for `unreadable`. |
| `unsupported-format` | The rules file's `schema` is an integer shingi doesn't support. | `path`; `schema`: the one found; `supported`: the ones shingi supports, ascending. |
| `not-found` | The unit named is not a unit, or, from [`where`](#where) without one, the current directory is in no unit. | `unit`: the path given, or `null`; `missing`: the shortest prefix of `unit` that is not a unit (the first folder on the path that doesn't exist, matches only ignoring case, or holds no `uow.json`), or `null`; `cwd`: the directory given, or `null`; `reason`: `not-a-unit` (a path was given), `outside-root`, or `no-unit`. |
| `invalid-name` | A path breaks the design spec's [Names](design-spec.md#names). | `path`: as given; `index`: the first bad segment's position, from `0`; `segment`: that segment; `reason`: `empty` (a leading, trailing, or doubled `/`, or an empty path), `characters`, `length`, `hyphen` (starts or ends with `-`), or, from [`create`](#create) only, `path-length` (the whole path is over 193 characters; `index` and `segment` `null`). |
| `parent-not-found` | `create`'s path has more than one segment, and its parent is not a unit. | `parent`: the parent's path; `missing`: as for `not-found`. |
| `name-taken` | An entry in the parent's folder has the new name in another case, or is a file with it exactly. | `entry`: the entry's name as on disk; `type`: `unit`, `folder`, or `file` (anything not a directory). |
| `unknown-kind` | `create`'s kind is not defined in the rules. | `kind`; `defined`: every defined kind, in name order. |
| `unit-exists` | The unit's `uow.json` already exists. | `manifest`: its path. |
| `koan-failed` | koan could not be run, or returned an error (see [Running koan](#running-koan)). | `call`: `list`, `create-batch`, or `block`; `exit`: koan's exit status, or `null` when it couldn't be run; `error`: koan's `error` object, or `null` when koan printed no envelope. |
| `io` | The filesystem refused: permission denied, disk full, and the like. | `path`; `code`: the symbolic OS error, e.g. `EACCES`, or `null` when it has none. |
| `internal` | A bug shingi detects: an unexpected exception, still reported as an envelope. | `{}`. |

`usage` is a CLI-only kind, raised for a malformed command line, as koan's is.

### Precedence

Each operation's Errors table lists its checks in the order it makes them, and an error is the first check that fails. For every operation but `version`, the first three are always `invalid-input`, `invalid-rules`, and `unsupported-format`; the rules file is checked as [Reading the rules](#reading-the-rules) says.

### Error schema

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "error",
  "type": "object",
  "required": ["kind", "message", "details"],
  "properties": {
    "kind": { "type": "string" },
    "message": { "type": "string", "description": "Human-readable; not part of the contract." },
    "details": { "type": "object" },
    "partial": { "$ref": "create-partial", "description": "create only, and only when it had made something." }
  },
  "additionalProperties": false
}
```

## Warnings

A warning is a problem an operation told and went on past. It never changes the outcome, and never guesses: what it reports as `null` stays `null`.

- **One warning per problem:** per unit for `unsupported-manifest` and `undefined-kind`, per unit and role for `missing-task`, per task for `orphan-task`, per koan warning for `koan-warning`.
- **Deterministic order:** `warnings` is sorted by `kind`, then by `unit` in [path order](design-spec.md#terms), `null` first, then by `ids`, compared element by element as numbers, then by `details.role`, `start` before `done`. `koan-warning`s that still tie keep koan's order, calls in the order shingi made them.

### Warning kinds

| Kind | Meaning | `unit` | `ids` | `details` |
|---|---|---|---|---|
| `unsupported-manifest` | A unit's `uow.json` is unusable (see [Reading a unit](#reading-a-unit)). It is still a unit, with `id` and `kind` `null`, and its tasks can't be matched, so `list` also reports them as `orphan-task`. | the unit | `[]` | `path`: the manifest; `reason`: `unreadable`, `corrupt`, or `unsupported-format`. |
| `undefined-kind` | A unit's kind is not defined in the rules. | the unit | `[]` | `kind`. |
| `missing-task` | No task in the unit's koan folder is its start task, or its done task. Not reported when the manifest is unusable or koan failed, which `null` the tasks for another reason. | the unit | `[]` | `role`: `start` or `done`. |
| `orphan-task` | A task tagged `shingi`, in the koan folders `list` read, that matches no unit. | the unit whose `id` it carries, when `list` found one elsewhere; otherwise `null` | the task | `folder`: the task's koan folder; `source`, `shingi_unit`: its `extra.source` and `extra.shingi-unit`, each `null` when absent or not a string. |
| `parent-done` | The parent's done task was already done, so the new done task was not added to its blockers. | the new unit | the parent's done task | `parent`. |
| `parent-unlinked` | The parent's start or done task could not be found, so that link was left out. | the new unit | `[]` | `parent`; `role`: `start` or `done`; `reason`: `unusable-manifest` or `missing-task`. |
| `notes-kept` | The working folder already held a `uow.md`, which was kept, so the title and notes given were not written. | the new unit | `[]` | `notes_path`. |
| `koan-failed` | koan could not be run, or returned an error, while reading tasks; every task is `null`. | the unit read, or `null` from `list` | `[]` | As the [error](#error-kinds). |
| `koan-warning` | A koan call succeeded with a warning of its own. An unusable task file can hide a start or done task, so while one is present, `missing-task`, `orphan-task`, or `parent-unlinked` may be wrong. | `null` | the koan warning's `ids` | `call`; `warning`: koan's warning, verbatim. |

### Warning schema

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "warning",
  "type": "object",
  "required": ["kind", "message", "unit", "ids", "details"],
  "properties": {
    "kind": { "type": "string", "description": "One of the Warning kinds; callers ignore unknown values." },
    "message": { "type": "string", "description": "Human-readable; not part of the contract." },
    "unit": { "oneOf": [{ "$ref": "unit-path" }, { "type": "null" }] },
    "ids": { "type": "array", "items": { "type": "integer" }, "description": "koan task IDs involved, ascending." },
    "details": { "type": "object" }
  },
  "additionalProperties": false
}
```

## Versioning

The schemas here, the error and warning kinds, and the envelope are shingi's public contract. Adding an optional input field, an output field, or an error or warning kind is a minor change; callers must ignore what they don't know. Anything else is a major change. Before 1.0, as the design spec's [Format versions](design-spec.md#format-versions) says, any of it may change in a minor release.

## Shared rules

### Reading the rules

Every operation but [`version`](#version) reads the rules file first, from its [location](design-spec.md#locations) or the CLI's `--config`, checking it in this order:

1. It exists and can be read (`invalid-rules`, `reason` `missing` or `unreadable`), as UTF-8 TOML (`syntax`).
2. `schema` is present and an integer (`invalid`), and one shingi supports (`unsupported-format`). shingi 0.x supports `1`.
3. Every other field, as [Fields](design-spec.md#fields) says, each problem reported (`invalid`). Unknown fields are problems. `roots.koan` is a koan folder path: `/`, or `/` followed by names joined by `/`. `roots.working`, after a leading `~/` is expanded, is absolute and an existing directory. Each kind name is a koan tag name, `^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$`, and each `suggests` entry names a defined kind.

The working root is then used as its real path, symlinks resolved, everywhere: in every check and every path in output.

### Unit paths

A unit path is a relative path of names, as [Names](design-spec.md#names) defines them. An input path that breaks the rule is `invalid-name`, never looked up, so no path reaches outside the working root.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "unit-path",
  "type": "string",
  "pattern": "^[A-Za-z0-9](?:[A-Za-z0-9-]{0,62}[A-Za-z0-9])?(?:/[A-Za-z0-9](?:[A-Za-z0-9-]{0,62}[A-Za-z0-9])?)*$"
}
```

A unit's **koan folder** is the koan root, `/`, and its path (`/work` + `HOME-12345` is `/work/HOME-12345`; a koan root of `/` gives `/HOME-12345`). Its **working folder** is the working root, `/`, and its path.

### Resolving a path

A path names a unit when, for each prefix of it from the first segment, the folder it names exists — an entry whose name equals the segment byte for byte, so a match only ignoring case doesn't count — is a directory, and holds an entry named `uow.json`. The first prefix that doesn't is the `missing` of a `not-found` or `parent-not-found`.

### Resolving a directory

[`where`](#where) without a unit names the unit `cwd` is in. `cwd`, resolved to its real path, is outside the working root unless it is the working root or under it (`not-found`, `reason` `outside-root`). Otherwise its segments below the working root are walked from the first: the unit is the longest prefix every folder of which holds a `uow.json`, so a directory inside a unit's working material is in that unit. When the first segment's folder holds none, or `cwd` is the working root, it is in no unit (`not-found`, `reason` `no-unit`).

### Walking the tree

[`list`](#list) walks from a unit's working folder, or from the working root. In each folder it lists the entries, skips every entry whose name starts with `.`, and takes each remaining entry that is a directory holding a `uow.json` as a unit, a child of the folder's unit, and walks into it. It walks into nothing else, so working material is never walked. The same test finds a unit's **children** for [`where`](#where).

### Reading a unit

- **The manifest** is usable when it is UTF-8 JSON, one object with exactly `schema`, `id`, and `kind`: `schema` an integer shingi supports (`1`), `id` a UUID in its lowercase canonical 36-character form, `kind` a string. Otherwise it is unusable, and `unsupported-manifest` gives the `reason`: `unreadable` (the file can't be read), `unsupported-format` (`schema` is an integer shingi doesn't support), or `corrupt` (anything else). A usable manifest whose `kind` the rules don't define is `undefined-kind`.
- **The title** is the first line of `uow.md` that holds anything but whitespace, when it starts with `# `: the rest of the line, with surrounding whitespace trimmed. Otherwise, and when `uow.md` is missing or unreadable, it is `""`. `uow.md` is read as UTF-8, with invalid bytes replaced, and its line endings may be `\n` or `\r\n`.
- **A child's kind** is from its manifest, or `null` when that is unusable. A child is never warned about by its parent's `where`.

### Running koan

shingi runs `koan` from `PATH`, with its operation input as JSON on stdin (`koan <op> -i -`), and reads one koan envelope from its stdout.

- **koan could not be run** — not on `PATH`, killed, an exit status other than `0`, `1`, or `2`, or stdout that is not an envelope — is `koan-failed` with `error` `null`. For a write, `create-batch` or `block`, its outcome is unknown: it may have taken effect.
- **koan returned an error** is `koan-failed` with its `error`, with one exception: `list`'s `not-found` whose `folders` names the folder it was given, or a folder above it, means the koan folder doesn't exist yet, as before the first `create`, and is read as no tasks. koan names the first missing folder on the path, so with a koan root of `/work/shingi` and neither folder made yet, it names `/work`.
- **koan's warnings** are passed on, one `koan-warning` each, whether the call succeeded or not.

### Finding start and done tasks

Every read of tasks is one koan `list`:

```json
{ "folder": "<koan folder>", "recursive": false, "readiness": ["ready", "blocked", "done"], "tags_all": ["shingi"] }
```

with `recursive` `true` for [`list`](#list). A task **matches** a unit when its `folder` is the unit's koan folder, its `extra["shingi-unit"]` is the unit's `id`, and its `extra.source` is `shingi-start` (its start task) or `shingi-done` (its done task). When several match one role, the lowest ID is reported. A unit with an unusable manifest has no `id`, so nothing matches it.

### Deriving state

A unit's `state` is `null` when its start or done task is `null`. Otherwise it is `done` when its done task's readiness is `done`, whatever its start task's; otherwise `started` when its start task's is; otherwise `not-started`.

## Shared schemas

### Task ref

A start or done task, as koan reports it.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "task-ref",
  "type": "object",
  "required": ["id", "readiness", "created_at", "completed_at"],
  "properties": {
    "id": { "type": "integer", "minimum": 1 },
    "readiness": { "enum": ["ready", "blocked", "done"] },
    "created_at": { "type": "string", "description": "koan's, verbatim." },
    "completed_at": { "type": ["string", "null"], "description": "koan's, verbatim; null unless done." }
  },
  "additionalProperties": false
}
```

### Unit

One unit, the same wherever it appears: [`where`](#where)'s result, each of [`list`](#list)'s units, [`create`](#create)'s result. Its fields are as the design spec's [Output](design-spec.md#output) describes them.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "unit",
  "type": "object",
  "required": ["path", "id", "kind", "title", "state", "parent", "children", "koan_folder", "working_folder", "notes_path", "start", "done"],
  "properties": {
    "path": { "$ref": "unit-path" },
    "id": { "type": ["string", "null"], "description": "null when the manifest is unusable." },
    "kind": { "type": ["string", "null"], "description": "null when the manifest is unusable." },
    "title": { "type": "string", "description": "\"\" when uow.md has no title." },
    "state": { "enum": ["not-started", "started", "done", null] },
    "parent": { "oneOf": [{ "$ref": "unit-path" }, { "type": "null" }], "description": "null for a top-level unit." },
    "children": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["path", "kind"],
        "properties": {
          "path": { "$ref": "unit-path" },
          "kind": { "type": ["string", "null"] }
        },
        "additionalProperties": false
      },
      "description": "In path order."
    },
    "koan_folder": { "type": "string" },
    "working_folder": { "type": "string", "description": "Absolute." },
    "notes_path": { "type": "string", "description": "Absolute: the working folder's uow.md, whether or not it exists." },
    "start": { "oneOf": [{ "$ref": "task-ref" }, { "type": "null" }] },
    "done": { "oneOf": [{ "$ref": "task-ref" }, { "type": "null" }] }
  },
  "additionalProperties": false
}
```

## Read operations

### where

Return everything about one unit: the unit named, or the one a directory is in.

**Kind:** read.

**Input schema:**

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "where-input",
  "type": "object",
  "properties": {
    "unit": { "type": "string", "description": "The unit's path." },
    "cwd": { "type": "string", "description": "A directory whose unit to report. The CLI passes its own when no unit is given." }
  },
  "additionalProperties": false
}
```

**Additional validation:** exactly one of `unit` and `cwd` is given. `cwd` is absolute.

**Preconditions:** `unit` names a unit, or `cwd` is in one.

**Effects:**

1. [Read the rules](#reading-the-rules).
2. With `unit`: check it is a [unit path](#unit-paths) and [resolve it](#resolving-a-path). With `cwd`: [resolve the directory](#resolving-a-directory).
3. [Read the unit](#reading-a-unit) and find its children.
4. With a usable manifest, [find its start and done tasks](#finding-start-and-done-tasks), non-recursively, in its koan folder. Otherwise both are `null`, and koan isn't run.

**Output schema:**

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "where-output",
  "$ref": "unit"
}
```

**Errors,** in this order:

| Kind | When |
|---|---|
| `invalid-input` | Neither or both of `unit` and `cwd`, a field not a string, or `cwd` not absolute. |
| `invalid-rules`, `unsupported-format` | The rules file is unusable. |
| `invalid-name` | `unit` breaks [Names](design-spec.md#names). |
| `not-found` | `unit` is not a unit; or `cwd` is outside the working root, or in no unit. |

**Warnings:**

| Kind | When |
|---|---|
| `unsupported-manifest` | The unit's manifest is unusable. |
| `undefined-kind` | The unit's kind is not defined. |
| `missing-task` | Its start task, or its done task, is not found. |
| `koan-failed` | koan failed; both tasks are `null`. |
| `koan-warning` | koan warned. |

**Retry safety:**

- After anything: safe. It changes nothing.

### list

Return a unit and every unit beneath it, at any depth, or every unit under the working root, with each one's tasks found in one koan call.

**Kind:** read.

**Input schema:**

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "list-input",
  "type": "object",
  "properties": {
    "unit": { "type": "string", "description": "The root unit's path. Absent: every unit." }
  },
  "additionalProperties": false
}
```

**Additional validation:** none.

**Preconditions:** `unit`, when given, names a unit.

**Effects:**

1. [Read the rules](#reading-the-rules).
2. With `unit`: check it is a [unit path](#unit-paths) and [resolve it](#resolving-a-path).
3. [Walk the tree](#walking-the-tree) from `unit`'s working folder, or the working root, and [read every unit](#reading-a-unit) found, `unit` among them. An unusable manifest doesn't stop the walk: that unit's children are walked like any other's.
4. [Find every task](#finding-start-and-done-tasks), recursively, under `unit`'s koan folder, or the koan root. Match each to its unit. Every task that matches no unit is an `orphan-task`: its `extra.shingi-unit` names no unit found, names a unit whose koan folder it isn't in, or its `extra` doesn't say. A task that matches a role already taken by a lower ID is not an orphan.

**Output schema:**

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "list-output",
  "type": "object",
  "required": ["root", "units"],
  "properties": {
    "root": { "oneOf": [{ "$ref": "unit-path" }, { "type": "null" }], "description": "The unit given, or null." },
    "units": { "type": "array", "items": { "$ref": "unit" }, "description": "Every unit in the tree, the root among them. Empty only for a working root with no units." }
  },
  "additionalProperties": false
}
```

**Order:** `units` in [path order](design-spec.md#terms), so the root comes first and every unit's descendants follow it directly.

**Errors,** in this order:

| Kind | When |
|---|---|
| `invalid-input` | `unit` is not a string. |
| `invalid-rules`, `unsupported-format` | The rules file is unusable. |
| `invalid-name` | `unit` breaks [Names](design-spec.md#names). |
| `not-found` | `unit` is not a unit. |

**Warnings:**

| Kind | When |
|---|---|
| `unsupported-manifest` | A unit's manifest is unusable. |
| `undefined-kind` | A unit's kind is not defined. |
| `missing-task` | A unit's start task, or its done task, is not found. |
| `orphan-task` | A task tagged `shingi` matches no unit. |
| `koan-failed` | koan failed; every unit's tasks are `null`, and no `missing-task` or `orphan-task` is reported. |
| `koan-warning` | koan warned. |

**Retry safety:**

- After anything: safe. It changes nothing.

### kinds

Return every kind the rules define, for a front end to offer.

**Kind:** read.

**Input schema:**

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "kinds-input",
  "type": "object",
  "additionalProperties": false
}
```

**Additional validation:** none.

**Preconditions:** none.

**Effects:** [read the rules](#reading-the-rules).

**Output schema:**

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "kinds-output",
  "type": "object",
  "required": ["kinds"],
  "properties": {
    "kinds": {
      "type": "array",
      "minItems": 1,
      "items": {
        "type": "object",
        "required": ["name", "description", "suggests"],
        "properties": {
          "name": { "type": "string" },
          "description": { "type": "string", "description": "\"\" when the rules give none." },
          "suggests": { "type": "array", "items": { "type": "string" }, "description": "As the rules list them." }
        },
        "additionalProperties": false
      }
    }
  },
  "additionalProperties": false
}
```

**Order:** `kinds` by `name`, byte order.

**Errors,** in this order:

| Kind | When |
|---|---|
| `invalid-input` | The input is not an empty object. |
| `invalid-rules`, `unsupported-format` | The rules file is unusable. |

**Warnings:** none.

**Retry safety:**

- After anything: safe. It changes nothing.

### version

Return shingi's own version.

**Kind:** read. Reads no rules file.

**Input schema:**

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "version-input",
  "type": "object",
  "additionalProperties": false
}
```

**Additional validation:** none.

**Preconditions:** none.

**Effects:** none.

**Output schema:**

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "version-output",
  "type": "object",
  "required": ["version"],
  "properties": {
    "version": { "type": "string", "description": "The installed package's version." }
  },
  "additionalProperties": false
}
```

**Errors:** none.

**Warnings:** none.

**Retry safety:**

- After anything: safe. It changes nothing.

## Write operations

### create

Make one unit: its start and done tasks in koan, linked to its parent's, then its working folder, `uow.md`, and manifest. The unit exists once the manifest is written, and not before.

**Kind:** write.

**Input schema:**

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "create-input",
  "type": "object",
  "required": ["path", "kind"],
  "properties": {
    "path": { "type": "string", "description": "The new unit's path." },
    "kind": { "type": "string" },
    "title": { "type": "string", "minLength": 1, "description": "uow.md's heading. Default: the unit's name." },
    "notes": { "type": "string", "description": "Written to uow.md below the heading. \"\" is the same as absent." }
  },
  "additionalProperties": false
}
```

**Additional validation:** `title` holds no line break (`\n` or `\r`). No string holds a NUL.

**Preconditions:** `path` is a valid unit path of at most 193 characters, `kind` is defined, the parent is a unit (or `path` is one segment), no entry in the parent's folder takes the name, and the unit's `uow.json` doesn't exist.

**Effects:**

1. **Check,** changing nothing:
   1. [Read the rules](#reading-the-rules).
   2. `path` is a [unit path](#unit-paths) (`invalid-name`) of at most 193 characters, so `Start: <path>` fits koan's 200-character title (`invalid-name`, `reason` `path-length`), and `kind` is defined (`unknown-kind`).
   3. With more than one segment, the parent, `path` without its last segment, [resolves](#resolving-a-path) (`parent-not-found`).
   4. List the parent's working folder, or the working root. An entry whose name equals the new name ignoring ASCII case but not exactly is `name-taken`; so is one with exactly the name that is not a directory. A directory with exactly the name that holds a `uow.json` is `unit-exists`. A directory with exactly the name and no `uow.json` is [adopted](design-spec.md#create): it becomes the unit's working folder.
2. **Find the parent's tasks,** with a parent: [read its manifest](#reading-a-unit), and, when usable, [find its start and done tasks](#finding-start-and-done-tasks), non-recursively, in its koan folder. A koan failure here is `koan-failed`, with nothing made. Each of the two that isn't found — the manifest unusable, or no task matches — is `parent-unlinked`, and its link is left out.
3. **Make the tasks.** Make a fresh `id`, a random (version 4) UUID. Run koan `create-batch`:

   ```text
   {
     "folder": "<koan folder>",
     "tasks": [
       { "ref": "start", "title": "Start: <path>", "tags": ["shingi", "shingi-start"], "extra": { "source": "shingi-start", "shingi-unit": "<id>" }, "blocked_by": [<parent's start task ID, when found>] },
       { "ref": "done", "title": "Done: <path>", "tags": ["shingi", "shingi-done"], "extra": { "source": "shingi-done", "shingi-unit": "<id>" }, "blocked_by": ["start"] }
     ]
   }
   ```

   koan makes the koan folder, and any missing folder above it, as it makes a batch's folders. On failure: `koan-failed`, with what koan's own `partial` says it made; when koan's outcome is unknown, with no `partial`, since what it made can't be known.
4. **Link the parent's done task,** when it was found: when its readiness is `done`, warn `parent-done` and leave it; otherwise run koan `block` with `{ "id": <parent's done task ID>, "blockers": [<new done task ID>] }`. On failure: `koan-failed`, with the tasks made; when koan's outcome is unknown, the link may have been made too, and `blocked` is `null`.
5. **Write the files.**
   1. Make the working folder, unless it was adopted. One that appears meanwhile is adopted then.
   2. Create `uow.md` exclusively: `# <title>` and a newline, then, with non-empty `notes`, a blank line and the notes, followed by a newline unless they already end in one. When `uow.md` already exists, adopted or appearing meanwhile, keep it and warn `notes-kept`.
   3. Write the manifest, `{ "schema": 1, "id": <id>, "kind": <kind> }`, in the [file format](design-spec.md#file-format): to a hidden temp file in the working folder, `.uow.json.<random>.tmp`, flushed, then hard-linked as `uow.json`, and the temp file removed. A link that fails because `uow.json` exists is `unit-exists`, with a `partial`. A temp file that can't be removed is left: it is hidden.
6. **Report:** read the new unit as [`where`](#where) does, and return it with the warnings that read gives.

`create` never removes or replaces anything, and never resumes: a failure after step 3 began, and before the manifest is linked, leaves what it made, listed in `partial`. Once the manifest is linked the unit exists, so an error from step 6 carries no `partial`: nothing is to be undone, and running `create` again is `unit-exists`.

**Output schema:**

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "create-output",
  "type": "object",
  "required": ["unit"],
  "properties": {
    "unit": { "$ref": "unit" }
  },
  "additionalProperties": false
}
```

**Errors,** in this order:

| Kind | When |
|---|---|
| `invalid-input` | `path` or `kind` missing or not a string, an empty `title` or one with a line break, a NUL, or an unknown field. |
| `invalid-rules`, `unsupported-format` | The rules file is unusable. |
| `invalid-name` | `path` breaks [Names](design-spec.md#names), or is over 193 characters. |
| `unknown-kind` | `kind` is not defined. |
| `parent-not-found` | The parent is not a unit. |
| `name-taken` | An entry in the parent's folder takes the name in another case, or is a file with it. |
| `unit-exists` | The unit's `uow.json` exists: found by the check, with nothing made, or by the manifest's link, with a `partial`. |
| `koan-failed` | koan failed: finding the parent's tasks, with nothing made; or making the tasks or linking the parent, with a `partial` when anything was made. When koan's outcome is unknown (`error` `null`) while making the tasks or linking the parent, more may have been made than `partial` lists. |

`io` and `internal` come with a `partial` when anything was made and the manifest is not yet linked.

**Warnings:**

| Kind | When |
|---|---|
| `parent-done` | The parent's done task was done; the new done task was not added to its blockers. |
| `parent-unlinked` | The parent's start or done task wasn't found; that link was left out. |
| `notes-kept` | `uow.md` already existed and was kept. |
| `koan-warning` | A koan call warned. |
| any of [`where`](#where)'s | Reading the new unit back warned. |

**Partial:** an error after `create` made something, and before the manifest is linked, carries what it made, for an agent or a person to undo (see [create](design-spec.md#create)). Absent when nothing was made, and once the unit exists.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "create-partial",
  "type": "object",
  "required": ["koan_folders", "tasks", "blocked", "files"],
  "properties": {
    "koan_folders": { "type": "array", "items": { "type": "string" }, "description": "The koan folders koan reported creating, in tree order; never one already there." },
    "tasks": { "type": "array", "items": { "type": "integer" }, "description": "The tasks made: the start task, then the done task." },
    "blocked": {
      "oneOf": [
        { "type": "null" },
        {
          "type": "object",
          "required": ["task", "added"],
          "properties": {
            "task": { "type": "integer", "description": "The parent's done task." },
            "added": { "type": "array", "items": { "type": "integer" } }
          },
          "additionalProperties": false
        }
      ],
      "description": "The blocker added to the parent's done task, or null."
    },
    "files": { "type": "array", "items": { "type": "string" }, "description": "The working folder and uow.md, when made, in that order; never one already there." }
  },
  "additionalProperties": false
}
```

Undo it in this order: `koan delete` each of `tasks`, which also takes the done task out of the parent's done task's blockers; `koan delete-folder` each of `koan_folders`, innermost first; then remove `files`, `uow.md` first.

**Retry safety:**

- After a `koan-failed` whose `error` is `null`, from making the tasks or linking the parent: an unclear outcome, below.
- After any other error without `partial`: safe. Nothing was made, or the unit exists and running it again is `unit-exists`.
- After an error with `partial`: undo what it lists first. Run again without undoing, `create` adopts the folder and makes a second pair of tasks, and the first pair are orphans that still block the parent's done task.
- After success: running it again is `unit-exists`.
- After a crash or an unclear outcome: not safe as it stands. Run [`list`](#list) on the parent, or with no unit for a top-level path: an `orphan-task` carrying a fresh `id` is what the crash left, to delete before running `create` again; a unit at the path means it succeeded.
