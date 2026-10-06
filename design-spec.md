# shingi design spec

## Goals

Give every piece of work on this machine one name and one place. A **unit of work** is a node in a hierarchy — a Jira story, the branches it is split into, a group of related work, a long-lived project — and its path names its tasks in koan and its working folder on disk at once. shingi records each unit in a small manifest beside a notes file, creates units in place with a start and a done task in koan, and tells you or your agent where everything for one of them lives.

- **One hierarchy, mirrored.** A unit's path is the same under every root: the koan root holds its tasks, the working root its working material. Nesting is the hierarchy; nothing else records it.
- **One shape for every unit.** Every unit has the same two files: `uow.json`, the facts tools rely on, and `uow.md`, its notes; and every manifest has the same fields. What differs between a story and a branch is its *kind*, a label. Once a unit exists, every command treats every kind alike.
- **Store only what can't be derived, and stays true.** A unit's name, parent, children, and folders follow from where its manifest sits; when it was started and finished, from its tasks in koan. The manifest holds only its format version, the unit's identity, and its kind, the label chosen when it was made; all three are written once and never updated.
- **shingi makes the structure, not the work.** `create` makes a unit's folders, its two files, and its start and done tasks, and nothing else. Its other tasks — setting it up, doing it, reviewing it — are added by a front end, an agent, or a person. Running the work, tracking it, and finishing it are other tools' jobs.
- **Refuse only at `create`; after that, tell.** `create` refuses only what would make a new unit wrong from the start — a name koan or a sibling rules out, a missing parent, a kind the rules don't define — and never how units nest: any kind may hold any kind. After that, `where` and `list` warn about what they find and fix nothing. Fixing is for a person or an agent, and cheap when someone notices.
- **Follow koan.** Wherever shingi and koan meet — names, the output envelope, exit codes, file formats, the config location, format versions — shingi does what koan does, so one habit covers both, and koan's specs give the detail this one leaves out.

