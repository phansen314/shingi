# Feature: shingi as a repo of recipes

**Status:** all the recipes are built: `start`, `claim`, `dispatch`, `worktree` and `stale-claims`. The Python tool is removed. Written against shingi `main` at v0.4.0, koan v0.14.0 and sesshin 1.2.1.

## Summary

shingi stops being a CLI and becomes a small repo of **recipes**: scripts, with a Claude Code skill wrapped around each, that compose [koan](https://github.com/phansen314/koan), [sesshin](https://github.com/phansen314/sesshin) and `jq` through their JSON output. It has no binary and no data of its own. The recipes:

- `/shingi:claim <task>`: claim a task and start on it **in this session**, with its notes loaded;
- `/shingi:start <task>`: load a task that's already claimed, its notes included;
- `/shingi:dispatch <task> [dir]`: claim a task and start **a new session** for it through sesshin;
- `/shingi:worktree <folder> <branch> [dir]`: add a git worktree and bind it to a koan folder;
- `/shingi:stale-claims`: list claims whose session is gone.

## Why

- **Agents claim tasks without reading their notes.** `claim` and `claim-next` return the task's `notes_path`, and an agent can skip opening it. A skill can run a script before its text reaches Claude, and put the script's output in its place, so a command that claims and then prints the notes makes reading them part of claiming. This covers the commands a person invokes. An agent that claims on its own, as koan's skill suggests with `claim-next`, isn't covered; a line in koan's skill would do that, proposed in koan on its own merits.
- **Starting work right away isn't always right.** A hook that pushed the notes into context after every `koan claim` would start work the moment anything claimed. Commands the user invokes decide when work starts: here (`/shingi:claim`), elsewhere (`/shingi:dispatch`), or not yet (a plain `koan claim`).
- **koan and sesshin stay independent.** Neither should know the other exists. shingi depends on both, and neither depends on shingi: the composition lives in one place, as small scripts joined by `jq`.
- **shingi's old job is done.** Its units of work (a koan folder for tasks, a working folder for notes, worktree markers) were built on the original koan. Today's koan has folders with notes and material, and binds worktrees itself.

## Principles

1. **Recipes, not a program.** Each recipe is a shell script plus a README, and usually a skill. No binary, no package, no state of its own.
2. **One-way dependency.** shingi knows koan and sesshin through their JSON contracts. Their docs, code and data never name shingi. A recipe that needs only koan says so and runs without sesshin.
3. **shingi owns the links it makes.** Following "one program, one namespace", a recipe that ties a claim to a session writes under `shingi`: `{"shingi":{"job":"koan-42"}}` on the koan claim. Never a `sesshin` key in koan, or a `koan` key in sesshin. A link no recipe reads isn't written.
4. **Skills wrap scripts, never the reverse.** A skill is a one-line `!` call to its recipe's script plus a few sentences telling the session what to do with the output. A person, a cron job or another harness can run the same script without Claude Code.
5. **Every recipe states what it needs and what it writes:** the tools and minimum versions, and every `extra` key it reads or writes. Its script checks the versions first, and names the missing tool plainly.
6. **Scripts tell, they don't abort.** A skill's `!` command aborts the whole invocation on a non-zero exit. So a script that runs from a skill exits 0 when koan or sesshin refuses, and prints what happened. A refusal's first line begins `DON'T START:`, which is what the skills look for, or `NOT DONE:` in a recipe that starts no work. A non-zero exit is kept for the script's own bugs and bad usage.
7. **Shell and `jq` only.** POSIX tools, bash, and `jq`. Every script passes shellcheck.

## Layout

```
README.md                         what shingi is, the recipes, what each needs; a History note
recipes-spec.md                   this doc
recipes/
  lib.sh                          shared: refusals, version checks, task IDs
  start/     README.md  start.sh
  claim/     README.md  claim.sh
  dispatch/  README.md  dispatch.sh
  worktree/  README.md  worktree.sh
  stale-claims/  README.md  stale-claims.sh
claude/skills/
  start/SKILL.md                  → /shingi:start <task>
  claim/SKILL.md                  → /shingi:claim <task>
  dispatch/SKILL.md               → /shingi:dispatch <task> [dir]
  worktree/SKILL.md               → /shingi:worktree <folder> <branch> [dir]
  stale-claims/SKILL.md           → /shingi:stale-claims
tests/
  run.sh                          runs every test file
  lib.sh                          a scratch HOME per test, assertions
  stub/sesshin                    a fake sesshin: records its arguments, prints canned JSON
  test_*.sh                       one file per recipe
.claude-plugin/                   plugin and marketplace, as today, with new descriptions
.github/workflows/ci.yml          shellcheck and tests, on Linux and macOS
```

Scripts find `lib.sh` and each other from their own path: Claude Code fills `${CLAUDE_PLUGIN_ROOT}` into a skill's text, but doesn't put it in the script's environment.

**Removed:** `src/`, `tests/*.py`, `pyproject.toml`, `uv.lock`, `claude/skills/shingi/`, `scripts/install.sh`, `scripts/smoke.sh`, and the five specs (`design-spec.md`, `operations.md`, `cli-spec.md`, `hooks-spec.md`, `hooks-impl-spec.md`). They stay in history at the `v0.4.0` tag, the last release of the units tool. The README's History section says so, as sesshin's does for herd, and that shingi's old tree under `~/shingi-root` and `/shingi` in koan are the user's to keep or remove by hand.

## The recipes

### start: load a claimed task

**Usage:** `start.sh <task>`, where `<task>` is an ID, `42` or `@42`. Skill: `/shingi:start <task>`.

**Needs:** koan v0.13.0 or later, and `jq`.

**Reads:** the task's claim, and its `extra.shingi.job` when present. Writes nothing.

**Does:**
1. Check `jq` and `koan version`. On a failure or an old version, print what's wrong and stop (exit 0).
2. `koan show <task>`. On a failure, print koan's envelope, say don't start, and stop. The same when the ID names a folder rather than a task.
3. **Check the claim.** If `.result.task.claim` is null: print that @42 isn't claimed and the user can run /shingi:claim 42, and stop. If `SESSHIN_JOB` is set in the environment (sesshin sets it in every session it spawns) and the claim's `extra.shingi.job` is set and differs, print that another session holds it, and stop.
4. **Check it's ready.** koan lets a blocked task be claimed, to reserve it ahead. If `.result.task.readiness` is `blocked`: print what it waits on, and that it stays claimed, and stop.
5. **Print the brief**, in this order, each under a plain heading:
   - one line: `@42 (/work/api) is claimed: <title>`. koan doesn't record who holds a claim, so this line doesn't say "you";
   - the task's record, as `koan show` printed it;
   - its notes: the file at `.result.task.notes_path`, whole, or `(no notes yet)` when it's missing or empty;
   - its folder's brief: `koan context <folder id> --limit 20`, as printed, unless the task sits in the root (`.result.task.folder.id` is null).
6. **Stay under the output limit.** Claude Code collapses a `!` command's output above about 30,000 characters to a 2KB preview and a file path, which would lose the notes. So the brief keeps to 25,000: when the notes, and then the folder's brief, won't fit, it prints instead where to read them and that they must be read before starting.
7. Exit 0.

**Skill** (`claude/skills/start/SKILL.md`):

```markdown
---
name: start
description: Load a koan task that's already claimed, with its notes, and start work on it.
disable-model-invocation: true
argument-hint: <task>
allowed-tools: Bash(${CLAUDE_PLUGIN_ROOT}/recipes/start/start.sh:*)
---
!`"${CLAUDE_PLUGIN_ROOT}/recipes/start/start.sh" $0`

If the output above begins with DON'T START, don't start: tell the user what it says. Otherwise start work on the task now, following its notes, and keep its notes file up to date as you go. You own this task; you aren't a coordinator's worker. Run `koan complete` on it when it's done, or `koan unclaim` if you stop early.
```

### claim: claim a task and start on it here

**Usage:** `claim.sh <task>`. Skill: `/shingi:claim <task>`.

**Needs:** koan v0.13.0 or later, and `jq`. Not sesshin.

**Writes:** the claim's `extra`: `{"shingi":{"by":"claude"}}`, plus `"job"` when `SESSHIN_JOB` is set.

**Does:**
1. Check `jq` and `koan version`, as for `start`.
2. `koan claim <task> --extra '<the shingi object>'`. On a failure, print a line for its kind, then koan's envelope, and stop:
   - `conflict`, rule `claimed`: "@42 is already claimed: tell the user; if it's this session's, /shingi:start 42 loads it";
   - `conflict`, rule `already-complete`: "@42 is complete: it needs reopening first, if the user wants it worked on";
   - any other kind: "Not claimed: tell the user, quoting the message".
3. Run `start.sh <task>` and print what it prints. It finds the claim just made. A blocked task stays claimed, reserved ahead, and isn't started.

**Skill** (`claude/skills/claim/SKILL.md`): as `start`'s, calling `claim.sh`, with the description "Claim a koan task and start work on it in this session, with its notes loaded", and `allowed-tools` naming `claim.sh`.

### dispatch: claim a task and start a new session for it

**Usage:** `dispatch.sh <task> [dir] [-- <sesshin spawn options>]`. Options after `--`, such as `--template opus` or `--type split`, go to `sesshin spawn` as given. Skill: `/shingi:dispatch <task> [dir]`.

**Needs:** koan v0.13.0 or later, sesshin 1.2.0 or later with kitty or iTerm2 set up for `spawn`, and `jq`. The new session needs the shingi plugin, installed for the user, not just for a project, so that it has `/shingi:start`.

**Writes:** the claim's `extra`, `{"shingi":{"by":"dispatch","job":"koan-<id>"}}`, and the session's sesshin job, `koan-<id>`.

**Does:**
1. Check `koan version` and `sesshin version`. Name what's missing or too old, and stop.
2. Work out the ID (`@42` → `42`), the job `koan-42`, and, when `[dir]` is given, the directory, resolved. It must exist.
3. **Check it's ready:** a blocked task prints what it waits on, and stops, so no window opens only to refuse.
4. **Claim first:** `koan claim <id> --extra '{"shingi":{"by":"dispatch","job":"koan-42"}}'`. On a failure, as `claim`'s step 2, and stop. Claiming before spawning means no other agent can take the task while the window opens.
5. **Spawn:** `sesshin spawn --job koan-42 [--cwd <dir>] --prompt '/shingi:start 42' [options after --]`. `--cwd` is passed only when `[dir]` is given, so a template's directory, or else the working directory, applies as sesshin's own default. So two dispatches with no `[dir]` share a checkout: give each its own directory until the `worktree` recipe exists.
6. **On a spawn failure**, by sesshin's error:
   - `terminal` with `details.reason` `launch-unknown`: a window may have opened, and sesshin keeps its reservation. Keep the claim, and print "A window may have opened: check with `sesshin focus koan-42`; @42 stays claimed".
   - anything else (`conflict` with `details.rule` `job-taken`, `terminal` with `launch-failed`, `invalid-input`, `not-found` for a template, …): nothing started, so undo the claim with `koan unclaim <id>`, and print sesshin's envelope with "No session started; @42 is unclaimed again".
7. **On success,** print "Dispatched @42 to the session with job koan-42", and sesshin's envelope. A `not-started` warning, meaning the session didn't start within the timeout and is perhaps waiting at Claude's workspace-trust dialog, keeps the claim, and the output says to accept the dialog in the new window.
8. Exit 0.

**The handle:** sesshin selects a session by its job, so `sesshin focus koan-42`, `sesshin show koan-42` and `sesshin send koan-42 --text '…'` reach the session working on @42. sesshin refuses a second live session with that job, which is a second guard beside koan's claim.

**Finishing:** the new session owns the task, by `start`'s skill text: it completes it, or unclaims it if it stops early. koan's skill has rules for a worker started by a coordinator, which report back instead; no coordinator is waiting here, so the skill text says so.

**Skill** (`claude/skills/dispatch/SKILL.md`):

```markdown
---
name: dispatch
description: Claim a koan task and start a new Claude session for it with sesshin.
disable-model-invocation: true
argument-hint: <task> [dir]
allowed-tools: Bash(${CLAUDE_PLUGIN_ROOT}/recipes/dispatch/dispatch.sh:*)
---
!`"${CLAUDE_PLUGIN_ROOT}/recipes/dispatch/dispatch.sh" $ARGUMENTS`

Report to the user what happened above, in a sentence or two. Don't start work on the task yourself: the new session does that.
```

## Tests

- **Real koan, scratch HOME.** Every test gets its own `HOME`, runs `koan init`, and builds the tasks it needs. CI installs koan at a pinned tag (`go install github.com/phansen314/koan/cmd/koan@v0.14.0`), so a koan release can't break the tests unannounced. The pin moves on purpose.
- **A stub sesshin, with `dispatch`.** `spawn` needs a real terminal, so `tests/stub/sesshin`, put first on `PATH`, records its arguments to a file and prints JSON that each test chooses: success, `job-taken`, `launch-failed`, `launch-unknown`, a `not-started` warning. `version` is stubbed too.
- **What they check:**
  - `start`: unclaimed, claimed, held by another job, blocked, a folder's ID, missing notes, notes over the limit, a task in the root, koan missing or too old.
  - `claim`: success, its `extra`, `claimed`, `already-complete`, not found, blocked.
  - `dispatch`: every branch of step 6, with the claim afterwards held or undone as the step says; the exact `spawn` arguments, with `--cwd` only when `[dir]` is given; options after `--` passed through; a blocked task opening no window.
  - `worktree`: a new and an existing branch, the default and an explicit directory, each refusal making nothing, and a refused bind removing what was made.
  - `stale-claims`: live, gone and no job, and that it changes nothing.
  - Every script that a skill runs exits 0 on every refusal, and prints the refused tool's envelope.
- **shellcheck** on every script, in CI.
- CI on Linux and macOS, reusing today's workflow's action pins.

## Permissions

A skill's `allowed-tools` pre-approves its own script and nothing else: `Bash(${CLAUDE_PLUGIN_ROOT}/recipes/start/start.sh:*)`. What a script runs inside isn't checked, so no rule for `koan`, `sesshin`, `jq` or `cat` is needed to run a recipe. What the session does afterwards, such as `koan complete`, goes by koan's and sesshin's own rules, set by their install scripts.

There's no install script. The old `shingi` permission rules are removed by `scripts/install.sh --uninstall` at `v0.4.0`.

## Settled before building

Checked on Claude Code 2.1.318 with a throwaway plugin:

1. **A slash command as the first prompt** works: `claude '/plugin:skill 42'` in an interactive session runs the skill, as if typed. Seen in a trusted directory.
2. **Placeholders in a `!` command** work: `${CLAUDE_PLUGIN_ROOT}`, `$0` and `$ARGUMENTS` are all filled in, `~` expands, and `-- --template opus` passes through.
3. **`allowed-tools` for a script path** works, with `${CLAUDE_PLUGIN_ROOT}` in the rule. `Bash(koan:*)` and `Bash(*/recipes/x.sh:*)` don't approve the script, and the skill fails with "This command requires approval".
4. **`SESSHIN_JOB`** reaches a `!` command. `CLAUDE_PLUGIN_ROOT` doesn't.
5. **Output over about 30,000 characters** reaches the model as a 2KB preview and a path, which is why `start` has a limit.

Not yet seen: a real `sesshin spawn`, Claude's workspace-trust dialog in front of the first prompt, and the plugin installed from the marketplace rather than `--plugin-dir`. The end-to-end check below covers them.

## Build order

In vertical slices: the recipes, then removing the Python tool as its own step. Both are done.

## The smaller recipes

Each recipe's README states its usage, needs and writes in full.

- **worktree:** `git worktree add` and `koan bind` together, with `koan context --here` to finish. A refused bind removes the worktree again, and the branch if this run made it. Its path goes to `dispatch`.
- **stale-claims:** claims whose `extra.shingi.job` names no live sesshin session, joined with `jq` from `koan task list --claimed` and `sesshin list`, for the user to decide on unclaiming. Claims with no job can't be judged, and are listed apart. It changes nothing.

## Later recipes

Not built. Each in the same shape, if wanted after real use:
- **parking:** the `waiting` and `deferred` conventions.
- **reminders:** a cron-driven runner that removes `deferred` when a date under `extra.shingi.remind` passes.

## Out of scope

- Any change to koan or sesshin. If a recipe needs one, it's proposed in that repo, on its own merits.
- A shingi binary, a config file, or data of shingi's own.
- OpenCode support. The scripts work from any harness, but the skills here are Claude Code's.

## Done when

- The recipes behave as above.
- `tests/run.sh` passes on Linux and macOS, and shellcheck is clean.
- Each recipe's README states its needs and writes.
- From a real session, `/shingi:claim`, `/shingi:start` and `/shingi:dispatch` each work end to end against your own koan root and kitty or iTerm2.
