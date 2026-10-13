# shingi hooks: implementation

How [hooks](hooks-spec.md) are built into shingi's code: what goes where, in what order, and the test that proves each rule. The behaviour is the hooks spec's and [operations.md](operations.md)'s; nothing here changes it. Where this document and those disagree, they are right.

## Shape

One new module, and a few lines in three that exist.

| File | Change |
|---|---|
| `src/shingi/hooks.py` | New. Finds and checks the hooks file (`load`), and runs an event's hooks (`run`). |
| `src/shingi/envelope.py` | Gains `decode`, strict JSON, beside `encode`. |
| `src/shingi/cli.py` | `read_input` uses `envelope.decode`; its `no_duplicate_keys` and `not_json` move there. |
| `src/shingi/operations.py` | `make_unit` and `delete` call `hooks.load` after the rules and `hooks.run` last. `delete` sorts its warnings. |
| `tests/support.py` | Gains the hooks file's path and helpers to write it and a hook. |
| `tests/test_hooks.py`, `tests/test_hooks_file.py` | New. |
| `pyproject.toml` | `version` becomes `0.3.0`, in the last slice. |

`hooks.py` imports `rules`, `units`, and `envelope`, never `cli` or `operations`: `cli` imports `operations`, which imports `hooks`.

## Strict JSON

`envelope.decode(data)` takes bytes and returns the value, or raises `ValueError` with a reason for people:

- not UTF-8;
- not one JSON value;
- a key repeated in any object (`object_pairs_hook`);
- `NaN`, `Infinity`, or `-Infinity` (`parse_constant`);
- nested too deeply to read (`RecursionError`, which `decode` turns into `ValueError`).

An integer over Python's limit for reading one (about 4,300 digits) is `json.loads`'s own `ValueError`, so it is "not one JSON value" too.

`cli.read_input` keeps its own checks for a byte-order mark and for "not an object", and its `invalid-input` wording, and calls `decode` for the rest. `units.read_manifest` is left as it is.

## The hooks file: `hooks.load()`

Takes no argument: `--config` never reaches it. Returns the hooks by event, `{"create": [Hook, …], …}`, every event present, disabled hooks included so that an index is the file's.

- **Its path** is `rules.default_path().with_name("hooks.json")`.
- **A `Hook`** is a dataclass: `command`, `timeout` (a float, to wait with), `timeout_given` (the number as the file wrote it, to report), `description` (or `None`), `disabled`.
- **No file** (`FileNotFoundError`) is every event empty. Nothing else is.

The checks, each raising at once unless it says otherwise:

| Step | Check | Raises |
|---|---|---|
| 1 | The file opens and reads. Any other `OSError`, a directory among them. | `invalid-hooks`, `unreadable`, with `code` |
| 1 | `envelope.decode` accepts it, and the value is an object. | `invalid-hooks`, `syntax` |
| 2 | `schema` is there and an integer, not a boolean. | `invalid-hooks`, `invalid`, one problem at `/schema` |
| 2 | `schema` is `1`. | `unsupported-format`, as the rules file's, with this file's `path` |
| 3 | Everything else, below, every problem gathered. | `invalid-hooks`, `invalid`, the problems sorted by `field`, as strings |

Step 3's problems, each `{field, reason}`, `field` a JSON Pointer (`~` as `~0`, `/` as `~1` in a key):

- a top-level key but `schema` and `hooks`: at `/<key>`;
- `hooks` not an object: at `/hooks`;
- an event but `create`, `adopt`, `delete`: at `/hooks/<event>`;
- an event's value not an array: at `/hooks/<event>`;
- a hook not an object: at `/hooks/<event>/<n>`, and its fields are not looked at;
- a hook's key but the four: at `/hooks/<event>/<n>/<key>`;
- `command` missing, not a string, empty, or holding a NUL: at `…/command`;
- `timeout` a boolean, not a number, not above `0`, or not finite: at `…/timeout`. `float(value)` is taken inside a `try`: an integer too large for a float raises `OverflowError`, and is "not finite" too. An integer too long for `json.loads` to read at all is `syntax`, as above;
- `description` not a string: at `…/description`;
- `disabled` not a boolean: at `…/disabled`.

