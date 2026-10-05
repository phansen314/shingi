# shingi design spec

## Goals

Keep agent work on one machine in the right place: one file declares where a story's tasks and working files belong, and every agent harness — Claude Code and OpenCode first, others [later](#future-work) — is told those rules.

- **The rules are the product.** shingi's value is one declaration of the layout, `shingi.toml`, that every actor reads the same way: an agent through its harness, a person through the CLI, a coordinator through JSON. shingi runs no agents and keeps no state; the rules and the trees they describe are the whole of it.
- **Harnesses get adapters, not a framework.** Everything a harness needs is the skill and one harness-neutral command, [`where`](#where). An adapter only puts them in front of the agent, as a skill or as tools. Adding a harness never changes the rules.
- **Runs only when asked.** shingi hooks into no harness and adds nothing to how a session starts. A session learns its story when you or its agent ask: through the skill, `where`, or `init`.
- **Tell, never enforce.** shingi never stands between an agent and its tools, and never judges what they did. Agents are told the layout ([`where`](#where)), and that is all. A misplaced task or file is cheap to move when someone notices it; preventing it would cost a hook on every tool call and a parser for every shell line an agent writes, and auditing it would make the layout a set of rules strict enough to check, which real work keeps breaking for good reasons.

shingi is one binary, `shingi`. Its commands are [`where`](#where), [`init`](#init), and `version`. [`graph`](#graph) and [`mcp`](#the-mcp-adapter) come after v1 (see [Future work](#future-work)).

## Non-goals

- **Running or coordinating agents.** Deciding who works on what, and when, is ino's job. shingi answers *where*, never *who* or *when*.
- **Ordering phases.** Phases are folders, listed in work order, but shingi never holds a task back until an earlier phase is done. Work rarely moves through phases in a straight line, so ordering between tasks stays with koan's `blocked_by`, set by whoever creates them.
- **State of its own.** shingi writes only what [`init`](#init) creates for a story: a workspace, and tasks through koan. It has no state directory, cache, or index.
- **Owning koan's or sesshin's data.** shingi reads and writes koan's tree only through koan's CLI, never its files, and takes nothing from sesshin but `SESSHIN_JOB` (see [Talking to koan and sesshin](#talking-to-koan-and-sesshin)).
- **Commands for task progress.** shingi has no command that marks a task. Agents record progress with a plain `koan update`, by the convention shingi's skill teaches (see [Task status](#task-status)).
- **Talking to Jira.** shingi knows a story by its key alone. Fetching a title or status from Jira is [future work](#jira-titles).
- **More than one user, or more than one machine.** As for koan and sesshin.

## Assumptions

- **koan is installed,** on `PATH`, with a version shingi supports (see [Talking to koan and sesshin](#talking-to-koan-and-sesshin)). sesshin is optional and never run: shingi reads only the `SESSHIN_JOB` it leaves in a session's environment, and without it a session's story is found by its other [sources](#finding-a-sessions-story).
- **shingi doesn't own the trees it describes.** koan owns its tree; you and your agents own the workspaces. Any of them may change a story's layout, and the rules only describe where things *should* go. shingi never looks for drift.
- **Agents follow what they are told, mostly.** An agent that knows its story's paths puts most things in the right place, and the rest is cheap to move by hand.
- **One user, one machine.** One OS user's config names one set of rules.

## Supported platforms

Linux and macOS, on amd64 and arm64, as koan and sesshin. Windows is never supported.

## Terms

| Term | Meaning |
|---|---|
| **rules** | The layout declared by `shingi.toml` (see [The rules file](#the-rules-file)). |
| **story** | One unit of work, named by a key: its tasks in koan and its workspace on disk. |
| **key** | A story's name, in canonical form: `JIRA-12345` (see [Keys](#keys)). |
| **stories root** | The koan folder that holds every story's folder, e.g. `/stories`. |
| **story folder** | A story's koan folder: the stories root plus the key, e.g. `/stories/JIRA-12345`. |
| **phase** | One of the folders the rules allow directly under a story folder, e.g. `research`. |
| **workspaces root** | The directory that holds every story's workspace, e.g. `~/work/stories`. |
| **workspace** | A story's directory of working files: the workspaces root plus the key. |
| **scratchpad** | The file the rules name at the top of a workspace, for running notes. |
| **workspace dirs** | The directories the rules name at the top of a workspace. |
| **harness** | A program that runs an agent and its tool calls: Claude Code, OpenCode, LM Studio, pi. |
| **adapter** | The harness-specific glue that gives an agent the skill or shingi's commands as tools (see [Adapters](#adapters)). |

## Locations

| What | Where |
|---|---|
| The rules | `shingi.toml` in shingi's config directory, found as koan and sesshin find theirs: on Linux, `$XDG_CONFIG_HOME/shingi` when `XDG_CONFIG_HOME` is an absolute path, otherwise `~/.config/shingi`; on macOS, `~/Library/Application Support/shingi`. |
| A story's tasks | The story folder in koan's tree, wherever koan's root is. shingi knows only koan folder paths, never where koan's root is on disk. |
| A story's workspace | The workspaces root plus the key. |

No environment variable sets a location or a rule, for sesshin's reason: an adapter's environment is whatever started the harness, so a setting there could reach one process and not another. `--config <file>` overrides the rules file for one command, for tests and trials.

## The rules file

### Example

```toml
schema = 1
key    = '[A-Z][A-Z0-9]+-[0-9]+'

[koan]
root   = "/stories"
phases = ["setup", "research", "implementation", "review"]

[workspace]
root       = "~/work/stories"
scratchpad = "scratchpad.md"
dirs       = ["common", "docs", "graphs"]
seed       = { "scratchpad.md" = "# {key}{title_suffix}\n" }

[[task]]
phase = "setup"
ref   = "common"
title = "Set up the common folder"
notes = "Inputs shared by every phase go in {workspace}/common."

[[task]]
phase = "setup"
ref   = "scratchpad"
title = "Start the scratchpad"
notes = "Running notes for {key} go in {scratchpad}."

[[task]]
phase      = "research"
ref        = "research"
title      = "Research {key}"
blocked_by = ["common"]

[[task]]
phase      = "implementation"
ref        = "implement"
title      = "Implement {key}"
blocked_by = ["research"]

[[task]]
phase      = "review"
title      = "Review {key}"
blocked_by = ["implement"]
```

Phases put no order on tasks: a starter task that should wait on another says so in `blocked_by`, as any koan task does.

### Fields

| Field | Type | Meaning |
|---|---|---|
| `schema` | integer | The file's format version (see [Format versions](#format-versions)). Required. |
| `key` | string | A regular expression (Go's RE2 syntax) for a key, unanchored: shingi anchors it itself (see [Keys](#keys)). Required. |
| `koan.root` | string | The stories root: a koan folder path, absolute, never `/`. Required. |
| `koan.phases` | list of strings | The phase folders, in work order, each a valid koan folder name. At least one. The order is for people and agents to read; nothing enforces it. |
| `workspace.root` | string | The workspaces root. A leading `~/` is the home directory; otherwise absolute. Required. |
| `workspace.scratchpad` | string | The scratchpad's filename. Optional: without one, a workspace has none. |
| `workspace.dirs` | list of strings | The workspace dirs. May be empty. |
| `workspace.seed` | table | Starting contents for files `init` creates, keyed by path relative to the workspace. Optional. Seeds are a story's starting content only: what happens to them afterwards is ordinary work. |
| `task` | array of tables | The tasks `init` creates (see [Starter tasks](#starter-tasks)). Optional. |

Unknown fields are an error, not ignored, so a typo says so instead of silently doing nothing.

Each path in `workspace.seed` must be the scratchpad or lie inside a workspace dir, so `init` never puts a file anywhere the layout doesn't. Anything else is an error when the rules are loaded.

### Placeholders

Text in `seed`, and in a task's `title` and `notes`, may use placeholders, written `{name}`:

| Placeholder | Value |
|---|---|
| `{key}` | The key, e.g. `JIRA-12345`. |
| `{title}` | The title given to `init`, or empty. |
| `{title_suffix}` | `: ` and the title, or empty when there is none. |
| `{story}` | The story folder, e.g. `/stories/JIRA-12345`. |
| `{workspace}` | The workspace, with `~` expanded. |
| `{scratchpad}` | The scratchpad's full path. |
| `{phase}` | The task's phase. Not in `seed`. |

`{{` and `}}` are a literal brace. Any other `{name}` is an error when the rules are loaded, not when they are used. There is no template language beyond this: paths are never templated, because every path is a root plus the key.

## Keys

- **Matching.** A key is a string the `key` pattern matches in full, ignoring case. `jira-12345` is a key; `JIRA-12345x` is not.
- **Canonical form is uppercase.** Every key shingi reads — from an argument, a job, a branch — is uppercased before it is used, so `jira-12345` and `JIRA-12345` are one story, and its folder and workspace are always named `JIRA-12345`.
- **Finding a key inside text.** To find a key in a job name, a branch, or a directory name, shingi finds the first match of the pattern that is bounded on both sides by the start or end of the text or by a character that is not a letter or digit: the first submatch of `(?i)(?:^|[^A-Za-z0-9])(<key>)(?:$|[^A-Za-z0-9])`, with `<key>` the rules' pattern. `JIRA-12345-research`, `feature/jira-12345-payment-retries`, and `JIRA-12345` all contain `JIRA-12345`; `JIRA-12345x` contains none.

## The layout

What `init` creates, and what agents are told:

- **koan side.** A story's tasks go in its phase folders, under the story folder. How a phase is broken down — subfolders, more tasks — is the agent's call.
- **Workspace side.** A story's working files go in its workspace: running notes in the scratchpad, everything else in a workspace dir.
- **Names are keys.** The story folder and the workspace are both named by the canonical key.

This is guidance, not a test. Nothing checks it, and nothing outside the stories root and the workspaces root is shingi's concern at all.

## Task status

koan knows two states, open and complete, and gives no meaning to anything finer: no status vocabulary, in its code or its skill. Finer states are shingi's convention, for a story's tasks:

- **One key,** `extra.status`, holding a task's one workflow state at a time — one key rather than tags, so a task can't be two states at once.
- **One value,** `in-progress`, set when work on a task begins. A task with no `status` is simply open.
- **Set with koan, not shingi:** `koan update <id> --extra-merge '{"status":"in-progress"}'`, cleared with `--extra-remove status`. shingi's skill teaches this; shingi has no command for it.
- **Complete wins.** A complete task is complete whatever its `status`.

shingi itself never reads it in v1; [`graph`](#graph) will.

## Finding a session's story

`where` without a key finds the story a session belongs to from these sources, in order, stopping at the first that yields a key:

1. **The key argument,** given by a person or an agent.
2. **`SESSHIN_JOB`,** in the process's environment. sesshin puts it in Claude's environment, so every hook and tool Claude runs inherits it: `sesshin spawn --job JIRA-12345-research` names the story.
3. **The working directory,** when it is inside a workspace: the key is the name of the workspace it is in.
4. **The git branch** of the working directory, found with `git rev-parse --abbrev-ref HEAD` with a 500 ms limit, when the key found in it names a story whose workspace exists.

The first two sources are deliberate, so their key is taken as given, even for a story `init` hasn't created yet: a session can be spawned for a story and create it. The last two are inferred, so they count only for a story that exists. Branch names are free text, and a key pattern finds keys in many that name no story (`release-2026`, `fix/utf-8-handling`); without the check, `where` would tell an agent it works on `UTF-8`. Whether the story exists is one `stat` of its workspace, with no call to koan. The working directory needs no check of its own: being inside a workspace means the workspace exists.

The result names its `source`, so a surprising story can be traced to where it came from. A source that yields no key, or a branch key with no workspace, is skipped quietly; one that fails (git missing, the timeout) is skipped with a warning. No source is ever guessed from: a session with no key has no story, and `where` fails with `no-story`.

## Commands

Every command prints one line of JSON to stdout, in the same envelope as koan and sesshin, and uses their exit codes, so one `jq` habit covers all three. Detailed inputs, outputs, and errors belong in `operations.md`; this section gives each command's purpose and contract.

### where

`shingi where [<key>]` — one story's paths, as fields and as prose. Without a key, the session's story (see [Finding a session's story](#finding-a-sessions-story)), and the `source` it came from.

- **The fields:** the story folder, each phase folder, the workspace, the scratchpad, and each workspace dir. Computed from the rules alone, and reported whether or not they exist yet.
- **`text`:** the same facts as short prose, for an agent to read or a skill to pass on:

```
This session works on JIRA-12345.
Tasks go in koan under /stories/JIRA-12345/<phase>; phases: setup, research, implementation, review.
Scratchpad: /home/you/work/stories/JIRA-12345/scratchpad.md
Shared files: common/, docs/, graphs/ in /home/you/work/stories/JIRA-12345.
```

Every path is absolute, with `~` expanded: not every harness's file tools expand `~`.

`where` is how an agent never has to rebuild a path. The skill tells agents to ask `where` rather than compose a path.

### init

`shingi init <key> [--title <text>]` — create a story in place: its workspace, its phase folders, and its starter tasks.

1. **Check the input.** Every starter task's title and notes are expanded and checked against koan's [title rules](https://github.com/phansen314/koan/blob/main/design-spec.md#titles) (at most 200 characters after trimming, no line breaks), so a long `--title` fails here, with `invalid-input`, before anything is written.
2. **Refuse an existing story.** If the story folder exists in koan, `init` fails with `story-exists` and changes nothing. The story folder is the one guard: koan's `create` is not safe to retry blindly, and a story folder is in place once any of step 3 has been written.
3. **The tasks.** One `koan create-batch` with every starter task, so koan checks all of them before writing any. It creates the story folder and the folder of every phase that has a starter task. With no starter tasks, `koan create-folder -p` creates the story folder instead.
4. **The empty phases.** `koan create-folder` for each phase step 3 didn't create.
5. **The workspace.** Create the workspace, each workspace dir, and each seeded file, each only if missing, never replacing an entry that exists. A workspace that already exists is used as it is.

`init` is for new stories only, never rerun on an existing one. The koan side comes first because it is the side that can't be retried: `create-batch` is all-or-nothing, and once it has written, the story folder refuses a second `init` that would duplicate the tasks. A crash after it leaves a story missing some phase folders or workspace entries; `where` lists every path that should exist, and `koan create-folder` and `mkdir` fill the gap.

#### Starter tasks

Each `[[task]]` becomes one item of the `create-batch` input:

| Field | Becomes |
|---|---|
| `phase` | The task's `folder`: the story folder plus the phase. Required, and must be a phase. |
| `ref` | The item's `ref`, for later tasks' `blocked_by`. Optional. |
| `title`, `notes` | The same fields, after [placeholders](#placeholders). `title` is required. |
| `priority`, `tags` | The same fields, as given. Optional. |
| `blocked_by` | Refs of earlier tasks in the file. Only refs: a starter task can't name a task ID, since the rules can't know one. |

The tasks keep koan's order rule: a ref names an earlier task, so the file lists blockers first.

On success, `init`'s result is [`where`](#where)'s for the new story, `text` included, plus the IDs of the tasks it created, so the skill can hand the agent its paths without a second call.

## Adapters

### Claude Code

A Claude Code plugin, served from this repository as koan's and sesshin's are, carrying one skill and no hooks: shingi adds nothing to how a Claude Code session starts. You invoke the skill to create a story, and it stays in the session from then on. A plugin can't grant permissions, so the permission rules below are added as koan's are, by `scripts/install.sh`, which backs `settings.json` up first and is safe to rerun.

- **The skill, on stories:** `shingi init` for a story you name, or `shingi where` for one that exists, and its `text` for the paths; the layout, in words; and to call `where` instead of composing a path.
- **The skill, on status:** set `extra.status` to `in-progress` when beginning a story's task, and remove it on stopping without finishing; `koan complete` when done.
- **Permissions:** `shingi where` and `version` run without a prompt; `init`, which creates a story, asks.

### OpenCode

The same skill, linked into OpenCode's skills directory as koan's is.

## Talking to koan and sesshin

- **koan through its CLI only.** shingi runs `koan` and reads its JSON; it never reads koan's task files. koan is pre-1.0 and changes its formats in place, and its CLI is the contract it keeps.
- **sesshin not at all, but for `SESSHIN_JOB`,** an environment hand-off sesshin documents. shingi never runs `sesshin` or reads its state directory.
- **Versions.** shingi checks `koan version` the first time a command needs koan, and fails with `unsupported-koan` outside the range it was built for, rather than misread an output it doesn't know.
- **koan's errors are wrapped, never translated.** When koan fails, shingi fails with kind `koan`, and its `details` hold the koan command it ran and koan's error object as koan gave it: `jq '.error.details.error.kind'` reads `busy`, `conflict`, and the rest. shingi keeps no map of koan's error kinds, so a kind koan adds needs no change in shingi.
- **An unknown outcome is said outright.** When koan exits `3` or is killed (its outcome unknown, per koan's [exit codes](https://github.com/phansen314/koan/blob/main/cli-spec.md#exit-codes)), shingi fails with kind `koan-unknown`. For `init`'s `create-batch`, the message says tasks may have been created, and to look for the story folder before running `init` again; a rerun is refused anyway once the story folder exists.
- **koan's warnings pass through,** each in shingi's `warnings` as koan gave it, with `source: "koan"` added.

## Concurrency

shingi writes only in `init`, which creates a new workspace, entry by entry without replacing any, and tasks through koan. Every koan write is under koan's own write lock. Every other command is read-only. Two `init`s of one key at once can both pass the existence check; the second's `create-batch` then puts a duplicate set of tasks in the story. Running `init` twice at once is not supported.

## Format versions

`shingi.toml` carries `schema`. A rules file with a `schema` shingi doesn't support is an error for every command. Before 1.0, as koan's and sesshin's formats, the schema may change in place: a change bumps the minor version, and its release notes say how to update the file.

## Open questions

### Per-repository rules

Some repositories may want a different layout (another phase set, another workspaces root). Whether a rules file in a repository should override or extend the user's, and how a harness finds it, is open.

## Future work

### graph

What it would do, as designed so far:

`shingi graph [<key>] [--all-edges]` — draw one story's tasks as a Graphviz DOT graph, top to bottom, on stdout: `shingi graph JIRA-12345 | dot -Tsvg > graph.svg`. It is the one command whose output breaks the [envelope rule](#commands), since stdout is meant for `dot`: success writes DOT to stdout, and failure writes the envelope to stderr instead, with a nonzero exit, so `dot` reads nothing and the error stays on screen. The exit code says which. It reads the story's tasks, complete ones included, with one `koan list`.

**What is drawn:**

- **Folders are dashed boxes,** one Graphviz cluster per folder under the story folder, nested as the folders are, each labeled with its path below the story folder (`research/spikes`). The graph's label is the key.
- **Tasks are rounded boxes** labeled `#<id>` and the title, wrapped near 28 characters, and filled by [status](#task-status): green when complete; otherwise the color the rules' `graph.colors` give its `extra.status` (yellow for `in-progress` by default), or white.
- **Edges run from blocker to blocked,** so work flows down the page.
- **Blockers outside the story** are drawn outside every cluster, dashed and grey, labeled with their ID, title, and folder, so a dependency on another story is visible without drawing that story.

**Layout:**

- **Top to bottom** (`rankdir=TB`).
- **Phases stack, in the rules' order.** Left alone, Graphviz places phases with no edges between them side by side. `graph` adds an invisible edge from each task of a phase that nothing else in the phase waits on to each task of the next non-empty phase that waits on nothing in its own phase, so each phase sits below the one before. These edges are layout only, never dependencies.
- **Redundant edges are dropped.** A task blocked by both `a` and `b`, where `b` already waits on `a`, would get an arrow from `a` that adds nothing to the order. By default `graph` draws the transitive reduction: an edge `a → c` is left out when `a` already reaches `c` another way. `--all-edges` draws every `blocked_by` as stored.
- **Colors** come from a new rules table, `graph.colors`, each any Graphviz color: `complete` and `open`, and `status`, from `extra.status` values to colors. Optional; defaults `palegreen`, `white`, and `{ in-progress = "yellow" }`. Its `status` keys then become the [status](#task-status) values the skill teaches.
- **Permissions:** runs without a prompt.
- **Stable output.** Nodes, clusters, and edges are written in ID and path order, so two runs on an unchanged story print the same bytes, and a graph kept in the workspace's `graphs/` diffs cleanly.

### The MCP adapter

When a story is first run in LM Studio: `shingi mcp`, serving `where`, `init`, and, once it exists, `graph`, as MCP tools over stdio, for any harness that speaks MCP and offers nothing else. The harness's system prompt or a preset tells the agent to call `where` when it works on a story.

### The pi adapter

When the pi-based orchestrator exists, a pi extension for it: tools that run `where` and `init`, so the orchestrator itself can create stories and find their paths.

### Story kinds

More than one layout — a story, a bug, a spike — each its own rules table, chosen at `init` (`shingi init JIRA-12345 --kind bug`) and recorded with the story, so `where` describes each story by its own rules. Where to record it is open.

### Jira titles

`init` fetching the story's title from Jira, through a connector or the Jira CLI, instead of `--title`.

### ino

When ino exists, it is one more reader of the rules: it asks `where` for a story's phase folders, and it is told the rules like any other actor. Which tasks are ready, and in what order, it learns from koan's `blocked_by` like everyone else.
