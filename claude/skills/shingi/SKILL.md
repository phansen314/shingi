---
name: shingi
description: Find, create, and coordinate units of work with the shingi CLI — one hierarchy of named units (a story, its branches, a project) mirrored as koan task folders and working folders on disk. Use when the user mentions a unit, a story or ticket key they work under, splitting work into branches or a stack, where a piece of work's notes, folder, or worktree is, starting or finishing a unit, coordinating or spawning workers for one, or shingi by name; and to ask `shingi where` instead of guessing a path.
---

# shingi

`shingi` gives every piece of work one name and one place. A **unit** is a node in a hierarchy — a Jira story, the branches it is split into, a group of related work, a long-lived project — named by its **path**: `HOME-12345/foo-split/1-schema`. The same path names its tasks in koan (its **koan folder**, `/shingi/HOME-12345/foo-split/1-schema`) and its **working folder** on disk (`~/shingi-root/HOME-12345/foo-split/1-schema`). Every command prints **one line of JSON** and nothing else.

Each unit's working folder holds two files: `uow.json`, its manifest (shingi's; never edit it), and `uow.md`, its notes (everyone's). Each unit has a **start task** and a **done task** in koan; its progress is theirs, never stored.

## Before the first command

```sh
shingi version
shingi kinds
```

The tree is always in the same two places: units' working folders under `~/shingi-root`, and their tasks under the koan folder `/shingi`. Nothing needs setting up: the first `create` makes both. The kinds are `group` and `branch` unless the user has written a `shingi.toml` (in `~/.config/shingi/` on Linux, `~/Library/Application Support/shingi/` on macOS) defining their own. **Never write or change `shingi.toml` unasked**; it is the user's. shingi also needs koan, set up and on `PATH`.

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
| 3 or other | Outcome unknown (killed, stdout lost) | Reads and `delete`: rerun. `create`, `adopt`, and `create-batch`: **don't** rerun blind; see [When create fails](#when-create-or-adopt-fails). |

Error kinds worth handling:

- `not-found` — the path isn't a unit; `.error.details.missing` is the first folder on it that isn't one. From `where` with no path: `reason` `no-unit` or `outside-root` (you're not in a unit's working folder). From `adopt`: `reason` `no-folder`, there is nothing at the path to adopt.
- `invalid-name` — a path segment breaks the name rule (below).
- `parent-not-found` — create the parent first.
- `after-not-found` — a unit named in `--after` isn't a unit (`.error.details.after`): create it first.
- `after-lineage` — `--after` names the unit itself or one of its ancestors, which would never let it start. Drop that entry: a unit already waits on its ancestors' start tasks. To wait on work inside the parent, name those sibling units instead.
- `duplicate-path` — two entries of a `create-batch` have the same path, or the same ignoring case (`.error.details.fields`).
- `after-cycle` — a `create-batch`'s own `after`s can never all be met; `.error.details.cycle` is the units it runs through, each waiting on the next. A unit waits on everything under a unit it comes after, so `x` after `y` with `y/c` after `x` is one. Show the user the cycle and ask which `after` to drop.
- `name-taken` — something is already at the name (`.error.details.entry`, `.type`): a folder, a file, or a name differing only in case. A folder of existing work is made a unit with `adopt`, not `create`.
- `unit-exists` — it's already a unit: `shingi where` it.
- `unknown-kind` — `.error.details.defined` lists the kinds there are.
- `invalid-rules`, `unsupported-format` — the user's `shingi.toml` is wrong; report `.error.message` to the user.
- `koan-failed` — koan failed; `.error.details.error` is koan's own error. See [When create fails](#when-create-or-adopt-fails).
- `io`, `internal` — stop and report to the user, quoting `.error.message`.

## Where things are

**Ask shingi; never compose a path yourself.**

```sh
shingi where                                    # the unit the current directory is in
shingi where HOME-12345/foo-split/1-schema      # a unit by its path
```

`where` returns the unit: `path`, `id`, `kind`, `title`, `state` (`not-started`, `started`, `done`), `parent`, `children` (`{path, kind}`), `koan_folder`, `working_folder`, `notes_path`, and `start` and `done`, its two koan tasks (`id`, `readiness`, `created_at`, `completed_at`). Every filesystem path is absolute.

- With no path, `where` works from anywhere in a unit's working folder, working material included. It does **not** work from a worktree: code lives outside the working root, `~/shingi-root`. A unit's notes say where its code is (below).
- **Read the unit's `uow.md` (`notes_path`)** for what it is for, what was decided, and where its code is.

**To start work on a unit, run `shingi context`** (with its path, or from its working folder): one call for everything you need to begin:

```sh
shingi context HOME-12345/foo-split/1-schema
```

`.result.unit` is what `where` returns; `.result.ancestors` is the chain above it, top-level unit first (`path`, `id`, `kind`, `title`), so you know what your piece is for; `.result.notes` and `.result.parent_notes` are its and its parent's `uow.md`, whole; `.result.tasks` is every open task in its own koan folder (`id`, `title`, `readiness`, `blocking`, `tags`, `notes_path`), its start task among them until the unit is begun. `tasks` is `null` when koan failed or the manifest is unusable: the warnings say which. Its output holds two notes files, so it is larger than `where`'s; print it as is.
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

**Order between units: `--after`.** A unit that must wait for another is created `--after` it: its start task is blocked by that unit's done task. Give full paths, comma-separated or with the option repeated; create the units it comes after first:

```sh
shingi create HOME-12345/setup group
shingi create HOME-12345/research group --after HOME-12345/setup
shingi create HOME-12345/implementation group --after HOME-12345/research
shingi create HOME-12345/review group --after HOME-12345/implementation
```

Order carries through the tree, so say it once, at the top: every unit under `implementation` waits on `research`, since a child's start task waits on its parent's; and `review` waits on every one of them, since a parent's done task waits on its children's. A stack's pieces are each `--after` the one before. `adopt` has no `--after`.

**A whole tree at once: `create-batch`.** When the user has agreed to several units, make them in one call instead of one `create` each: the input is `{"units": [...]}`, each entry what `create` takes (`path`, `kind`, and optionally `title`, `notes`, `after`), given with `-i`:

```sh
shingi create-batch -i - <<'EOF' | jq -c 'if .ok then .result.units |= map({path, kind, state}) else . end'
{"units": [
  {"path": "HOME-12345", "kind": "group", "title": "Payment retries", "notes": "Story: retry failed card payments up to three times."},
  {"path": "HOME-12345/setup", "kind": "group"},
  {"path": "HOME-12345/research", "kind": "group", "after": ["HOME-12345/setup"]},
  {"path": "HOME-12345/implementation", "kind": "group", "after": ["HOME-12345/research"]},
  {"path": "HOME-12345/implementation/1-schema", "kind": "branch", "title": "foo: schema changes"},
  {"path": "HOME-12345/implementation/2-model", "kind": "branch", "title": "foo: model", "after": ["HOME-12345/implementation/1-schema"]},
  {"path": "HOME-12345/review", "kind": "group", "after": ["HOME-12345/implementation"]}
]}
EOF
```

- Paths are full, and the entries may be in any order. A parent, or a unit in `after`, is either in the batch or a unit already, so a batch can also add to a story that exists. At most 500 units.
- Everything is checked before anything is made; an error about one entry says which in `.error.details.field` (`/units/3/after/0`, counting from 0).
- **Show the user the whole batch and get a yes before running it.** It asks for permission once, for all of it.
- `.result.units` is every new unit, in path order; shape it with `jq`, as `list`'s.

**Existing work:** a folder that already holds work (drafts, notes) becomes a unit with `adopt`, which keeps everything in it, its `uow.md` included:

```sh
shingi adopt HOME-12345 group              # ~/shingi-root/HOME-12345 already exists
shingi adopt HOME-12345/spike branch --title 'foo: spike'   # --title only used if there's no uow.md
```

`create` refuses a folder that's already there (`name-taken`), so a typo never swallows existing work.

**A unit made by mistake** (a mistyped name, the wrong parent, the wrong kind) is undone with `delete`:

```sh
shingi delete HOME-12345/1-schmea
```

It removes the unit's koan folder with **every task in it, and their notes, for good**, and its `uow.json`; the parent's done task stops waiting on it. The folder, its `uow.md`, and everything else in it stay as a plain folder: `adopt` it again with the right kind, or remove it yourself if the user wants it gone. It refuses a unit with child units (`has-children`: delete those first), and takes a path, never the current directory. If it fails, run it again. **Ask the user before deleting, and say what tasks will be lost** (`koan list --folder <its koan folder>`). Never `delete` a unit whose work was cancelled or finished: that one is finished, below, so its history stays.

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

- **Order across units** is given when the later unit is created, with `create --after` (above). Between units that both exist already, add it by hand: the later unit's start task is blocked by the earlier one's done task (`koan block <later start> --blockers <earlier done>`).
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

**A worker** starts in a worktree, where `shingi` can't find its unit from the current directory and `CLAUDE.md` is the repository's. So **spawn a worker with `run shingi context <its path>` in its first prompt**, and what it is asked to do. A worker:

- runs `shingi context <its path>` first, and reads what it returns before doing anything else;
- takes its next task from `koan frontier --folder <its koan folder> --recursive=false`: its own unit's, never a child's;
- stops and says so when that task is its unit's start task: the unit hasn't been begun, and that isn't the worker's call;
- marks no task tagged `shingi` but its own unit's done task, and that only when asked to finish the unit;
- records what it decides and learns in its unit's `uow.md`.

### Sessions and units

When sessions are started with sesshin, **tag each one with its unit's path, in its `extra`, under `shingi-path`.** The tag is the link between a session and a unit; the job name is only a short handle.

```sh
sesshin spawn --job 1-schema --extra '{"shingi-path":"HOME-12345/foo-split/1-schema"}' \
  --cwd <the worktree, from the unit's notes> \
  --prompt 'Run shingi context HOME-12345/foo-split/1-schema, then do its next task.'
```

- **Never use the path as the job.** A job can't hold `/`, must be unique among live sessions, and a unit may have several sessions (a worker and a reviewer).
- **The job is the unit's name,** its last segment, when sesshin will take it. Leave `--job` out, and use the sesshin ID it returns, when the name is all digits (`12345` always means a sesshin ID) or the spawn fails `job-taken` (two units share a name, or the unit already has a session).
- **Still put the path in the prompt.** The tag is for finding sessions; the prompt is what the worker reads.
- **A unit's sessions**, live ones:

  ```sh
  sesshin list --fields job,status,extra | jq -c '.result.sessions[] | select(.extra["shingi-path"] == "HOME-12345/foo-split/1-schema")'
  ```

  Every session under a unit: `select((.extra["shingi-path"] // "") | startswith("HOME-12345/"))`.
- **A session that doesn't know its unit** asks sesshin: `sesshin show self | jq -r '.result.session.extra["shingi-path"] // empty'`, then `shingi context` on what that prints. Nothing printed means it was never tagged: ask the user.
- **Tag a session started by hand,** or one that moves to another unit, from inside it: `sesshin update self --extra-merge '{"shingi-path":"HOME-12345/research"}'`.

The key is `shingi-path`, never `shingi-unit`: on a koan task, `shingi-unit` is the unit's `id`, a different thing.

## When create or adopt fails

`create` and `adopt` never resume. An error with **`.error.partial`** stopped after making something, before the unit existed; `partial` lists what was made: `koan_folders`, `tasks`, `blocked` (the blocker added to the parent's done task), `files`. **Undo it, then run the command again**:

1. `koan delete <id>` for each of `partial.tasks` (this also takes the done task out of the parent's blockers);
2. `koan delete-folder <folder>` for each of `partial.koan_folders`, innermost first;
3. remove each of `partial.files`, `uow.md` first.

**A cycle is not run again.** After `create --after` or a `create-batch`, a `koan-failed` whose `.error.details.error.kind` is `conflict` and `.rule` is `cycle` means a unit named in an `after` itself waits on the new unit's parent or another ancestor that already exists, so the new unit could never start. Undo the partial, tell the user, and don't run it again with that `after`: `.error.details.error.ids` are the tasks in the cycle, and `koan show` on them says which unit it runs through.

**A `create-batch` that fails part-way may have finished some units.** Its `partial` has one more list, `units`: the units that exist. **Keep them**; everything else in `partial` belongs to the units that were not made, and `blocked` is a list, one entry for each existing parent whose done task got new blockers. Undo it in fewer calls than one per task: `koan delete-folder -r <folder>` for each of `partial.koan_folders` that isn't inside another listed, which removes the tasks in it; `koan delete <id>` for each of `partial.tasks` still there (`koan show <id>` says); then remove each of `partial.files`, last first. Then run `create-batch` again **without the entries whose paths are in `partial.units`**. Their parents, and the units they come after, exist now, so the rest link to them.

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
| `after-unlinked` | The done task of a unit named in `--after` (`.details.after`) wasn't found, so the new unit doesn't wait on it. | Tell the user; the link can be added by hand with `koan block`. |
| `koan-failed`, `koan-warning` | koan failed, or warned (`.details`); tasks may be `null` or missing. | Tell the user; check koan (`koan info`, `koan doctor`). |

## Moving and removing units

There are no commands for these yet. **Only with the user's go-ahead**, naming what changes:

- **Move**: `koan move-folder <old koan folder> --to <new>`, `mv` the working folder to the same new path, then `koan update <id> --title 'Start: <new path>'` (and `Done: …`) for the start and done tasks of it and every unit under it.
- **Remove**: `koan delete-folder -r <koan folder>` (which also unblocks its parent's done task), then remove the working folder, then undo whatever its setup made (its worktree and branch).

## Hard rules

- **Never create, edit, rename, or delete a `uow.json`.** It is shingi's. Edit `uow.md` freely: it is everyone's, and its first line, `# <title>`, is the unit's title.
- **Never compose a unit's koan folder or working folder** from the roots and the path: ask `shingi where`.
- **Don't create or adopt units the user didn't ask for**; propose them. Both ask for permission anyway.
- **Never `delete` a unit unasked,** and never one whose work was done or cancelled: finish that one instead.
- **Never mark a start task done unless asked to begin that unit, nor a parent's done task unless the user agrees to close it.**
- **Don't put anything under `~/shingi-root` but units and their working material**: never a repository checkout. Code lives in worktrees elsewhere, named in `## Code`.
