# shingi hooks spec

## Goals

Let a user run their own commands when shingi changes the tree, so what a kind, a machine, or a workflow needs set up happens without shingi knowing what it is: a template copied into a `branch` unit's working folder, a line added to its log, a coordinator told. shingi makes the structure; hooks do the rest.

- **Notifications, after the fact.** A hook runs once a command has succeeded, and is told what it did. It can't stop the command, change it, or change its result.
- **Simple, and always the same.** Every hook runs synchronously, in the order configured, with a timeout. There is no asynchronous mode, no matching, and no output a hook can return. A hook that wants more does it itself.
- **Seen, never silent.** A hook that fails or runs too long is a warning in the command's envelope. A hooks file shingi can't use stops every command that would run hooks, before it changes anything.
- **The user's own.** Hooks are commands the user wrote into their own config. shingi runs them as given; whether they are safe to run twice, whether they call shingi again, and what they touch are the user's to decide.

## Non-goals

- **Running a hook asynchronously.** A hook that starts slow work in the background does so itself (see [Running a hook](#running-a-hook)).
- **Hooks before a command, or hooks that decide.** No hook runs before a change, vetoes one, or returns anything shingi reads but its exit status.
- **Matchers.** Every hook for an event runs for every command that fires it, and filters for itself, with `jq` on its input. A matcher (a kind, a path prefix) is added only if starting hooks that do nothing is ever noticeably slow.
- **Skipping hooks for one command.** No flag or environment variable turns hooks off for a single run. A hook is turned off in the hooks file, with `disabled`, for every command.
- **Retries.** shingi runs each hook once. A failed hook is told; running it again is the user's (see [By hand](#by-hand)).
- **Guarding against loops.** A hook that runs `shingi create`, whose hook runs `shingi create` again, loops until something fails. Keeping hooks from that is the user's.
- **Serializing hooks across commands.** Two shingi commands run at the same time run their hooks at the same time. A hook that can't share what it touches with another copy of itself takes its own lock.
- **Sandboxing.** A hook runs with the user's permissions, as anything else they run.

## Terms

| Term | Meaning |
|---|---|
| **hook** | A command in the hooks file, run when an event fires. |
| **event** | What a successful command fires, named after the command: `create`, `adopt`, `create-batch`, `delete`. |
| **hooks file** | `hooks.json`, in shingi's config directory, beside `shingi.toml`. |
| **payload** | The JSON a hook reads on stdin: the event, and the command's input, result, and warnings. |

## Events

A command that succeeds fires one event, named after it, once, however much it changed. A command that fails fires none, even one that made something before failing (a `create` or `adopt` whose error carries `partial`, a `create-batch` whose `partial` names units that exist, a `delete` that removed the tasks and not the manifest): its error says what it made, and whoever handles the error deals with it. Nor does a `create`, `adopt`, or `create-batch` that fails reading the new units back, after the manifests are written: the units exist with their hooks not run, and they are run [by hand](#by-hand). Reads never fire one.

| Event | Fired by | `input` | `result` |
|---|---|---|---|
| `create` | [`create`](operations.md#create) | `create`'s input | `create`'s output: `{ "unit" }` |
| `adopt` | [`adopt`](operations.md#adopt) | `adopt`'s input | `adopt`'s output: `{ "unit" }` |
| `create-batch` | [`create-batch`](operations.md#create-batch) | `create-batch`'s input | `create-batch`'s output: `{ "units" }` |
| `delete` | [`delete`](operations.md#delete) | `delete`'s input | `delete`'s output |

A `create-batch` fires `create-batch` alone, once, never `create` for each unit: a hook that sets up a new unit however it was made is listed under both, and reads `.result.unit` for one and `.result.units[]` for the other. An empty batch succeeds, and fires it with no units.

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
        "description": "Give a branch unit a plan.md from a template"
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
| `hooks.<event>[].timeout` | finite number > 0 | Seconds the hook may run. Optional; default `10`. No upper limit, but one that reads as infinite, such as `1e999`, is an error. |
| `hooks.<event>[].description` | string | What the hook is for, since JSON has no comments. Optional; repeated in its warnings. |
| `hooks.<event>[].disabled` | boolean | `true` skips the hook, as commenting it out would. Optional; default `false`. |

An unknown field, at any level, and an event shingi doesn't fire, are errors, not ignored, so a typo says so rather than a hook silently never running.

A `command` is quoted as a shell quotes: a path with a space in it, as macOS's config directory has, is quoted, with `$HOME` for `~` (`"$HOME/Library/Application Support/shingi/hooks/x.sh"`).

### When it is read

Every command that fires an event reads the hooks file after the rules and before it changes anything, and checks all of it, every event's hooks, not only its own:

1. It can be opened and read (`invalid-hooks`, `reason` `unreadable`), and is UTF-8 JSON, one object, with no key repeated at any level (`syntax`). `NaN` and `Infinity` aren't JSON, and are `syntax` too.
2. `schema` is present and an integer (`invalid`), and one shingi supports (`unsupported-format`).
3. Every other field, as [Fields](#fields) says, each problem reported (`invalid`), disabled hooks' fields among them. A missing required field is reported at the field that is missing (`/hooks/create/0/command`).

So a broken hooks file stops `create`, `adopt`, `create-batch`, and `delete` before they change anything: a change never happens with its hooks skipped. Reads never read the file, so a broken one never hides the tree. A file that changes between this check and the hooks running is read once only, here: the hooks that run are the ones checked.

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
| `tool` | `shingi`, so a hook that other tools run too knows which ran it. |
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
- **stderr:** kept, to a file, and its last 2,048 bytes reported if the hook fails or runs past its timeout.
- **Its own Unix session, and so its own process group** (`setsid`). A timeout ends the hook and everything it started, and nothing of shingi's. With no terminal, a hook that tries to read from one fails at once, where one in shingi's own would be stopped and sit until its timeout.
- **Waited for until it exits,** never until its output closes. A hook that starts something in the background and exits is done; the background process goes on, unwatched, and shingi returns.
- **The timeout:** when it passes with the hook still running, shingi sends `SIGKILL` to the hook's process group, with no warning signal first, and reports `hook-timeout`.
- **An interrupt:** shingi killed by `SIGINT`, `SIGTERM`, or `SIGHUP` while a hook runs sends `SIGKILL` to the hook's process group, then dies of the same signal, as it would have (see [Exit codes](cli-spec.md#exit-codes)). The hooks after it don't run. A signal that was ignored when shingi started stays ignored while a hook runs, as it is with none. A shingi killed by `SIGKILL`, or one that crashes, kills nothing: its hook runs on, with nothing watching it or its timeout.

A hook that exits `0` succeeded. Anything else is a warning, and the next hook still runs. So is anything that goes wrong in shingi running a hook, a missing temporary file among it: it is `hook-failed`, and the command's outcome never changes.

### By hand

shingi has no command that runs a hook again. A hook that failed, or never ran, is run by hand, with a payload made from `where`:

```sh
shingi where <unit> | jq -c --arg version "$(shingi version | jq -r .result.version)" \
	'{schema: 1, tool: "shingi", version: $version, event: "create", input: {path: .result.path, kind: .result.kind}, result: {unit: .result}, warnings: []}' | <hook>
```

- **`input`** has the two fields `create` and `adopt` always have. `title` and `notes` are absent, as when the command was given neither.
- **`event`** is `adopt` for a unit that was adopted.
- **A `create-batch` hook** is given a payload made the same way from `where` of each unit, `event` `create-batch`, `input` `{ "units": [{ "path", "kind" }, …] }`, and `result` `{ "units": [ … ] }`, in path order.
- **A `delete` hook** can't be run this way: the unit is gone, and `where` can't find it. Its payload is made from the `delete`'s own envelope, whose `result` is the payload's, with `input` `{ "unit": <its path> }`.

## What a hook changes in the envelope

Only `warnings`. The command's `result`, its exit status, and whether it succeeded are what they would have been with no hooks: a failed hook never fails the command, since its change is already made.

| Kind | When |
|---|---|
| `hook-failed` | The hook exited nonzero, was killed by a signal, or couldn't be started: shingi unable to make the temporary files a hook needs, on a full disk say, is that too. |
| `hook-timeout` | The hook was still running when its timeout passed, and was killed. |

Each one's `unit`, `ids`, and `details`, and where it sorts among the command's own warnings, are in operations.md's [Warnings](operations.md#warnings).

## Errors

| Kind | Commands | When |
|---|---|---|
| `invalid-hooks` | `create`, `adopt`, `create-batch`, `delete` | The hooks file can't be read, isn't JSON, or breaks [Fields](#fields). Nothing was changed. |
| `unsupported-format` | `create`, `adopt`, `create-batch`, `delete` | The hooks file's `schema` is an integer shingi doesn't support. Nothing was changed. |

Their `details` are in operations.md's [Error kinds](operations.md#error-kinds), and where they come among a command's other errors, right after the rules file's, in its [Precedence](operations.md#precedence).

## Trust

A hook is a command the user put in their own config, run with their permissions, as a git hook is. One consequence is worth knowing: **an agent's command runs your hooks.** When an agent runs `shingi create`, Claude Code's permission prompt covers the `shingi create`, not the hooks it then runs. A hook that does something an agent shouldn't trigger shouldn't be in the hooks file.

## An example

A `create` and `create-batch` hook that gives every new `branch` unit a plan to fill in, copied from a template:

```sh
#!/bin/sh
# branch-setup.sh: give each new branch unit a plan.md, from a template.
jq -c '.result.unit // .result.units[]' | while read -r unit; do
	[ "$(printf '%s' "$unit" | jq -r .kind)" = branch ] || continue
	plan=$(printf '%s' "$unit" | jq -r .working_folder)/plan.md
	[ -e "$plan" ] || cp ~/templates/branch-plan.md "$plan"      # never over one already there
done
```

It reads one unit from `create` and every unit from `create-batch`, filters on its own input, does nothing for other kinds, and looks before it writes, so running it twice does no harm: the kind of care this spec leaves to the hook. Listed under `adopt` as well, it does the same for an adopted folder.

## How it is tested

Against the real `shingi`, with a hooks file in a temporary config directory, one test for each rule here. The tests are listed in the implementation spec's [Tests](hooks-impl-spec.md#tests).

## In the other specs

- **design-spec.md:** a summary, [Hooks](design-spec.md#hooks); the hooks file in Locations; the new kinds in Problems. The `## Log` convention a hook follows is in [The notes file](design-spec.md#the-notes-file).
- **operations.md:** the shared rule, [Running hooks](operations.md#running-hooks); the kinds' `details`, sorting, and precedence; and the hooks' place in `create`, `adopt`, `create-batch`, and `delete`, with their Retry safety.
- **cli-spec.md:** that a hook writes nothing to shingi's output, in [Output](cli-spec.md#output); what an interrupt does to one, in [Exit codes](cli-spec.md#exit-codes); that `--config` doesn't move the hooks file; and, in Not included, that nothing skips hooks for one command.
- **The skill:** report `hook-failed` and `hook-timeout` to the user, never run the command again for one, and never write `hooks.json` unasked.
- **README:** a Hooks section, with the file's location and the example.
- **[hooks-impl-spec.md](hooks-impl-spec.md):** where each part goes in the code, the tests, and the order it is built in.