`invalid-hooks`'s `details` are built as `rules.invalid` builds `invalid-rules`'s, and its `message` lists the problems the same way.

## Running hooks: `hooks.run(hooks, event, inp, result, warnings, unit)`

Returns the hook warnings, in the order the hooks ran. With no enabled hook for the event it returns `[]` and does nothing else: no temp directory, no signal handler.

1. **Build the payload** once: `{"schema": 1, "tool": "shingi", "version": <package version>, "event", "input": inp, "result", "warnings"}`, as `envelope.encode` writes it, which ends it in a newline. `inp` is the operation's input as it came in; `warnings` are the operation's own, already sorted.
2. **Make a temp directory** (`tempfile.TemporaryDirectory`) and write the payload to `payload.json` in it. Any exception from building the payload, from either, makes every enabled hook `hook-failed`, as one that couldn't be started is (`exit` `None`, `stderr` `""`, the `message` naming `exc.strerror`), and the command succeeds.
3. **Install the signal handlers** (see [Interrupts](#interrupts)).
4. **For each hook, in order, skipping disabled ones,** run it as below, and add its warning if it has one.
5. **Restore the handlers and remove the directory,** in a `finally`.

One hook:

- **Open `payload.json` anew, for reading,** as its stdin: a fresh open file, so each hook reads from the start, whatever an earlier hook, or a process it left behind, did with its own.
- **Open `stderr-<index>` in the temp directory, for writing,** as its stderr.
- **Start it:** `subprocess.Popen(["/bin/sh", "-c", command], stdin=…, stdout=subprocess.DEVNULL, stderr=…, start_new_session=True)`. No `cwd`, no `env`: both are shingi's. `start_new_session` is `setsid`: the hook's process ID is also its process group's and its session's.
- **An exception running one hook,** the `OSError` opening the payload or stderr file or starting it among them, is `hook-failed` with `exit` `None` and `stderr` `""`, its `message` naming `exc.strerror`, or the exception's type and text when it has none.
- **Wait:** `proc.wait(timeout=hook.timeout)`. This waits for the shell to exit, not for its output to close, since no pipe is read.
- **On `subprocess.TimeoutExpired`:** `os.killpg(proc.pid, signal.SIGKILL)`, ignoring `ProcessLookupError`, then `proc.wait()`. It is `hook-timeout` whatever status that wait returns.
- **Otherwise,** a return code of `0` is success and no warning. A positive one is `exit`. A negative one, `-n`, is `exit` `128+n`.
- **The stderr tail:** the file's last 2,048 bytes, decoded as UTF-8 with `errors="replace"`, or `""` when it can't be read back (a hook that removed it).

The warnings are made with `units.warning`: `unit` as given, `ids` empty, `details` as [Warning kinds](operations.md#warning-kinds) lists them, `timeout` being `timeout_given`.

## In the operations

`make_unit` (`create` and `adopt`) and `delete`, each:

- **Loads the hooks** on the line after `rules_file.load(config)`, before any other check. That gives the [precedence](operations.md#precedence): `inputs.check` first, then the rules, then the hooks file.
- **Runs them last,** once its result and its warnings are complete and sorted:

  ```python
  warnings = units.sort_warnings(warnings)
  warnings = units.sort_warnings(warnings + hooks.run(loaded, event, inp, result, warnings, unit=path))
  return result, warnings
  ```

  `sort_warnings` is stable and hook warnings tie on everything but `kind`, so they keep the order they ran in.
- **Runs none on an error:** every failure raises before that line, a `create` whose read-back fails among them.

`make_unit` takes the event from `adopting`. `delete` gains the first `sort_warnings` call, which it lacks today.

## Interrupts

While hooks run, and only then, `hooks.run` handles `SIGINT`, `SIGTERM`, and `SIGHUP` with one handler, except one whose disposition is `SIG_IGN`, which is left ignored, as it is with no hooks:

1. `os.killpg` the running hook's process group with `SIGKILL`, when one is running, ignoring `ProcessLookupError`;
2. set the signal back to `SIG_DFL`;
3. `os.kill(os.getpid(), signum)`, so shingi dies of the same signal, with no envelope.

The running hook's process ID is kept in a variable the handler reads, set right after `Popen` returns and cleared after the wait. While `Popen` runs, the handler only records the signal, and it is acted on, as above, once the process ID is set: a signal that came as the hook started still kills it. The handlers that were there before are put back when the hooks are done, so nothing changes for a command that runs none.

The temp directory is left behind by an interrupt. It holds a payload and a few bytes of stderr, in the system's temp directory.

## Tests

Run against this checkout, not an installed shingi:

```sh
uv run python -m unittest discover -s tests
```

`ShingiTestCase` gains:

- **`self.hooks_file`:** where `hooks.json` is for the test's `HOME` and `XDG_CONFIG_HOME`: `<tmp>/config/shingi/hooks.json` on Linux, `<tmp>/Library/Application Support/shingi/hooks.json` on macOS. The tests' `--config` moves the rules and not this, which is the rule under test.
- **`self.write_hooks(**events)`:** writes `{"schema": 1, "hooks": events}` there.
- **`self.hook(script)`:** writes an executable `sh` script to the temp directory and returns its path, quoted, to use as a `command`.
- **`self.recorder()`:** a hook command that copies its stdin to a file, and that file's path, for reading the payload a hook was given.

Each line is a test. Together they are the hooks spec's rules, with nothing left to judgment about what proves one.

**The hooks file** (`test_hooks_file.py`):

- No hooks file: `create`, `adopt`, and `delete` behave as now, with no warnings.
- Each problem is `invalid-hooks`, `invalid`, with its `field`, and several are reported together, sorted: an unknown top-level key, an unknown event, an unknown hook field, a missing `command`, an empty one, a `timeout` of `0`, of `true`, of `"10"`, and of `1e999`.
- A file that isn't JSON, isn't an object, repeats a key, or holds `NaN` or `Infinity` is `invalid-hooks`, `syntax`.
- A hooks file that is a directory is `invalid-hooks`, `unreadable`, with `code`.
- A `schema` of `2` is `unsupported-format`, with the hooks file's `path`; with other fields wrong too, it is still `unsupported-format`.
- After each of those, nothing was changed: no working folder, and no task.
- A problem in a disabled hook, and in another event's hooks, stops the command.
- With a broken hooks file, `where`, `context`, `list`, `kinds`, and `version` still work.
- A broken rules file and a broken hooks file together are `invalid-rules`; `invalid-input` is first of all; and a broken hooks file comes before `invalid-name`, `unknown-kind`, `unit-exists`, and `not-found`, in `create`, `adopt`, and `delete`.
- A key with a `/` or `~` in it, in a hook as at the top, is escaped in its `field`.
- A file nested too deeply to read is `invalid-hooks`, `syntax`.
- `--config` naming a file elsewhere still runs the hooks at the usual location.

**Running** (`test_hooks.py`):

- `create` gives its hook the payload: the seven fields, `input` as the command line set it, with no `title` when none was given, `result` equal to the envelope's, and one line ending in a newline.
- `create -i` gives the same `input` as the command line does.
- `adopt` and `delete` each fire their own event, with their own `input` and `result`; none fires another's.
- A failed command fires nothing: a `create` that is `unit-exists`, and one that fails part-way, with a `partial`.
- A read fires nothing.
- Hooks run in the file's order; a disabled one is skipped; a failing one doesn't stop the next.
- A hook's stdout never reaches shingi's: stdout is exactly one line.
- Exit `3`, a command not found (`127`), and a hook that kills itself with `SIGKILL` (`137`) are each `hook-failed`, with that `exit`, the command exiting `0` with its `result` unchanged.
- `hook-failed` carries `event`, `index` counting a disabled hook before it, `command`, `description` or `null`, and the last 2,048 bytes of a longer stderr.
- Two failing hooks and a timed-out one sort as [Warnings](operations.md#warnings) says, among a warning of the command's own.
- A hook that never reads stdin doesn't block, given a payload of several megabytes: the payload carries `input`, so `--notes-file -` with notes that long makes one. Its stdin is a regular file, not a pipe.
- A hook runs in the caller's current directory, with shingi's environment.
- A temp directory, a payload, or a hook's stderr file shingi can't make is `hook-failed` for each hook affected, with `exit` `null`, and the command succeeds (in-process, with the failure mocked: no environment makes `tempfile` fail).
- A `delete` with a koan warning of its own and a failing hook has `hook-failed` first in the envelope, and gives its hooks only its own warning.
- Two hooks each read the whole payload.
- A hook that starts a background process without redirecting its output, and exits, returns at once.

**Timeouts:**

- A hook past its timeout is `hook-timeout`, with `timeout` as the file wrote it and its stderr's tail; the command returns within a second of it; and a process the hook started in the background is gone.
- A hook that ignores `SIGTERM` is killed all the same.
- The default is 10 seconds: a hook with no `timeout` that sleeps for 2 isn't killed.

**The session:**

- With shingi run under a pseudo-terminal that is its controlling terminal (`pty.openpty`, the child made a session leader with the terminal as its own), a hook that opens `/dev/tty` is `hook-failed` at once. Without its own session the open succeeds and there is no warning, so the test fails; run with no terminal at all it would pass either way, which is why it makes one.

**Interrupts:**

- shingi sent `SIGTERM` while a hook sleeps dies of `SIGTERM`, prints nothing, and the hook and a process it started are gone; the unit exists.
- The same for `SIGINT` and `SIGHUP`.
- The hook after an interrupted one never ran.
- A signal that was ignored when shingi started is still ignored while a hook runs: shingi finishes, and its envelope is as with no signal.

**By hand:**

- For a unit created with no `title` and no `notes`, the hooks spec's [recipe](hooks-spec.md#by-hand), run as written, makes a payload with the same fields, of the same types, as the one shingi sent; `warnings` is compared by type only.
- The spec's example hook, run on that payload twice, copies the template once and leaves an edited copy alone.

## Slices

Each is one commit that works from end to end, with its tests, and leaves every earlier test passing.

1. **`create` runs a hook.** `envelope.decode`; `hooks.load` through step 2 and `command` alone, with any other hook field an error for now; `hooks.run` without a timeout; the call in `make_unit` for `create`. Tests: the payload, order, stdout, the exits, `stderr`, stdin never read, two hooks reading, the background process, the session.
2. **The whole hooks file.** Step 3 in full, `description`, `disabled`, and `timeout` checked though not yet used. Tests: all of *The hooks file*, and the disabled hook.
3. **Timeouts.** `proc.wait(timeout=…)`, the group kill, `hook-timeout`. Tests: *Timeouts*, and the sorting test.
4. **`adopt` and `delete`.** The event from `adopting`; the two calls in `delete`, and its sort. Tests: their events, and *By hand*.
5. **Interrupts.** The handlers. Tests: *Interrupts*.
6. **Release.** `version` to `0.3.0`; `scripts/smoke.sh` gains a hooks section: a `create` with a hook that fails, checking for `hook-failed` and exit `0`; a broken hooks file stopping `create` with nothing made; and a read ignoring it.

Until slice 3, a hook that never exits hangs the command. That is three commits on a branch, not a release.
