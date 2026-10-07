---
name: shingi
description: Find, create, and coordinate units of work with the shingi CLI — one hierarchy of named units (a story, its branches, a project) mirrored as koan task folders and working folders on disk. Use when the user mentions a unit, a story or ticket key they work under, splitting work into branches or a stack, where a piece of work's notes, folder, or worktree is, starting or finishing a unit, coordinating or spawning workers for one, or shingi by name; and to ask `shingi where` instead of guessing a path.
---

# shingi

`shingi` gives every piece of work one name and one place. A **unit** is a node in a hierarchy — a Jira story, the branches it is split into, a group of related work, a long-lived project — named by its **path**: `HOME-12345/foo-split/1-schema`. The same path names its tasks in koan (its **koan folder**, under the koan root, e.g. `/work/HOME-12345/foo-split/1-schema`) and its **working folder** on disk (under the working root, e.g. `~/work/HOME-12345/foo-split/1-schema`). Every command prints **one line of JSON** and nothing else.

Each unit's working folder holds two files: `uow.json`, its manifest (shingi's; never edit it), and `uow.md`, its notes (everyone's). Each unit has a **start task** and a **done task** in koan; its progress is theirs, never stored.

## Before the first command

```sh
shingi version
shingi kinds
```

`kinds` failing with `invalid-rules` (`.error.details.reason: "missing"`) means shingi isn't set up on this machine: tell the user it needs `shingi.toml` in its config directory (`~/.config/shingi/` on Linux, `~/Library/Application Support/shingi/` on macOS), naming a koan root, a working root, and the kinds, as in the README. **Never write or change `shingi.toml` unasked**; it is the user's. shingi also needs koan, set up and on `PATH`.

## Reading output

Every command writes one envelope:

- success: `{"ok":true,"result":{…},"warnings":[…]}`
- failure: `{"ok":false,"error":{"kind":"…","message":"…","details":{…}},"warnings":[…]}`

Branch on `.error.kind`, not the exit code. **Always tell the user about any `warnings`**: each names the unit it is about in `.unit` and is never guessed past.

| Exit | Meaning | What to do |
|---|---|---|
| 0 | Success, with or without warnings | — |
| 1 | Operation error; see `.error.kind` | See below |
| 2 | Usage error (bad command line) | Fix the command |
| 3 or other | Outcome unknown (killed, stdout lost) | Reads: rerun. `create` and `adopt`: **don't** rerun blind; see [When create fails](#when-create-or-adopt-fails). |

Error kinds worth handling:

- `not-found` — the path isn't a unit; `.error.details.missing` is the first folder on it that isn't one. From `where` with no path: `reason` `no-unit` or `outside-root` (you're not in a unit's working folder). From `adopt`: `reason` `no-folder`, there is nothing at the path to adopt.
- `invalid-name` — a path segment breaks the name rule (below).
- `parent-not-found` — create the parent first.
- `name-taken` — something is already at the name (`.error.details.entry`, `.type`): a folder, a file, or a name differing only in case. A folder of existing work is made a unit with `adopt`, not `create`.
- `unit-exists` — it's already a unit: `shingi where` it.
- `unknown-kind` — `.error.details.defined` lists the kinds there are.
- `invalid-rules`, `unsupported-format` — `shingi.toml` is missing or wrong; report `.error.message` to the user.
- `koan-failed` — koan failed; `.error.details.error` is koan's own error. See [When create fails](#when-create-or-adopt-fails).
- `io`, `internal` — stop and report to the user, quoting `.error.message`.

## Where things are

**Ask shingi; never compose a path yourself.**

```sh
shingi where                                    # the unit the current directory is in
shingi where HOME-12345/foo-split/1-schema      # a unit by its path
```

`where` returns the unit: `path`, `id`, `kind`, `title`, `state` (`not-started`, `started`, `done`), `parent`, `children` (`{path, kind}`), `koan_folder`, `working_folder`, `notes_path`, and `start` and `done`, its two koan tasks (`id`, `readiness`, `created_at`, `completed_at`). Every filesystem path is absolute.

- With no path, `where` works from anywhere in a unit's working folder, working material included. It does **not** work from a worktree: code lives outside the working root. A unit's notes say where its code is (below).
- **Read the unit's `uow.md` (`notes_path`)** for what it is for, what was decided, and where its code is.
- Paths are exact and case-sensitive: `HOME-12345`, not `home-12345`; no leading or trailing `/`.

The whole tree, or one subtree, in one call:

```sh
shingi list | jq -c 'if .ok then .result.units |= map({path, kind, state, title}) else . end'
shingi list HOME-12345 | jq -c 'if .ok then .result.units |= map(select(.state != "done") | {path, state}) else . end'
```

A unit in `list` is ~700 bytes, so **shape `list` with `jq`** as above, keeping `ok`, `error` and `warnings`; `where` is small: print it as is. `list`'s units are in path order, each unit's descendants right after it.

## Creating units

`create` never asks anything; asking is your job. **Don't create units the user didn't ask for**; propose them. To create:

1. `shingi kinds` for the kinds there are. A kind's `suggests` lists the kinds it usually holds: propose those first. The usual two are `group` (work gathered under one name: a story, an epic, a project, a research phase) and `branch` (work on one branch of one repository).
2. Propose names and kinds to the user; confirm before creating. Names are letters, digits, and `-`, at most 64, not starting or ending with `-`; a whole path is at most 193 characters. A Jira key is a fine name (`HOME-12345`); so is a short slug (`foo-split`, `1-schema`). Number a stack's pieces in order (`1-schema`, `2-model`).
3. One `create` per unit, **parent first**:

```sh
shingi create HOME-12345 group --title 'Payment retries' --notes-file - <<'EOF'
Story: retry failed card payments up to three times.
Jira: https://jira.example.com/browse/HOME-12345
EOF
shingi create HOME-12345/foo-split group --title 'foo: seven stacked MRs'
shingi create HOME-12345/foo-split/1-schema branch --title 'foo: schema changes'
```

`--title` is one line (default: the name). `--notes` for a line or two, `--notes-file -` with a quoted heredoc for more. `create` makes the koan folder, the start and done tasks (linked to the parent's: the start task waits on the parent's start task, and the parent's done task waits on the new done task), the working folder, `uow.md`, and the manifest. `.result.unit` is the new unit.

**Existing work:** a folder that already holds work (drafts, notes) becomes a unit with `adopt`, which keeps everything in it, its `uow.md` included:

```sh
shingi adopt HOME-12345 group              # ~/work/HOME-12345 already exists
shingi adopt HOME-12345/spike branch --title 'foo: spike'   # --title only used if there's no uow.md
```

`create` refuses a folder that's already there (`name-taken`), so a typo never swallows existing work.

4. **Add the unit's other tasks,** wired to its start and done tasks (below). A `branch` gets a setup task.

## A unit's tasks

shingi makes only the start and done tasks. **Every other task in a unit goes in its koan folder, is blocked by its start task, and blocks its done task.** So nothing in a unit is ready until someone begins it, and the unit can't close while work is open:

```sh
u=$(shingi where HOME-12345/foo-split/1-schema)
folder=$(jq -r .result.koan_folder <<<"$u"); start=$(jq .result.start.id <<<"$u"); done=$(jq .result.done.id <<<"$u")
out=$(koan create-batch -i - <<EOF
{"folder": "$folder", "tasks": [
  {"ref": "setup", "title": "Set up: choose branch, make worktree", "blocked_by": [$start]},
  {"ref": "work", "title": "Schema changes", "blocked_by": ["setup"]},
  {"ref": "review", "title": "Open MR and get review", "blocked_by": ["work"]}
]}
EOF
); echo "$out"
koan block "$done" --blockers "$(jq -r '.result.ids | join(",")' <<<"$out")"
```

- **Order across units** is ordinary blocking: a stack's next piece has its start task blocked by the previous piece's done task (`koan block <next start> --blockers <previous done>`); likewise for a unit that needs another's API change.
- **Never tag your tasks `shingi`, `shingi-start`, or `shingi-done`**, and never set `extra.source` or `extra.shingi-unit` on them: those mark the start and done tasks, and anything else carrying them shows up as an `orphan-task`.

## Setting a unit up: `## Code`

A `branch` unit's setup task decides where its code is: the repository, the branch name (propose a slug, e.g. the path joined with `-`: `HOME-12345-foo-1-schema`, and let the user confirm), the base, and a worktree. Make the worktree with git, then **record it in the unit's `uow.md` under `## Code`, in exactly this form**:

```markdown
## Code

Repository: foo
Branch: HOME-12345-foo-1-schema
Base: origin/main
Worktree: /home/you/repos/foo/.claude/worktrees/HOME-12345-foo-1-schema
```

- One `## Code` section, its first lines these four, each `Key: value`, in this order: `Repository` (the repository's name, as its clone's folder is called), `Branch`, `Base` (what it branches from: `origin/main`, or the previous piece's branch in a stack), `Worktree` (absolute path). Prose may follow after a blank line.
- Every coordinator finds a unit's code here, so keep the form exact, and update it when the branch or worktree changes.
- A unit with no code has no `## Code` section. A `group` normally has none; its branches do.

## Starting and finishing

A unit's `state` comes from its two tasks: `not-started` until its start task is done, `started` until its done task is done, then `done`.

- **Begin a unit** by marking its start task done: `koan done <start id>`. Only when the user (or the coordinator you are working for) says to begin it.
- **Finish a unit** by marking its done task done, once its work is done. Cancelled is the same, with the reason in the done task's notes (`koan show <done id>` gives `notes_path`).
- **A parent's done task becomes ready when its last child is done.** Closing it is a decision, never a side effect: offer it to the user rather than doing it.
- Ready to begin, or to close, under a unit:

```sh
koan frontier --folder <koan folder> --tags-all shingi-start --limit 20 --fields id,title,folder   # units ready to begin
koan frontier --folder <koan folder> --tags-all shingi-done --limit 20 --fields id,title,folder    # units ready to close
```

## Coordinating

**A coordinator** starts in a parent unit's working folder, `shingi where` for itself and `shingi list <its path>` for the picture: each unit's state, koan folder, and notes, whose `## Code` names the worktree to start a worker in. Its decisions are the shingi tasks on its frontier (`koan frontier --folder <its koan folder> --tags-all shingi --limit 20 --fields id,title,folder`): units ready to begin, and units ready to close. Closing a parent whose children are all done is its job.

**A worker** starts in a worktree, where `shingi where` can't find its unit and `CLAUDE.md` is the repository's. So **spawn a worker with its unit's `shingi where` facts in its first prompt** (path, koan folder, notes path, done task ID), and what it is asked to do. A worker:

- takes its next task from `koan frontier --folder <its koan folder> --recursive=false`: its own unit's, never a child's;
- stops and says so when that task is its unit's start task: the unit hasn't been begun, and that isn't the worker's call;
- marks no task tagged `shingi` but its own unit's done task, and that only when asked to finish the unit;
- records what it decides and learns in its unit's `uow.md`.

## When create or adopt fails

`create` and `adopt` never resume. An error with **`.error.partial`** stopped after making something, before the unit existed; `partial` lists what was made: `koan_folders`, `tasks`, `blocked` (the blocker added to the parent's done task), `files`. **Undo it, then run the command again**:

1. `koan delete <id>` for each of `partial.tasks` (this also takes the done task out of the parent's blockers);
2. `koan delete-folder <folder>` for each of `partial.koan_folders`, innermost first;
3. remove each of `partial.files`, `uow.md` first.

Tell the user what you're undoing before you do it. A `koan-failed` with `.error.details.error` `null`, or exit 3 or a signal, means the outcome is unknown: more may have been made than `partial` lists. Run `shingi list <parent>` (or `shingi list` for a top-level path): a unit at the path means it succeeded; an `orphan-task` whose `.details.folder` is the path's koan folder is what it left, to delete before trying again.

## Warnings, and what to do

| Kind | Means | Do |
|---|---|---|
| `orphan-task` | A start or done task matches no unit: left by a failed `create`, a removed working folder, or a moved task. `.details.folder`, `.ids`. | Tell the user; offer to delete it only once they confirm what it is. |
| `missing-task` | A unit's start or done task isn't in its koan folder (`.details.role`): a copied folder, a deleted task, or a half-done move. | Tell the user. A copied unit isn't a unit: `create` is how units are made. |
| `unsupported-manifest` | A `uow.json` can't be used (`.details.reason`); `id` and `kind` are `null`. Its tasks show as `orphan-task`. | Tell the user. Never edit `uow.json` to fix it. |
| `undefined-kind` | A unit's kind is no longer in `shingi.toml`. | Tell the user; the rules or the unit is theirs to fix. |
| `parent-done` | The parent's done task was already done, so the new unit doesn't block it. | Tell the user: they may want to `koan reopen` the parent's done task and block it on the new one. |
| `parent-unlinked` | The parent's start or done task wasn't found, so that link was left out. | Tell the user; the link can be added by hand with `koan block`. |
| `koan-failed`, `koan-warning` | koan failed, or warned (`.details`); tasks may be `null` or missing. | Tell the user; check koan (`koan info`, `koan doctor`). |

## Moving and removing units

There are no commands for these yet. **Only with the user's go-ahead**, naming what changes:

- **Move**: `koan move-folder <old koan folder> --to <new>`, `mv` the working folder to the same new path, then `koan update <id> --title 'Start: <new path>'` (and `Done: …`) for the start and done tasks of it and every unit under it.
- **Remove**: `koan delete-folder -r <koan folder>` (which also unblocks its parent's done task), then remove the working folder, then undo whatever its setup made (its worktree and branch).

## Hard rules

- **Never create, edit, rename, or delete a `uow.json`.** It is shingi's. Edit `uow.md` freely: it is everyone's, and its first line, `# <title>`, is the unit's title.
- **Never compose a unit's koan folder or working folder** from the roots and the path: ask `shingi where`.
- **Don't create or adopt units the user didn't ask for**; propose them. Both ask for permission anyway.
- **Never mark a start task done unless asked to begin that unit, nor a parent's done task unless the user agrees to close it.**
- **Don't put anything under the working root but units and their working material**: never a repository checkout. Code lives in worktrees elsewhere, named in `## Code`.
