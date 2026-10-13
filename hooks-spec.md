# shingi hooks spec

## Goals

Let a user run their own commands when shingi changes the tree, so what a kind, a machine, or a workflow needs set up happens without shingi knowing what it is: a `branch` unit's setup task added, a template copied, a coordinator told. shingi makes the structure; hooks do the rest.

- **Notifications, after the fact.** A hook runs once a command has succeeded, and is told what it did. It can't stop the command, change it, or change its result.
- **Simple, and always the same.** Every hook runs synchronously, in the order configured, with a timeout. There is no asynchronous mode, no matching, and no output a hook can return. A hook that wants more does it itself.
- **Seen, never silent.** A hook that fails or runs too long is a warning in the command's envelope. A hooks file shingi can't use stops every command that would run hooks, before it changes anything.
- **The user's own.** Hooks are commands the user wrote into their own config. shingi runs them as given; whether they are safe to run twice, whether they call shingi or koan again, and what they touch are the user's to decide.
- **Shared with koan.** The rules here, but for the events and the payload's `input` and `result`, are tool-agnostic, so koan can run hooks the same way, and one habit covers both.

## Non-goals

- **Running a hook asynchronously.** A hook that starts slow work in the background does so itself (see [Running a hook](#running-a-hook)).
- **Hooks before a command, or hooks that decide.** No hook runs before a change, vetoes one, or returns anything shingi reads but its exit status.
- **Matchers.** Every hook for an event runs for every command that fires it, and filters for itself, with `jq` on its input. A matcher (a kind, a path prefix) is added only if starting hooks that do nothing is ever noticeably slow.
- **Retries.** shingi runs each hook once. A failed hook is told; running it again is the user's (see [By hand](#by-hand)).
- **Guarding against loops.** A hook that runs `shingi create`, whose hook runs `shingi create` again, loops until something fails. Keeping hooks from that is the user's.
- **Sandboxing.** A hook runs with the user's permissions, as anything else they run.

## Terms

| Term | Meaning |
|---|---|
| **hook** | A command in the hooks file, run when an event fires. |
| **event** | What a successful command fires, named after the command: `create`, `adopt`, `delete`. |
| **hooks file** | `hooks.json`, in shingi's config directory, beside `shingi.toml`. |
| **payload** | The JSON a hook reads on stdin: the event, and the command's input, result, and warnings. |

## Events

A command that succeeds fires one event, named after it, once, however much it changed. A command that fails fires none, even one that made something before failing (a `create` or `adopt` whose error carries `partial`, a `delete` that removed the tasks and not the manifest): its error says what it made, and whoever handles the error deals with it. Nor does a `create` or `adopt` that fails reading the new unit back, after the manifest is written: the unit exists with its hooks not run, and they are run [by hand](#by-hand). Reads never fire one.

| Event | Fired by | `input` | `result` |
|---|---|---|---|
| `create` | [`create`](operations.md#create) | `create`'s input | `create`'s output: `{ "unit" }` |
| `adopt` | [`adopt`](operations.md#adopt) | `adopt`'s input | `adopt`'s output: `{ "unit" }` |
| `delete` | [`delete`](operations.md#delete) | `delete`'s input | `delete`'s output |

An event's contract is its command's input and output schemas in [operations.md](operations.md): nothing is defined twice, and a change to a command's output is a change to its event, under the same [versioning](operations.md#versioning).

## The hooks file

`hooks.json` in shingi's config directory, the directory `shingi.toml` is found in (see [Locations](design-spec.md#locations)). It is optional: with none, no hooks run. `--config` names a rules file, not a config directory, and doesn't move it.

JSON, not TOML as the rules file is, since tools write it as well as people: an installer adds its hook with `jq`, as `scripts/install.sh` adds permission rules to Claude Code's `settings.json`.

```json
{
  "schema": 1,
  "hooks": {
    "create": [
      {
        "command": "~/bin/branch-setup.sh",
        "timeout": 30,
        "description": "Add a branch unit's setup task"
      },
      { "command": "~/bin/notify-ino" }
    ],
    "delete": [
      { "command": "~/bin/notify-ino", "disabled": true }
    ]
  }
}
```

### Fields

| Field | Type | Meaning |
|---|---|---|
| `schema` | integer | The file's format version. Required; shingi 0.x supports `1`. |
| `hooks` | object | Each key an event, each value that event's hooks, in the order they run. Optional; default `{}`. |
| `hooks.<event>[].command` | non-empty string | Run by `/bin/sh -c`, so `~`, arguments, and pipes work as in a shell. Required. |
| `hooks.<event>[].timeout` | number > 0 | Seconds the hook may run. Optional; default `10`. No upper limit. |
| `hooks.<event>[].description` | string | What the hook is for, since JSON has no comments. Optional; repeated in its warnings. |
| `hooks.<event>[].disabled` | boolean | `true` skips the hook, as commenting it out would. Optional; default `false`. |

An unknown field, at any level, and an event shingi doesn't fire, are errors, not ignored, so a typo says so rather than a hook silently never running.

A `command` is quoted as a shell quotes: a path with a space in it, as macOS's config directory has, is quoted, with `$HOME` for `~` (`"$HOME/Library/Application Support/shingi/hooks/x.sh"`).

### When it is read

Every command that fires an event reads the hooks file after the rules and before it changes anything, and checks all of it, every event's hooks, not only its own:

1. It can be read, as UTF-8 JSON, one object with no repeated key (`invalid-hooks`, `reason` `unreadable` or `syntax`).
2. `schema` is present and an integer (`invalid`), and one shingi supports (`unsupported-format`).
3. Every other field, as [Fields](#fields) says, each problem reported (`invalid`), disabled hooks' fields among them. A missing required field is reported at the field that is missing (`/hooks/create/0/command`).

So a broken hooks file stops `create`, `adopt`, and `delete` before they change anything: a change never happens with its hooks skipped. Reads never read the file, so a broken one never hides the tree. A file that changes between this check and the hooks running is read once only, here: the hooks that run are the ones checked.

## The payload

What every hook reads on stdin, one line of JSON in the envelope's encoding, ending in a newline as the envelope does:

```json
{
  "schema": 1,
  "tool": "shingi",
  "version": "0.3.0",
  "event": "create",
  "input": { "path": "HOME-12345/foo", "kind": "branch", "title": "foo: retries" },
  "result": { "unit": { "path": "HOME-12345/foo", "id": "3f6c2a9e-…", "kind": "branch", "…": "…" } },
  "warnings": []
}
```

| Field | Meaning |
|---|---|
| `schema` | The payload's format version, `1`. |
| `tool` | `shingi`. koan's payloads say `koan`, so one hook can serve both. |
| `version` | shingi's version, as `shingi version` reports it. |
| `event` | The event. |
| `input` | The command's input as the operation received it: the fields the command line set, or `-i`'s object, so a hook sees the same shape either way. Defaults are not filled in. |
| `result` | The command's `result`, exactly. |
| `warnings` | The command's own warnings, exactly; never another hook's. |

## Running a hook

The hooks for an event run one at a time, in the order the file lists them, skipping disabled ones, after the command has done everything else and before it prints its envelope.

- **The command line:** `/bin/sh -c <command>`.
- **The directory:** the caller's current directory, as for every other process the user starts. The payload names every folder a hook needs.
- **The environment:** shingi's own, unchanged.
- **stdin:** the payload, from a file, not a pipe, so a hook that never reads it never blocks shingi. Every hook reads it from its start, whatever the hooks before it read.
- **stdout:** discarded. Nothing a hook prints reaches shingi's output, which stays one line of JSON.
- **stderr:** kept, to a file, and its last 2,048 bytes reported if the hook fails.
- **Its own process group,** so a timeout ends the hook and everything it started, and nothing of shingi's.
- **Waited for until it exits,** never until its output closes. A hook that starts something in the background and exits is done; the background process goes on, unwatched, and shingi returns.
- **The timeout:** when it passes with the hook still running, shingi sends `SIGKILL` to the hook's process group, with no warning signal first, and reports `hook-timeout`.
- **An interrupt:** shingi killed by `SIGINT`, `SIGTERM`, or `SIGHUP` while a hook runs sends `SIGKILL` to the hook's process group, then dies of the same signal, as it would have (see [Exit codes](cli-spec.md#exit-codes)). The hooks after it don't run.

A hook that exits `0` succeeded. Anything else is a warning, and the next hook still runs.

### By hand

shingi has no command that runs a hook again. A hook that failed, or never ran, is run by hand, with a payload made from `where`:

```sh
shingi where <unit> | jq -c --arg version "$(shingi version | jq -r .result.version)" \
	'{schema: 1, tool: "shingi", version: $version, event: "create", input: {}, result: {unit: .result}, warnings: []}' | <hook>
```

## What a hook changes in the envelope

Only `warnings`. The command's `result`, its exit status, and whether it succeeded are what they would have been with no hooks: a failed hook never fails the command, since its change is already made.

| Kind | When | `unit` | `ids` | `details` |
|---|---|---|---|---|
| `hook-failed` | The hook exited nonzero, was killed by a signal, or couldn't be started. | the unit the command was about; for `delete`, the path of the unit deleted | `[]` | `event`; `index`: its position in the event's list, from `0`, disabled hooks counted, so it is the index in the hooks file; `command`; `description`, or `null`; `exit`: its exit status, `128+n` when signal `n` killed it, as a shell reports it, or `null` when it couldn't be started; `stderr`: the last 2,048 bytes of its stderr, as UTF-8 with invalid bytes replaced. |
| `hook-timeout` | The hook was still running when its timeout passed, and was killed. | the unit the command was about | `[]` | `event`; `index`; `command`; `description`; `timeout`: the seconds it had; `stderr`, as above. |

They are sorted with the command's own warnings, by the [usual order](operations.md#warnings), hooks that tie keeping the order they ran in. That order puts every `hook-failed` before every `hook-timeout`; `index` says the order they ran in.

## Errors

| Kind | Commands | When | `details` |
|---|---|---|---|
| `invalid-hooks` | `create`, `adopt`, `delete` | The hooks file can't be read, isn't JSON, or breaks [Fields](#fields). Nothing was changed. | `path`: the hooks file; `reason`: `unreadable`, `syntax`, or `invalid`; `problems`: for `invalid`, a `{field, reason}` list, `field` a JSON Pointer into the file (`/hooks/create/0/timeout`), sorted by `field`; otherwise empty. `code`: the symbolic OS error, for `unreadable`. |
| `unsupported-format` | `create`, `adopt`, `delete` | The hooks file's `schema` is an integer shingi doesn't support. | As for the rules file: `path`, `schema`, `supported`. `path` says which file it is. |

In each command's precedence, both come right after the rules file's checks: `invalid-input`, `invalid-rules`, `unsupported-format` (the rules), `invalid-hooks`, `unsupported-format` (the hooks), then the command's own. Within the hooks file, the order is the steps of [When it is read](#when-it-is-read), as it is for the rules: an unsupported `schema` is `unsupported-format` whatever else is wrong with the file's fields.

## Trust

A hook is a command the user put in their own config, run with their permissions, as a git hook is. Two consequences are worth knowing:

- **An agent's command runs your hooks.** When an agent runs `shingi create`, Claude Code's permission prompt covers the `shingi create`, not the hooks it then runs. A hook that does something an agent shouldn't trigger shouldn't be in the hooks file.
- **koan's hooks run too.** `create`, `adopt`, and `delete` run koan, and once koan has hooks, a `shingi create` or `adopt` also fires koan's `create-batch` and `block`, and a `shingi delete` koan's `delete-folder`. shingi's tasks carry the tag `shingi`, which a koan hook can test for.

## An example

A `create` hook that gives every new `branch` unit its setup task, wired between its start and done tasks [by convention](design-spec.md#start-and-done-tasks):

```sh
#!/bin/sh
# branch-setup.sh: give a new branch unit its setup task, between its start and done tasks.
unit=$(jq -c .result.unit)
[ "$(printf '%s' "$unit" | jq -r .kind)" = branch ] || exit 0
folder=$(printf '%s' "$unit" | jq -r .koan_folder)
id=$(koan list --folder "$folder" --recursive=false --tags-all branch-setup --readiness ready,blocked,done |
	jq -r '.result.tasks[0].id // empty')      # made already?
[ -n "$id" ] || id=$(koan create "Set up: $(printf '%s' "$unit" | jq -r .path)" --folder "$folder" --tags branch-setup \
	--blocked-by "$(printf '%s' "$unit" | jq -r .start.id)" | jq -er .result.task.id) || exit 1
koan block "$(printf '%s' "$unit" | jq -r .done.id)" --blockers "$id" >/dev/null
```

It filters on its own input, does nothing for other kinds, and looks for its task before making it, so running it twice does no harm, and a run that failed part-way is finished by the next: the kind of care this spec leaves to the hook. Listed under `adopt` as well, it does the same for an adopted folder.

## How it is tested

Each of these is a test, against the real `shingi` and a hooks file in a temporary config directory:

- No hooks file: commands behave as now, with no warnings.
- Each event fires for its command, with the payload above; a failed command and a read fire nothing.
- Hooks run in order; a disabled one is skipped; a failing one doesn't stop the next.
- A hook's stdout never reaches shingi's; its stderr's tail is in `hook-failed`.
- Exit `3`, a command not found (`127`), and a hook killed by `SIGKILL` (`137`) are each `hook-failed`, with that `exit`.
- A hook past its timeout is `hook-timeout`, returns as soon as it passes, and a process it started in the background, in its group, is gone.
- A hook that starts a background process without redirecting its output, and exits, returns at once.
- A hook that never reads stdin, given a payload far over a pipe's buffer, doesn't block.
- Each problem in the hooks file is `invalid-hooks` with its field, and nothing is changed; an unsupported `schema` is `unsupported-format`; reads still work with a broken file.

## Changes to the other specs

- **design-spec.md:** [Post-create hooks](design-spec.md#post-create-hooks) leaves Future work for a short section pointing here, which keeps its `## Log` convention; the "How shingi fits" table's hooks row loses "future work"; Problems gains `invalid-hooks`, `hook-failed`, and `hook-timeout`; `unsupported-format` covers the hooks file. The Claude Code adapter still carries no hooks of Claude Code's.
- **operations.md:** a shared rule, Running hooks, pointing here; `create`, `adopt`, and `delete` gain a last effect, running their event's hooks, and the errors and warnings above; their Retry safety says that a crash while hooks run leaves the change made and the hooks after it not run.
- **cli-spec.md:** Exit codes' "Interrupts are crashes" gains the hook: shingi still dies of the signal, with no envelope, after killing the hook's process group, where a koan call is left to finish.
- **The skill:** report `hook-failed` and `hook-timeout` to the user, never run the command again for one (its change is made), and never write `hooks.json` unasked.
- **README:** a Hooks section, with the file's location and the example.
