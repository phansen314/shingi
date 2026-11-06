# Feature: shingi as a repo of recipes

**Status:** all the recipes are built: `claim`, `dispatch`, `worktree`, `stale-claims` and `uow`. The Python tool is removed. Written against shingi `main` at v0.4.0, koan v0.14.0 and sesshin 1.2.1.

## Summary

shingi stops being a CLI and becomes a small repo of **recipes**: scripts, with a Claude Code skill wrapped around each, that compose [koan](https://github.com/phansen314/koan), [sesshin](https://github.com/phansen314/sesshin) and `jq` through their JSON output. It has no binary and no data of its own. The recipes:

- `/shingi:claim <task> [--start]`: claim a task for this session, and wait; with `--start`, load its notes and start work on it;
- `/shingi:dispatch <task> [--start] [dir]`: claim a task and start **a new session** for it through sesshin, whose first prompt is `/shingi:claim`, with `--start` if asked for;
- `/shingi:worktree <folder> [branch] [dir]`: add a git worktree in the repository's `.claude/worktrees` and bind it to a koan folder;
- `/shingi:stale-claims`: list claims whose session is gone;
- `/shingi:uow <type> <key> [--in <epic>] [title]`: scaffold a unit of work of type `implementation`, `research` or `epic`, marked with its type, with the type's tasks in order.

## Why

- **Agents claim tasks without reading their notes.** `claim` and `claim-next` return the task's `notes_path`, and an agent can skip opening it. A skill can run a script before its text reaches Claude, and put the script's output in its place, so a command that prints the notes makes reading them part of starting work. This covers the commands a person invokes. An agent that claims on its own, as koan's skill suggests with `claim-next`, isn't covered; a line in koan's skill would do that, proposed in koan on its own merits.
- **Starting work right away isn't always right.** A hook that pushed the notes into context after every `koan claim` would start work the moment anything claimed. Commands the user invokes decide when work starts. A worker session has two steps, claiming and starting: `/shingi:claim` stops after the first, so the user can work on the task with that session, and `--start` goes on to the second, taking the first if it hasn't happened. A coordinator session's `/shingi:dispatch` opens a worker at either step, and a plain `koan claim` only reserves.
- **koan and sesshin stay independent.** Neither should know the other exists. shingi depends on both, and neither depends on shingi: the composition lives in one place, as small scripts joined by `jq`.
- **shingi's old job is done.** Its units of work (a koan folder for tasks, a working folder for notes, worktree markers) were built on the original koan. Today's koan has folders with notes and material, and binds worktrees itself.

## Principles

1. **Recipes, not a program.** Each recipe is a shell script plus a README, and usually a skill. No binary, no package, no state of its own.
2. **One-way dependency.** shingi knows koan and sesshin through their JSON contracts. Their docs, code and data never name shingi. A recipe that needs only koan says so and runs without sesshin.
3. **shingi owns the links it makes.** Following "one program, one namespace", a recipe that ties a claim to a session writes under `shingi`: `{"shingi":{"job":"koan-42"}}` on the koan claim. Never a `sesshin` key in koan, or a `koan` key in sesshin. A link no recipe reads isn't written, unless it's data for the user to read back: `uow` marks each unit's folder with `{"shingi":{"uow":{"type":…,"v":1}}}`, so finished work can be studied by type.
4. **Skills wrap scripts, never the reverse.** A skill is a one-line `!` call to its recipe's script plus a few sentences telling the session what to do with the output. The exceptions are `dispatch`, `uow` and `worktree`, whose skills may need to ask the user something first, which a `!` call can't wait for. Their text has the session settle the script's arguments from what the user said and the conversation, using koan's reads to find a folder, ask for what's still missing, and then run the script once. The session never runs a write itself, so the script stays the only thing that changes anything, and its checks still apply. A person, a cron job or another harness can run the same script without Claude Code.
5. **Every recipe states what it needs and what it writes:** the tools and minimum versions, and every `extra` key it reads or writes. Its script checks the versions first, and names the missing tool plainly.
6. **Scripts tell, they don't abort.** A skill's `!` command aborts the whole invocation on a non-zero exit. So a script that runs from a skill exits 0 when koan or sesshin refuses, and prints what happened. A refusal's first line begins `DON'T START:`, which is what the skills look for, or `NOT DONE:` in a recipe that starts no work. A non-zero exit is kept for the script's own bugs and bad usage.
7. **Shell and `jq` only.** POSIX tools, bash, and `jq`. Every script passes shellcheck.
8. **Workers don't complete.** koan describes the work, and the user manages it from a coordinator session. A session using `claim`, dispatched or not, is a worker: it edits its task's notes and reports. The coordinator or the user runs `koan complete`, which breaks Claude's auto mode classifier when a session's working directory is a worktree.

## Layout

```
README.md                         what shingi is, the recipes, what each needs; a History note
recipes-spec.md                   this doc
recipes/
  lib.sh                          shared: refusals, version checks, task IDs
  claim/     README.md  claim.sh
  dispatch/  README.md  dispatch.sh
  worktree/  README.md  worktree.sh
  stale-claims/  README.md  stale-claims.sh
  uow/       README.md  uow.sh
claude/skills/
  claim/SKILL.md                  → /shingi:claim <task> [--start]
  dispatch/SKILL.md               → /shingi:dispatch <task> [--start] [dir]
  worktree/SKILL.md               → /shingi:worktree <folder> [branch] [dir]
  stale-claims/SKILL.md           → /shingi:stale-claims
  uow/SKILL.md                    → /shingi:uow <type> <key> [--in <epic>] [title]
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

### claim: claim a task, and wait or start work

**Usage:** `claim.sh <task> [--start]`, where `<task>` is an ID, `42` or `@42`. Skill: `/shingi:claim <task> [--start]`.

**Needs:** koan v0.13.0 or later, and `jq`. Not sesshin.

**Reads:** the task's claim, and its `extra.shingi.job` when present.

**Writes:** when the task is unclaimed, the claim's `extra`: `{"shingi":{"by":"claude"}}`, plus `"job"` when `SESSHIN_JOB` is set.

**Does, without `--start`:**
1. Check `jq` and `koan version`. On a failure or an old version, print what's wrong and stop (exit 0).
2. `koan claim <task> --extra '<the shingi object>'`. On a failure, print a line for its kind, then koan's envelope, and stop:
   - `conflict`, rule `claimed`: if the claim's `extra.shingi.job` is this session's `SESSHIN_JOB`, it's this session's, as after `dispatch`, so go on. Otherwise "@42 is already claimed: tell the user; if it's this session's, /shingi:claim 42 --start starts work on it";
   - `conflict`, rule `already-complete`: "@42 is complete: it needs reopening first, if the user wants it worked on";
   - any other kind: "Not claimed: tell the user, quoting the message".
3. Print a line naming the task, and where its notes are. A blocked task is claimed, reserved ahead, and the output says what it waits on. It doesn't print the notes, and starts nothing. Refusals begin `NOT DONE:`.

**Does, with `--start`:** refusals begin `DON'T START:`.
1. Check `jq` and `koan version`, as above.
2. `koan show <task>`. On a failure, print koan's envelope, say don't start, and stop. The same when the ID names a folder rather than a task.
3. **Check it can be worked on.** A complete task: print that it needs reopening, and stop. If `SESSHIN_JOB` is set in the environment (sesshin sets it in every session it spawns) and the claim's `extra.shingi.job` is set and differs, print that another session holds it, and stop.
4. **Check it's ready.** If `.result.task.readiness` is `blocked`: print what it waits on, and whether it was claimed, and stop. This comes before claiming, so a task that can't start isn't reserved by accident; a plain claim is how to reserve one ahead.
5. **Claim it** if `.result.task.claim` is null, as in step 2 above. A claim that's already there is left as it is, which is how `/shingi:claim 42` then `/shingi:claim 42 --start` works.
6. **Print the brief**, in this order, each under a plain heading:
   - one line: `START: @42 (/work/api) is claimed: <title>`. `START:` is what tells the skill to start work. koan doesn't record who holds a claim, so this line doesn't say "you";
   - the task's record, as `koan show` printed it;
   - its notes: the file at `.result.task.notes_path`, whole, or `(no notes yet)` when it's missing or empty;
   - its folder's brief: `koan context <folder id> --limit 20`, as printed, unless the task sits in the root (`.result.task.folder.id` is null).
7. **Stay under the output limit.** Claude Code collapses a `!` command's output above about 30,000 characters to a 2KB preview and a file path, which would lose the notes. So the brief keeps to 25,000: when the notes, and then the folder's brief, won't fit, it prints instead where to read them and that they must be read before starting.
8. Exit 0.

**Skill** (`claude/skills/claim/SKILL.md`): a `!` call to `claim.sh` with `$ARGUMENTS`. One skill behaves two ways, so its text goes by the output's first line rather than the session's reading of the arguments: `NOT DONE` or `DON'T START` is reported, `START:` starts work on the task, following its notes, and anything else is reported and then waits for the user, without reading the notes. It gives the worker rules of principle 8 for any work on the task.

### dispatch: claim a task and start a new session for it

**Usage:** `dispatch.sh <task> [--start] [dir] [-- <sesshin spawn options>]`. Without `--start`, the new session waits for the user; with it, the session starts work. Options after `--`, such as `--template opus` or `--type split`, go to `sesshin spawn` as given. Skill: `/shingi:dispatch <task> [--start] [dir]`, which asks which is wanted when it isn't clear.

**Needs:** koan v0.13.0 or later, sesshin 1.2.0 or later with kitty or iTerm2 set up for `spawn`, and `jq`. The new session needs the shingi plugin, installed for the user, not just for a project, so that it has `/shingi:claim`.

**Writes:** the claim's `extra`, `{"shingi":{"by":"dispatch","job":"koan-<id>"}}`, and the session's sesshin job, `koan-<id>`.

**Does:**
1. Check `koan version` and `sesshin version`. Name what's missing or too old, and stop.
2. Work out the ID (`@42` → `42`), the job `koan-42`, and, when `[dir]` is given, the directory, resolved. It must exist.
3. **Check it's ready:** a blocked task prints what it waits on, and stops, so no window opens only to refuse.
4. **Claim first:** `koan claim <id> --extra '{"shingi":{"by":"dispatch","job":"koan-42"}}'`. On a failure, as `claim`'s step 2, and stop. Claiming before spawning means no other agent can take the task while the window opens. The new session's `/shingi:claim` recognises the claim by its job.
5. **Spawn:** `sesshin spawn --job koan-42 [--cwd <dir>] --prompt '/shingi:claim 42[ --start]' [options after --]`. `--cwd` is passed only when `[dir]` is given, so a template's directory, or else the working directory, applies as sesshin's own default. So two dispatches with no `[dir]` share a checkout: give each its own directory until the `worktree` recipe exists.
6. **On a spawn failure**, by sesshin's error:
   - `terminal` with `details.reason` `launch-unknown`: a window may have opened, and sesshin keeps its reservation. Keep the claim, and print "A window may have opened: check with `sesshin focus koan-42`; @42 stays claimed".
   - anything else (`conflict` with `details.rule` `job-taken`, `terminal` with `launch-failed`, `invalid-input`, `not-found` for a template, …): nothing started, so undo the claim with `koan unclaim <id>`, and print sesshin's envelope with "No session started; @42 is unclaimed again".
7. **On success,** print "Dispatched @42 to the session with job koan-42", and sesshin's envelope. A `not-started` warning, meaning the session didn't start within the timeout and is perhaps waiting at Claude's workspace-trust dialog, keeps the claim, and the output says to accept the dialog in the new window.
8. Exit 0.

**The handle:** sesshin selects a session by its job, so `sesshin focus koan-42`, `sesshin show koan-42` and `sesshin send koan-42 --text '…'` reach the session working on @42. sesshin refuses a second live session with that job, which is a second guard beside koan's claim.

**Finishing:** the new session is a worker, by its skill's text and principle 8: it says when it's done or stopped, and the coordinator session or the user completes or unclaims the task. This matches koan's rules for a worker started by a coordinator.

**Skill** (`claude/skills/dispatch/SKILL.md`): text, not a `!` call, since a `!` command runs before the session can ask anything (principle 4). It settles `--start` from the arguments or the conversation, asks the user if neither says, runs the script once, and reports. The session doesn't start work on the task itself.

## Tests

- **Real koan, scratch HOME.** Every test gets its own `HOME`, runs `koan init`, and builds the tasks it needs. CI installs koan at a pinned tag (`go install github.com/phansen314/koan/cmd/koan@v0.14.0`), so a koan release can't break the tests unannounced. The pin moves on purpose.
- **A stub sesshin, with `dispatch`.** `spawn` needs a real terminal, so `tests/stub/sesshin`, put first on `PATH`, records its arguments to a file and prints JSON that each test chooses: success, `job-taken`, `launch-failed`, `launch-unknown`, a `not-started` warning. `version` is stubbed too.
- **What they check:**
  - `claim`: success, loading no notes, its `extra`, a claim under this session's job and under another's, `claimed`, `already-complete`, not found, blocked, and a first line that only says `START:` with `--start`.
  - `claim --start`: unclaimed (claiming it), claimed, a plain claim first, complete, held by another job, blocked with and without a claim, a folder's ID, missing notes, notes over the limit, a task in the root, koan missing or too old.
  - `dispatch`: every branch of step 6, with the claim afterwards held or undone as the step says; the exact `spawn` arguments with and without `--start`, with `--cwd` only when `[dir]` is given; the new session's `claim` accepting the claim, with and without `--start`; options after `--` passed through; a blocked task opening no window.
  - `worktree`: a new and an existing branch, the branch defaulting to the folder's name, the default and an explicit directory, git's status staying clean, each refusal making nothing, and a refused bind removing what was made.
  - `stale-claims`: live, gone and no job, and that it changes nothing.
  - `uow`: what each type makes and its `extra`, the phases or tasks opening one at a time, a task joined later, units in an epic and an epic in an epic, each refusal making nothing, and a refused edge saying what's left.
  - Every script that a skill runs exits 0 on every refusal, and prints the refused tool's envelope.
- **shellcheck** on every script, in CI.
- CI on Linux and macOS, reusing today's workflow's action pins.

## Permissions

A skill's `allowed-tools` pre-approves its own script and nothing else: `Bash(${CLAUDE_PLUGIN_ROOT}/recipes/claim/claim.sh:*)`. What a script runs inside isn't checked, so no rule for `koan`, `sesshin`, `jq` or `cat` is needed to run a recipe. What the session does afterwards, such as `koan complete`, goes by koan's and sesshin's own rules, set by their install scripts.

There's no install script. The old `shingi` permission rules are removed by `scripts/install.sh --uninstall` at `v0.4.0`.

## Settled before building

Checked on Claude Code 2.1.318 with a throwaway plugin:

1. **A slash command as the first prompt** works: `claude '/plugin:skill 42'` in an interactive session runs the skill, as if typed. Seen in a trusted directory.
2. **Placeholders in a `!` command** work: `${CLAUDE_PLUGIN_ROOT}`, `$0` and `$ARGUMENTS` are all filled in, `~` expands, and `-- --template opus` passes through.
3. **`allowed-tools` for a script path** works, with `${CLAUDE_PLUGIN_ROOT}` in the rule. `Bash(koan:*)` and `Bash(*/recipes/x.sh:*)` don't approve the script, and the skill fails with "This command requires approval".
4. **`SESSHIN_JOB`** reaches a `!` command. `CLAUDE_PLUGIN_ROOT` doesn't.
5. **Output over about 30,000 characters** reaches the model as a 2KB preview and a path, which is why `claim --start` has a limit.

Not yet seen: `allowed-tools` approving the `dispatch` script when the session runs it, rather than a `!` command, a real `sesshin spawn`, Claude's workspace-trust dialog in front of the first prompt, and the plugin installed from the marketplace rather than `--plugin-dir`. The end-to-end check below covers them.

## Build order

In vertical slices: the recipes, then removing the Python tool as its own step. Both are done.

## The smaller recipes

Each recipe's README states its usage, needs and writes in full.

- **worktree:** `git worktree add` and `koan bind` together, with `koan context --here` to finish. A refused bind removes the worktree again, and the branch if this run made it. The branch defaults to the folder's name, and the directory to `.claude/worktrees/` in the repository, where Claude Code's `EnterWorktree` can switch to it, which it allows between worktrees only under that directory. Since that's inside the checkout, it adds the directory to `.git/info/exclude` when git doesn't already ignore it. Its path goes to `dispatch`. Its skill settles the folder, perhaps from a key, then runs the script (principle 4).
- **stale-claims:** claims whose `extra.shingi.job` names no live sesshin session, joined with `jq` from `koan task list --claimed` and `sesshin list`, for the user to decide on unclaiming. Claims with no job can't be judged, and are listed apart. It changes nothing.
- **uow:** a unit of work, as the Python tool had, now as a koan folder named for its key and marked with its type under `extra.shingi.uow`, with a template version `v`. The types are built in, with no config: `implementation` has `setup`, `research`, `implementation`, `review` and `cleanup` phase folders with a task joined to each, and each phase's start gate waits on the previous phase's done gate, so the frontier shows only the current phase: if tasks alone waited on the previous phase, all five start gates would be ready at once. A batch can't make an edge between gates, so `koan block` makes them after it. Its setup task's notes say to run `/shingi:worktree <unit>`, for one worktree per unit, which the coordinator or the user does, since a worker changes nothing in koan. `research` is three tasks in order, `Scope`, `Investigate` and `Write up`, and no worktree. `epic` is the folder alone, and `--in <epic>` joins a unit to it, so the epic's gates enclose its units, which run side by side; an implementation's phases are joined to the unit then, so the unit's gates enclose them. Only the type is stored: the key, title, parent and times come from koan, which keeps `extra` in the archive. It completes nothing, gates included (principle 8). Its skill settles the type, key, epic and title from what the user said, asking for a missing type or key and never inventing one, then runs the script (principle 4). A `review` type waits on its phases being settled.

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
- From a real session, `/shingi:claim`, with and without `--start`, and `/shingi:dispatch` each work end to end against your own koan root and kitty or iTerm2.