shingi is one command, `shingi`: a Python 3.11+ package with no dependencies outside the standard library (see [Installing](#installing)). Its commands are [`where`](#where), [`list`](#list), [`create`](#create), [`kinds`](#kinds-1), and [`version`](#version).

## How shingi fits

shingi is one building block among several, each owning one thing and talking to the others only through a CLI, JSON, or a file anyone can read:

| Block | Owns |
|---|---|
| **shingi** | Structure and identity: paths, folders, `id`, start and done tasks. |
| **koan** | Tasks, their dependencies, and time: when anything was made, started, and done. |
| **sesshin** | Sessions: starting and watching them. |
| **Post-create hooks** ([future work](#post-create-hooks)) | What a kind or a machine needs set up: worktrees, setup tasks, templates. Work and home differ here without shingi knowing. |
| **`uow.md`** | What was decided and learned about a unit, readable by any person or agent. |
| **ino** (later) | Coordination: reads `shingi list` for the shape and progress of the work and each unit's `uow.md` for its details, then hands work out through koan and sesshin. |

Two boundaries keep the blocks apart:

- **A hook stays a plugin.** What a hook does that proves useful on every machine becomes a shared hook, not a shingi feature. shingi grows only where every unit, of every kind, on every machine, needs the same thing.
- **A section of `uow.md` that a tool reads is a format.** While only people and agents read `uow.md`, prose is enough. Once ino or a hook depends on a section, that section is written down as a format in the skill, or the fact moves to [machine-readable facts](#machine-readable-facts). No tool parses prose and hopes. `## Code`, where a unit's code is, is a format from the start, since every coordinator reads it to find a worktree; the skill defines it, not this spec (see [The notes file](#the-notes-file)).

## Non-goals

- **Tracking progress or completion.** A unit stores no status; its state is derived from its start and done tasks in koan (see [Start and done tasks](#start-and-done-tasks)).
- **Setting up the work.** shingi runs no git and knows no repository. Which repository a unit works in, what its branch is called, and where its worktree is are decided by the unit's setup tasks, which shingi doesn't make, and recorded in its notes.
- **Running sessions.** sesshin starts and watches them, and ino or you name them; shingi only says where a unit's folders are.
- **Moving, renaming, or deleting units.** By hand for now; see [Moving and removing units](#moving-and-removing-units).
- **Knowing what a name means.** A name is only a name: a Jira key, a ticket number, or a slug are all the same to shingi, which infers nothing from one. What a name refers to comes from outside shingi.
- **Talking to Jira or any other tracker.**
- **More than one user, or more than one machine.** Each machine has its own rules and roots. Work and home are separate machines, with separate trees.
- **Windows.** As for koan and sesshin.

## Assumptions

shingi is designed for a user who has bought in: one who works through shingi, koan, and sesshin, and their agents, and keeps to the assumptions below. Its specs, and reviews of them, hold the design to that user, not to one who breaks them: a case that needs an assumption broken is outside the contract, and gets no warning, check, or rule of its own until real use shows it matters. shingi is built to be used now and improved from what use teaches.

- **shingi owns both its roots.** The working root holds units and their scratch material, nothing else: never a repository's checkout, whose code lives elsewhere and is only pointed to (see [The notes file](#the-notes-file)). It may be a git repository of its own. The koan root is a koan folder nothing but shingi uses.
- **shingi is the only writer of `uow.json`, and koan of its task files.** A change made another way is an *outside change*, outside the contract: shingi warns about what it trips over and never crashes on one, but doesn't set out to explain it. shingi, koan, and sesshin all say so: edit the `.md` files, never the `.json`.
- **`uow.md` is everyone's:** you, your agents, and any editor change it freely. It carries nothing shingi depends on but its title (see [The notes file](#the-notes-file)).
- **koan is installed,** on `PATH`, and shingi talks to it through its CLI only, never its files, and knows only koan folder paths, never where koan's tree is on disk.
- **The working root is on a local filesystem,** so hard links and exclusive file creation behave as specified.
- **Hidden entries are ignored.** Any entry under the working root whose name starts with `.` is skipped by every walk.
- **Start and done tasks are threaded into the work.** Front ends, hooks, and agents wire every other task in a unit between its start and done tasks (see [Start and done tasks](#start-and-done-tasks)), so a unit's tasks are begun and finished in order. koan allows marking any task done at any time; shingi tells what it finds, and isn't designed around it.

## Supported platforms

Linux and macOS, on amd64 and arm64, as koan and sesshin.

### Installing

shingi needs Python 3.11 or later, for `tomllib`, and is installed into its own environment with `uv tool install` or `pipx install`, from a clone or the repository. macOS's system Python is too old: use one from uv, Homebrew, or python.org. Either tool puts `shingi` in `~/.local/bin`, which must be on `PATH` (`uv tool update-shell` or `pipx ensurepath`), and pins it to the Python it was installed with: if that Python is removed or upgraded away, `shingi` stops running until it is reinstalled (`uv tool install --reinstall`, `pipx reinstall shingi`). uv and pipx are needed only to install, never to run.

## Terms

| Term | Meaning |
|---|---|
| **unit** | A unit of work: one node of the hierarchy, recorded by a `uow.json` (see [The manifest](#the-manifest)). |
| **path** | A unit's place in the hierarchy, its names joined by `/`: `HOME-12345/foo-1-schema`. Relative; never starts with `/`. |
| **path order** | Paths compared segment by segment, each segment by its bytes, so every unit's descendants follow it directly: `a`, `a/c`, `a-b`. |
| **name** | The last segment of a path: the unit's own folder name. |
| **parent**, **children** | The unit whose folder holds this one's, and the units whose folders this one holds. Derived from the nesting. |
| **top-level unit** | A unit whose folder sits directly in the working root. |
| **id** | A unit's identity: a random UUID in its manifest, carried by its start and done tasks (see [Names and identity](#names-and-identity)). |
| **kind** | A label for what a unit is: `group`, `branch`, or any other the rules define (see [Kinds](#kinds)). |
| **roots** | The two places the rules name: the koan root, a koan folder path, and the working root, a directory (see [The rules file](#the-rules-file)). |
| **koan folder** | A unit's folder in koan's tree: the koan root plus its path. |
| **working folder** | A unit's folder on disk: the working root plus its path. Holds its `uow.json`, its `uow.md`, and any other working material. |
| **manifest** | A unit's `uow.json`: its identity and kind, written by shingi. |
| **notes** | A unit's `uow.md`: its title and running notes, written by anyone. |
| **start task**, **done task** | The two koan tasks `create` makes for a unit (see [Start and done tasks](#start-and-done-tasks)). |

## Locations

| What | Where |
|---|---|
| The rules | `shingi.toml` in shingi's config directory, found as koan and sesshin find theirs: on Linux, `$XDG_CONFIG_HOME/shingi` when `XDG_CONFIG_HOME` is an absolute path, otherwise `~/.config/shingi`; on macOS, `~/Library/Application Support/shingi`. |
| A unit's tasks | Its koan folder: the koan root plus its path. |
| A unit's manifest, notes, and working material | Its working folder: the working root plus its path. |
| A unit's code | Wherever its setup tasks put it, as recorded in its notes. shingi doesn't know. |

No shingi environment variable sets a location or a rule — only the platform's own config location, as for koan: a harness's environment is whatever started it, so a setting there could reach one process and not another. `--config <file>` overrides the rules file for one command, for tests and trials.

## The rules file

### Example

```toml
schema = 1

[roots]
koan    = "/work"
working = "~/work"

[kind.group]
description = "Work gathered under one name: a project, a story, an epic, a research phase."
suggests    = ["group", "branch"]

[kind.branch]
description = "Work on one branch of one repository."
suggests    = []
```

### Fields

| Field | Type | Meaning |
|---|---|---|
| `schema` | integer | The file's format version (see [Format versions](#format-versions)). Required. |
| `roots.koan` | string | The koan root: a koan folder path, absolute. A folder only shingi uses, such as `/work` (see [Assumptions](#assumptions)). Required. |
| `roots.working` | string | The working root. A leading `~/` is the home directory; otherwise absolute. Must be an existing directory: shingi never makes it. Required. |
| `kind.<name>` | table | Defines a kind. `<name>` is lowercase ASCII letters, digits, and `-`, as a koan tag. At least one kind is required. |
| `kind.<name>.description` | string | What the kind is for, one line, for [`kinds`](#kinds-1) to report. Optional. |
| `kind.<name>.suggests` | array of strings | The kinds a unit of this kind usually holds, for a front end to propose first. Each names a defined kind. Optional; default `[]`. |

Unknown fields are an error, not ignored, so a typo says so instead of silently doing nothing. Any error in the rules file, a missing working root among them, is an error for every command but `version`, which doesn't read it. A missing rules file is `invalid-rules` too, and its message points to the example above, which the [skill](#claude-code) and the README carry; there is no `init`.

## The hierarchy

- **A unit is a folder with a manifest.** A folder under the working root is a unit exactly when it holds a `uow.json`.
- **Units nest only in units.** A unit's folder sits directly in the working root (a top-level unit) or directly in another unit's folder (its parent). A manifest anywhere else — in a plain folder, or deeper inside a unit's working material — is not a unit, and no walk finds it.
- **Walks follow manifests.** A walk looks only in the working root and in units' folders, and goes no deeper than a folder with no `uow.json`: that branch of the walk stops there. So a unit's working material, however large, is never walked.
- **Children are found, never listed.** A parent records nothing about its children: they are the folders directly in its folder that hold a manifest.
- **The path is mirrored.** A unit's koan folder and working folder are its path under the koan root and the working root. Both trees show the same hierarchy, but the working tree decides it: a unit exists when its manifest does, and its koan folder follows.
- **A unit's koan folder holds only its own tasks and its children's folders.** There are no phase folders or other special folders. Anything phase-like is a child unit (a `group` named `research`), so a name can only collide with a sibling, which the filesystem already prevents. Beyond the tasks `create` makes, how a unit's tasks are arranged is up to you.
- **A unit's working folder is its own.** Beyond its [notes](#the-notes-file), the people and agents doing the work are encouraged to add whatever files and folders the work needs — drafts, graphs, captured logs, a `docs/` — with no names reserved and no layout imposed. Everything in the folder that isn't a child's folder is that unit's working material, and shingi names no files in it but its own two.

### Names

- **A name is a koan folder name:** ASCII letters, digits, and `-`, at most 64 characters, neither starting nor ending with `-`: `HOME-12345`, `foo-1-schema`. The path is a koan folder path too, so a name koan would refuse would break the mirror; and every name this allows is also a valid part of a git branch name and a shell argument, with no quoting.
- **A path is at most 193 characters,** so its start task's title, `Start: <path>`, fits koan's 200. `create` checks this; nothing else needs to.
- **A name means nothing to shingi.** `HOME-12345` may be a Jira key to you; to shingi it is a name, checked only against the rule above.
- **Case is kept, never changed.** A name is stored, shown, and matched exactly as it was given to `create`, in whatever mix of cases it has, and so is everything derived from it: the koan folder and the working folder. shingi never uppercases, lowercases, or folds a name, and matches a path case-sensitively.
- **Names are unique among siblings, ignoring case.** `create` refuses a name that differs only in case from any entry in the parent's folder, whether a unit, a plain folder, or a file ([`name-taken`](#problems)). So a tree means the same on macOS, whose filesystem usually ignores case, as on Linux, whose filesystem doesn't. This is the one place case is compared loosely, and it only ever refuses.

## The manifest

### Fields

Every `uow.json` has the same fields:

| Field | Type | Meaning |
|---|---|---|
| `schema` | integer | The manifest's format version. |
| `id` | string | The unit's identity: a random UUID, lowercase, in its canonical 36-character form, made by `create`. Ties the unit to its [start and done tasks](#start-and-done-tasks) and survives a move (see [Names and identity](#names-and-identity)). |
| `kind` | string | The unit's [kind](#kinds), as named when it was created. |

All fields are required. Unknown fields are an error, as in the rules file.

### Example

`~/work/HOME-12345/foo-1-schema/uow.json`:

```json
{
  "schema": 1,
  "id": "3f6c2a9e-8b1d-4e47-9c05-7a2d41e6b0f3",
  "kind": "branch"
}
```

Beside it, `uow.md`, after the unit's setup task has run:

```markdown
# foo: schema changes

## Code

Repository: foo
Branch: HOME-12345-foo-1-schema
Base: origin/main
Worktree: /home/you/repos/foo/.claude/worktrees/HOME-12345-foo-1-schema
```

### Derived, never stored

| Fact | Derived from |
|---|---|
| Name, path | Where the manifest sits. Renaming a folder can't leave a stale name behind. |
| Parent, children | The nesting. |
| Koan folder, working folder | The roots plus the path. |
| Title | The first non-blank line of `uow.md`, if it is a `# ` heading. |
| When it was created, started, and done | Its start and done tasks in koan (see [Start and done tasks](#start-and-done-tasks)). |
| Where its code is | Nothing shingi reads: its notes say, for people and agents. |

### The notes file

`uow.md` sits beside `uow.json` and is the unit's scratchpad. `create` writes it with the unit's title as its first heading, `# <title>` — `--title`, one line, or the unit's name when none is given — and then, after a blank line, `create`'s `--notes`, if given: whatever a front end or script wants recorded about the unit from the start. After that it belongs to whoever is working: append notes, rewrite it, link out to other files in the folder. A unit's setup tasks record what they decided here, under `## Code`.

- **The title is the first non-blank line, if it starts with `# `.** Only that line is looked at, so a `# ` line further down, in a code block or anywhere else, is never taken for it. A unit whose first non-blank line is something else, or with no `uow.md`, has the empty title, and tools show its path instead. Changing a title is editing that line.
- **`## Code` is the skill's format.** A unit with code says where it is under `## Code`, in the form the [skill](#claude-code) defines — the example above shows it — so every unit's notes say where its code is the same way. shingi neither writes nor reads it, and this spec doesn't define it: the skill is what agents learn it from, and the one place it changes.
- **Nothing in it is read by shingi** but its title.
- **Never replaced.** `create` writes `uow.md` only when there is none, by exclusive create, so a `uow.md` that appears meanwhile is kept, never overwritten.

### File format

`uow.json`, as koan's task files: UTF-8, one JSON object, pretty-printed with two-space indents and a trailing newline. Written once, never replaced: to a hidden temp file in the same folder, flushed, then hard-linked as `uow.json`, which fails if one is already there (see [Concurrency](#concurrency)), and the temp file removed. A reader sees no manifest or a whole one, never part of one. A temp file left by a crash is hidden, so every walk skips it.

## Kinds

A kind is a label for what a unit is, defined in the rules file: context for the people, agents, and front ends reading the tree. shingi does nothing differently for one kind than another: every unit has the same manifest, the same files, and the same start and done tasks, whatever its kind.

- **Configured, not built in.** shingi knows no kind by name. The rules define them, each with a description and the kinds it suggests holding. Adding a kind, or changing one, is an edit to `shingi.toml`, never a change to shingi or to any manifest.
- **Checked at `create`, told after.** `create` refuses a kind the rules don't define ([`unknown-kind`](#problems)), so a typo doesn't become a label. A manifest whose kind is no longer defined — renamed or removed from the rules since — is still a unit: [`where`](#where) and [`list`](#list) read it as usual and warn [`undefined-kind`](#problems).
- **What a kind means in practice is the front end's.** A front end or the skill may add different tasks to a `branch` than to a `group` — a setup task, a review task — by looking at the kind.
- **Suggestions, not rules.** A kind's `suggests` is what a front end proposes first when creating a child. Any kind may hold any kind, and nothing checks the nesting, at `create` or after.

The example rules define two kinds, the shapes that come up most:

- **`group`:** work gathered under one name — a long-lived project; a Jira story or epic, named by its key; a one-off at the top level; story-level research; the seven stacked branches of one large change. What a group is *for* goes in its `uow.md`.
- **`branch`:** work on one branch of one repository. Usually a leaf, and the unit with code to work on: a story split into seven merge requests is a `group` named by its key, holding a `group` of seven `branch` units, plus a `branch` in each other repository it touches. Its setup task, added by the front end or an agent, chooses the repository and branch name — an agent proposing a slug, a person confirming it — makes the worktree, and records them under `## Code` in its `uow.md`.

A stack's order lives where it stays true: in git, which knows each branch's history; in the units' names (`1-schema`, `2-model`); and in koan, where each piece's start task waits on the previous piece's done task.

## Names and identity

A unit is *named* by its path and *identified* by its `id`.

- **People and tools name a unit by its path.** It is unique, since the filesystem allows one folder per name, and readable: `HOME-12345/foo-1-schema` says what it is. Every command takes a path, and ino, later, would hand units out by it.
- **Start and done tasks are tied to a unit by its `id`,** not its path (see [Start and done tasks](#start-and-done-tasks)). The koan folder is where they are looked for; the `id` is how they are recognized there.
- **The `id` is random, not counted.** `create` makes a fresh UUID, so there is no counter, no lock, and no state outside the units themselves.
- **Moving a unit keeps its identity.** Its path changes and its `id` doesn't; moved together with its koan folder, its tasks still match it. Moving is [by hand](#moving-and-removing-units) for now.
- **Copying is not how a unit is made: `create` is.** A copied folder carries its original's `id` but has no tasks in its own koan folder, so it is told as [`missing-task`](#problems).

## Start and done tasks

A unit has no status of its own. Its progress is told by two koan tasks that `create` makes directly in its koan folder, in one `koan create-batch`:

| Task | Tags | `extra` | Title | Blocked by |
|---|---|---|---|---|
| start | `shingi`, `shingi-start` | `{"source": "shingi-start", "shingi-unit": "<id>"}` | `Start: <path>` | the parent's start task, if there is a parent |
| done | `shingi`, `shingi-done` | `{"source": "shingi-done", "shingi-unit": "<id>"}` | `Done: <path>` | its own start task |

and the new done task is added to the blockers of the parent's done task, so a parent's done task isn't ready while a child is open. koan lets any task be marked done at any time, blocked or not, so this is a signal, not a lock.

- **Found by the unit's `id`, never stored.** Every task shingi makes is tagged `shingi`, so one `koan list` narrowed to that tag finds them all, and, as long as nothing else is tagged `shingi`, nothing else. Among them, `extra.source` says the role and `extra.shingi-unit` the unit: a unit's start task is the one in its koan folder whose `source` is `shingi-start` and whose `shingi-unit` is the unit's `id`; its done task, the one whose `source` is `shingi-done`. The manifest records no task IDs.
- **Tagged by role, for the frontier.** koan's `frontier` filters by tag, never by `extra`, so each task also carries its role as a tag: `koan frontier --tags-all shingi-start` is every unit ready to begin, and `--tags-all shingi-done` every unit ready to close. shingi reads only `extra`; the role tags are for people and agents.
- **Looked for in the unit's koan folder, and only there.** Every command that reads tasks runs one `koan list` of tasks tagged `shingi`, done tasks included: `where` of the unit's koan folder alone, and `list` of the koan folder it starts from and everything under it (the koan root, with no argument). A task matches a unit only when it carries the unit's `id` *and* sits in the unit's koan folder, so `where` and `list` always agree. A task carrying a unit's `id` in any other folder matches nothing: `list` warns it as [`orphan-task`](#problems). A koan folder that doesn't exist yet, such as the koan root before the first `create`, holds no tasks.
- **Titles are for people.** shingi writes them, and never reads them: renaming one changes nothing. A title names the unit's path, the one thing in it that can go stale: a unit moved by hand keeps its old titles until its tasks are retitled, as [moving](#moving-and-removing-units) says, and `shingi move` would retitle them itself.
- **Times are koan's.** A unit was created at its start task's `created_at`, started at its start task's `completed_at`, and done at its done task's `completed_at`.
- **The start task is the unit's gate.** Every other task in a unit waits on it, so a unit's tasks stay off the frontier until someone decides to begin it: a stack's next piece, or work specified now for later, waits there unseen. Whoever begins a unit marks its start task done first; whoever finishes it marks its done task. Done covers cancelled; a reason goes in the task's notes.
- **Closing a parent is the coordinator's job.** A parent's done task becomes ready once its last child's done task is done, and shingi closes nothing: whoever coordinates the parent — a person, a coordinator session, later ino — marks it, finding it with `koan frontier --tags-all shingi-done`. In a deep tree that is one close per level, by design: a group done is a decision, not a side effect.
- **Every other task is added and wired by whoever adds it.** shingi makes and links only these two. The convention, taught by the skill: every other task in a unit — its setup task among them — is blocked by its start task and blocks its done task. Nothing checks this.
- **Work order across units is ordinary task dependencies.** A unit in one repository that needs another's API change has its start task blocked by that unit's done task, across repositories or within a stack.

## Commands

Every command prints one line of JSON to stdout, in koan's envelope, and uses koan's exit codes, so one `jq` habit covers koan, sesshin, and shingi. No failure ends in a Python traceback: an unexpected exception is still an envelope, and a closed stdout (`shingi where X | head -c 10`) is koan's exit `3`, not a `BrokenPipeError`. Output is always UTF-8, whatever the locale. Every filesystem path in output is absolute, with `~` expanded: not every harness's file tools expand `~`. [operations.md](operations.md) specifies each command's input, output, and problems in full.

A unit is named on the command line by its path (`HOME-12345/foo-1-schema`), matched exactly (see [Names](#names)).

### Output

**The envelope** is koan's:

```text
{ "ok": true,  "result": { }, "warnings": [ ] }
{ "ok": false, "error":  { "kind", "message", "details", "partial"? }, "warnings": [ ] }
```

`error.kind` and `error.details` are the contract, and `message` is for people. `error.partial` is present only when `create` failed after making something, before the unit existed (see [create](#create)). `warnings` is present, possibly empty, on success and failure alike.

**A warning** is `{ "kind", "message", "unit", "ids", "details" }`: `unit` is the path of the unit it is about, or `null`; `ids` the koan task IDs involved, possibly empty; `details` anything else the kind carries, such as koan's own warning for `koan-warning`, or `{}`.

**A unit** is the same object wherever it appears — `where`'s result, each of `list`'s units, `create`'s result:

```json
{
  "path": "HOME-12345/foo-1-schema",
  "id": "3f6c2a9e-8b1d-4e47-9c05-7a2d41e6b0f3",
  "kind": "branch",
  "title": "foo: schema changes",
  "state": "started",
  "parent": "HOME-12345",
  "children": [],
  "koan_folder": "/work/HOME-12345/foo-1-schema",
  "working_folder": "/home/you/work/HOME-12345/foo-1-schema",
  "notes_path": "/home/you/work/HOME-12345/foo-1-schema/uow.md",
  "start": { "id": 41, "readiness": "done", "created_at": "2026-10-04T09:12:00Z", "completed_at": "2026-10-05T08:30:00Z" },
  "done": { "id": 42, "readiness": "blocked", "created_at": "2026-10-04T09:12:00Z", "completed_at": null }
}
```

| Field | Meaning |
|---|---|
| `path` | The unit's path. |
| `id`, `kind` | From its manifest; `null` when the manifest can't be read. |
| `title` | The `# ` heading on the first non-blank line of its `uow.md`; `""` when there is none (see [The notes file](#the-notes-file)). |
| `state` | Derived from its start and done tasks, never stored: `null` when either task is; otherwise `done` when its done task is done, whatever its start task, since koan lets any task be marked done at any time; otherwise `started` when its start task is done; otherwise `not-started`. |
| `parent` | The parent's path; `null` for a top-level unit. |
| `children` | Each child as `{ "path", "kind" }`, in [path order](#terms). |
| `koan_folder`, `working_folder`, `notes_path` | Where its tasks, its working material, and its notes are. |
| `start`, `done` | Its start and done tasks, as koan reports them: `id`, `readiness`, `created_at`, `completed_at`, with koan's meanings. `null` when the task isn't found, or koan failed (see [Problems](#problems)); more than one, only after an outside change, reports the lowest ID. |

### where

`shingi where [<unit>]` — everything about one unit. `result` is the [unit](#output).

With no unit, `where` names the unit the current directory is in, for an agent that starts with no context: the current directory, resolved like the working root to its real path, is taken as a path under the working root, and its unit is the deepest folder along it reached through units alone — every folder from the working root down to it holds a `uow.json`. A directory inside a unit's working material is in that unit. A current directory outside the working root, or in no unit, is `not-found`. A worktree is outside the working root, so this doesn't work from code; see [Unit from a worktree](#unit-from-a-worktree).

`where` checks that every folder on the path holds a `uow.json`, reads the unit's own files and its children's manifests, and finds its start and done tasks with [one koan call](#start-and-done-tasks). When koan fails, the tasks are `null` and `where` warns [`koan-failed`](#problems), still reporting everything else. Likewise with a manifest it can't read: `id` and `kind` are `null`, its tasks can't be matched and are `null`, and `where` warns [`unsupported-manifest`](#problems), as `list` does — still reporting its folders and notes, which are what fixing it needs. A path that holds no `uow.json` at all is `not-found`.

### list

`shingi list [<unit>]` — a full description of a tree: the unit and every unit beneath it, at any depth, or every unit under the working root when none is given. `result` is `{ "root", "units" }`: `root` is the unit named, or `null`; `units` is every [unit](#output) in the tree, the root among them, as a flat list in [path order](#terms). The tree is in each unit's `parent` and `children`. One call tells a reader where every unit's tasks and notes are, and how far along each is: `jq '.result.units[] | select(.state != "done")'` is what's left.

- **Always current.** `list` walks the tree each time it runs (see [The hierarchy](#the-hierarchy)), and stores nothing, so there is no generated file to fall out of date. A coordinator is told to run it, not to read a file.
- **Any unit can be the root.** `shingi list HOME-12345/foo-split` describes the stack alone.
- **One koan call,** of the koan folder it starts from, finds every unit's start and done tasks (see [Start and done tasks](#start-and-done-tasks)).
- **Problems are warnings, never failures,** so one bad manifest doesn't hide the rest (see [Problems](#problems)). A folder whose `uow.json` can't be read is still a unit: it is listed with what can't be read as `null`, and the walk goes on into its children.

### create

`shingi create <path> <kind> [--title <text>] [--notes <text>]`, or `shingi create -i <file>` with the same input as one JSON object, `{ "path", "kind", "title"?, "notes"? }` — make one unit. `result` is `{ "unit" }`, the new [unit](#output).

1. **Check,** in this order. The path is valid; the kind is defined; the parent (from the path) exists, or the path is a single segment; no entry in the parent's folder has the name in another case, and no file has it exactly; no `uow.json` is there yet. A failed check changes nothing.
2. **Set up koan.** Make the unit's `id`, a fresh UUID. One `koan create-batch` makes the koan folder and the unit's [start and done tasks](#start-and-done-tasks): the start task, blocked by the parent's start task, and the done task, blocked by the start task. Then `koan block` adds the done task to the parent's done task's blockers, unless that task is already done, which is warned as [`parent-done`](#problems) and left alone. The parent's tasks are found by its `id`, as `where` finds them, before anything is made. Each link is made or left out on its own: when the parent's start task, or its done task, can't be found — the parent's `id` is unreadable, or no task carries it — that link is left out and warned as [`parent-unlinked`](#problems), never guessed, and the other is still made.
3. **Write the files.** Make the working folder if there is none, write `uow.md` if there is none, then write the manifest, with its `id`. The unit exists from this moment, and not before.

`create` never resumes. One that fails after making something, before the manifest is written, is an error with `partial`, as koan's multi-file writes are; once the manifest is written the unit exists, and an error after that carries no `partial`:

```json
{ "koan_folders": ["/work/HOME-12345/foo-1-schema"], "tasks": [41, 42], "blocked": { "task": 17, "added": [42] }, "files": ["/home/you/work/HOME-12345/foo-1-schema/uow.md"] }
```

`koan_folders` are the koan folders it made, as koan's `folders_created` reports them, never one that was already there; `tasks`, the tasks it made; `blocked`, the blocker it added to the parent's done task, or `null`; `files`, the files and folders it made, never one that was already there. Cleaning up is undoing what `partial` lists, by an agent or by hand — `koan delete` on each task, which also takes it out of the parent's blockers, then `koan delete-folder` on each koan folder, innermost first, then removing the files — before running `create` again. The [skill](#claude-code) teaches this. A `create` killed before it could report leaves tasks that no manifest claims, which [`list`](#list) warns as [`orphan-task`](#problems); so may a koan call killed in the middle of `create`, whose outcome shingi can't know, so its `partial` may list less than was made.

**Adopting a folder.** A working folder that already exists without a `uow.json` — working material, a folder made by hand, what a failed `create` left — becomes the unit, and everything in it stays as it was, so moving existing work onto shingi is one `create` per folder, parent first. A `uow.md` already there is kept, and `--title` and `--notes` are not written; `create` warns [`notes-kept`](#problems), and the result's `title` is what the kept `uow.md` says. A koan folder that already exists, such as one a failed `create` left, is used as it is.

A unit whose manifest already exists is [`unit-exists`](#problems), and nothing changes. `create` never replaces or removes anything, and makes nothing outside koan and the working root, and no task but the unit's start and done tasks.

### kinds

`shingi kinds` — every kind the rules define, for a front end — a Claude command, an OpenCode command, a pi tool — to offer the right kinds without knowing them itself. `result` is `{ "kinds": [ { "name", "description", "suggests" } ] }`, in name order; `description` is `""` when the rules give none.

### version

`shingi version` — shingi's own version. `result` is `{ "version" }`.

## Problems

Every problem shingi reports, by name. An error means the command changed nothing, except a `create` that failed part-way, whose error lists what it made in `partial` (see [create](#create)); a warning is told, never guessed past, and fixed by a person or an agent. Each kind's `details` are in [operations.md](operations.md#errors).

### Errors

| Kind | Commands | When |
|---|---|---|
| `usage` | all | The command line is malformed: an unknown command or option, a missing or extra argument, `-i` together with arguments. |
| `invalid-input` | all | The input is the wrong shape: `create -i` JSON that isn't an object of the right fields, or a `--title` that is empty or holds a line break. |
| `invalid-rules` | all but `version` | The rules file is missing, unreadable, or breaks [Fields](#fields). |
| `unsupported-format` | all but `version` | The rules file's `schema` is one shingi doesn't support. |
| `not-found` | `where`, `list` | The path named is not a unit: a folder on it doesn't exist, matches only ignoring case, or holds no `uow.json`. Names the first folder on the path that isn't a unit, so a unit cut off by an ancestor's missing manifest says which. From `where` with no unit, the current directory is in no unit, or outside the working root. |
| `invalid-name` | `where`, `list`, `create` | A segment of the path breaks [Names](#names), or, from `create`, the path is over 193 characters. Checked before the path is looked up, so no path reaches outside the working root. |
| `parent-not-found` | `create` | The path has more than one segment, and its parent is not a unit. |
| `name-taken` | `create` | An entry in the parent's folder — a unit, a plain folder, or a file — has the new name in another case, or a file has it exactly. |
| `unknown-kind` | `create` | The kind is not defined in the rules. |
| `unit-exists` | `create` | The unit's `uow.json` already exists. Found by the check, or, in a race, by the manifest's exclusive create (see [Concurrency](#concurrency)). |
| `koan-failed` | `create` | koan could not be run, or returned an error; koan's envelope is in `details`, and what `create` made in `partial`. Undo what `partial` lists, then run `create` again. When koan couldn't report, its outcome is unknown: run `list` for `orphan-task`s before running `create` again. |
| `io` | all but `version` | The filesystem refused: permission denied, disk full, and the like. From `create`, with `partial` when it had made something and the unit doesn't exist yet. |
| `internal` | all | A bug: an unexpected exception, still reported as an envelope; from `create`, with `partial` when it had made something and the unit doesn't exist yet. |

### Warnings

| Kind | Commands | When |
|---|---|---|
| `unsupported-manifest` | `where`, `list` | A unit's `uow.json` has a `schema` shingi doesn't support (see [Format versions](#format-versions)), or, after an outside change, can't be read at all. It is still a unit, with `id` and `kind` `null`; with its `id` unknown, its tasks can't be matched, and `list` shows them as `orphan-task`, which this explains. |
| `undefined-kind` | `where`, `list` | A unit's kind is no longer defined in the rules (see [Kinds](#kinds)). |
| `missing-task` | `where`, `list` | No start task, or no done task, in the unit's koan folder carries its `id`. That task is reported as `null`. |
| `orphan-task` | `list` | A task tagged `shingi`, in the koan folders `list` reads, that matches no unit: its `extra.shingi-unit` names no unit `list` found, or names one whose koan folder it isn't in. Left by a `create` killed before it could report, by a unit whose working folder was removed and whose tasks weren't, or by a task moved out of its unit's koan folder. |
| `parent-done` | `create` | The parent's done task was already done, so the new done task was not added to its blockers. |
| `parent-unlinked` | `create` | The parent's start or done task could not be found — missing, or the parent's `id` unreadable — so the link to it was left out, to be added by hand; a link to the other was still made. |
| `notes-kept` | `create` | The working folder already held a `uow.md`, which was kept, so `--title` and `--notes` were not written. |
| `koan-failed` | `where`, `list` | koan could not be run, or returned an error; every task is `null`, and everything else is still reported. |
| `koan-warning` | `where`, `list`, `create` | A koan call warned, passed on in `details`. An unusable or unreadable task file can hide a start or done task, so while one is present, `missing-task`, `orphan-task`, or `parent-unlinked` may be wrong. |

## Front ends

`create` never asks anything: every answer is an argument. Asking is a front end's job, and the part an agent does best — proposing names for a story's pieces, or how to split one large change into a stack. A front end:

1. reads `shingi kinds` for what to offer, proposing a parent's `suggests` first,
2. asks the person, proposing names where it can,
3. runs one `shingi create` per unit, parent first. Creating a whole tree in one call is [future work](#batch-create-and-tree-templates).
4. adds the unit's other tasks — a `branch`'s setup task, say — wired to its start and done tasks [by convention](#start-and-done-tasks), found with `shingi where`.

A story with seven branches in `foo` and one in `bar` is one `create … group` and eight `create … branch`, each a separate, checkable step — often run by the story's own setup task, once the split is agreed. Each `branch` then sets itself up through the setup task the front end gave it.

## Adapters

### Claude Code

A Claude Code plugin, served from this repository as koan's and sesshin's are, carrying one skill and no hooks. The skill teaches the hierarchy and the kinds; to ask `shingi where` instead of composing a path; the [front-end](#front-ends) steps for creating units; how to do a setup task and where in `uow.md` to record what it decided, so every unit's notes say where its code is in the same form; how to clean up after a `create` that failed, by undoing what its `partial` lists, or after an `orphan-task` warning; and how to coordinate:

- **A coordinator** starts in a parent unit's working folder and runs `shingi list <unit>` for its picture of the work: each unit's koan folder, and its notes for the worktree to start a session in. Its decisions are the shingi tasks on the frontier: `koan frontier --folder <koan folder> --tags-all shingi` is every unit under it ready to begin or to close; closing a parent whose children are all done is its job. The session's job is the coordinator's to choose.
- **A worker** is spawned with its own unit's `shingi where` facts in its first prompt, since it starts in a worktree whose `CLAUDE.md` is the repository's, not the unit's. Its next task is `koan frontier --folder <its koan folder> --recursive=false`: its own unit's, never a child's. When that is its unit's start task, the unit hasn't been begun, and the worker stops and says so rather than marking it. It marks no task tagged `shingi` but its own unit's done task, and that only when it was asked to finish the unit.

A plugin can't grant permissions, so `scripts/install.sh` adds rules letting `where`, `list`, `kinds`, and `version` run without a prompt, while `create`, which changes things, still asks; it backs `settings.json` up first and is safe to rerun.

### OpenCode

The same skill, linked into OpenCode's skills directory as koan's is, and the same permission rules.

## Concurrency

`create` is the only writer of manifests, and takes no lock; koan serializes its own writes. Two `create`s of different paths never touch the same file. Two `create`s of the same path are in no workflow; if they happen, both make tasks, the manifest's exclusive create lets only one write it, and the other fails with `unit-exists`, its `partial` listing the tasks to delete.

## Format versions

`shingi.toml` and every `uow.json` carry `schema`, each versioned on its own. A rules file with a `schema` shingi doesn't support is an error for every command but `version`; an unsupported manifest is a warning from `where` and `list`, which still report the unit (see [Problems](#problems)). Before 1.0, as koan's and sesshin's formats, a schema may change in place: a change bumps shingi's minor version, and its release notes say how to update existing files. Kinds are configuration: adding, changing, or removing one is never a schema change.

## Future work

Grouped by when, not ranked within a group.

### Next

#### Filtering `list`

`shingi list --open`, leaving out every unit that is done. After months of work most of the tree is finished, and a coordinator wants what's left. The data is already in `list`'s one koan call; this only decides what to print.

### Later

#### Batch create and tree templates

`shingi create -i plan.json` taking a whole tree — a story, its groups, every branch — as one input, as `koan create-batch` takes many tasks, so a front end can propose the entire shape for review and build it in one call. A batch that fails part-way would report what it made, unit by unit, as one `create` does, for an agent to undo; and each unit's [post-create hook](#post-create-hooks) would run as if it had been created alone.

A plan file kept and reused is a **tree template**: "a story with a research group, a split group, and one `branch` per repository", with names filled in per use. Templates are files the user keeps, not shingi configuration: shingi only reads the plan it is given.

#### Post-create hooks

A command a kind names in `shingi.toml`, as Claude Code names its hooks, that `create` runs once the unit exists, so a kind can bring its own setup without shingi knowing what it is: a `branch` hook adds a setup task and a review task, wired [by convention](#start-and-done-tasks); another kind's hook copies a template into the working folder. A hook may specify work without doing it: making a unit's tasks now, for an agent to carry out much later.

- **Given the whole context.** The hook gets, as JSON on stdin, the new [unit](#output) and `create`'s own input, and runs in the unit's working folder.
- **After the commit, never part of it.** The unit exists before its hook runs, so a hook that fails leaves a whole unit with less set up, never a half-made one. `create` reports the failure as a warning, `hook-failed`, with the hook's exit code and stderr.
- **Rerunnable on its own.** A failed or changed hook is run again by a command of its own (`shingi hook <unit>`), since running `create` again is `unit-exists`. Hooks are expected to be safe to rerun: finding what an earlier run made by its `extra` keys before making it again.
- **Trusted as the rules file is.** A hook is a command the user wrote into their own config, with the user's permissions; shingi sandboxes nothing.
- **A log convention.** Hooks, and the agents doing a unit's tasks, append timestamped lines under a `## Log` heading in `uow.md` — set up, merge request opened, blocked on review — giving a reader the unit's history without a database. Once ino reads it, it is a [format](#how-shingi-fits), and the skill writes it down.

#### Context

`shingi context <unit>`: everything an agent needs to start work on a unit, in one call — what a worker is spawned with, and what ino reads instead of composing it from three tools.

- **Where it is:** everything [`where`](#where) reports.
- **Why it exists:** the chain of its ancestors, from the top-level unit down, each with its path, `id`, kind, and title — `HOME-12345` (group) *Payment retries* › `foo-split` (group) *seven stacked MRs* › `1-schema` (branch) *schema changes*. `where` gives only the parent; a worker three levels down needs the whole chain to know what its piece is for. Derived each time from the ancestors' manifests and `uow.md` titles, never stored, so it can't go stale when a title is edited or a unit moves.
- **What is known:** the unit's `uow.md` in full, and its parent's.
- **What is left:** the unit's open koan tasks, with their readiness.

Read-only, and a composition of what shingi already reads — its own files and koan — so it belongs in shingi rather than in each consumer. It decides nothing: which unit to work on next stays ino's.

#### Unit from a worktree

[`shingi where`](#where) with no argument, answering "which unit am I in?" from a unit's code as well as its working folder.

- **A worktree is outside the working root,** so there is nothing to resolve from. Whoever makes the worktree — a hook, or an agent doing a setup task much later — registers it: `shingi bind <unit> [<dir>]` writes the unit's `id` to a file named `shingi-unit` in that checkout's own git directory (the one its `.git` file points to), and `where` with no argument reads it from there. Inside the git directory, the file can never be committed, shows in no `git status`, and is removed with the worktree. shingi reads the `.git` file to find it, and still runs no git.
- **Timing follows the work.** A unit whose tasks were specified now and done later has no worktree to be in until its setup runs; binding is part of that setup, so the marker appears exactly when there is a directory to resolve from.

#### Moving and removing units

`shingi move`, which moves a unit's koan folder and working folder together, and `shingi remove`, which removes both. Until then, by hand. To move, `koan move-folder` the unit's koan folder, `mv` its working folder to the same new path, and `koan update --title` the start and done tasks of it and every unit beneath it to their new paths. To remove, `koan delete-folder -r` on the unit's koan folder, which also takes its tasks out of every `blocked_by` outside it, so its parent's done task is no longer waiting on it; then remove its working folder; then undo whatever its setup made, such as a worktree and branch, the way it was made.

#### Changing a unit's kind

`shingi retype <unit> <kind>`, for a label that was wrong from the start. It would be the first command to rewrite a manifest; until then, a corrected kind is an outside change.

#### Machine-readable facts

A free-form `extra` object in the manifest, as koan's, for facts a script needs to read reliably and `uow.md` can't hold. `## Code` holds what a setup task decides for now; a fact moves here only when a script can't rely on that format, and would need a way to set it after `create`, which a write-once manifest doesn't have. Added as a manifest schema change when a script needs it.

#### Keeping the working root in git

Not a shingi feature, a habit it makes possible: `git init` the working root, and every `uow.md` gets its history — what was decided, and when it changed — for nothing. Hidden temp files and `.gitignore` keep it clean. Worth a paragraph in the skill once it has been tried.
