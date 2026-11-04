# shingi

A small repo of **recipes**: scripts, most with a Claude Code skill around them, that compose [koan](https://github.com/phansen314/koan), [sesshin](https://github.com/phansen314/sesshin) and `jq` through their JSON output. It has no binary, no config and no data of its own, and koan and sesshin don't know it exists.

Linux and macOS only.

## The recipes

| Command | What it does | Needs |
|---|---|---|
| [`/shingi:claim <task>`](recipes/claim/README.md) | Claim a task and start on it in this session, with its notes loaded. | koan |
| [`/shingi:start <task>`](recipes/start/README.md) | Load a task that's already claimed, with its notes, and start on it. | koan |
| [`/shingi:dispatch <task> [dir]`](recipes/dispatch/README.md) | Claim a task and start a new session for it. | koan, sesshin |
| [`/shingi:worktree <folder> <branch> [dir]`](recipes/worktree/README.md) | Add a git worktree and bind it to a koan folder. | koan, git |
| [`/shingi:stale-claims`](recipes/stale-claims/README.md) | List claims whose session is gone, for you to decide on. | koan, sesshin |

Every recipe needs `jq`. koan must be v0.13.0 or later, and sesshin v1.2.0 or later. Each recipe's README says what it reads and writes.

The skills are for you to invoke, so nothing starts work on its own: `/shingi:claim` works here, `/shingi:dispatch` works elsewhere, and a plain `koan claim` reserves a task for later. The scripts run the same way without Claude Code.

## Install

Install koan, sesshin and `jq`, each with its own instructions, then the plugin:

```sh
claude plugin marketplace add phansen314/shingi
claude plugin install shingi@shingi
```

Install it for the user rather than a project, so that the sessions `/shingi:dispatch` opens have `/shingi:start` too.

There's nothing else to set up. A skill pre-approves its own script, and what the script runs inside isn't checked. What a session does afterwards, such as `koan complete`, goes by the permission rules koan's and sesshin's install scripts set.

## Develop

```sh
tests/run.sh       # needs koan on PATH; each test gets a scratch HOME, so your own tasks are safe
shellcheck -x recipes/lib.sh recipes/*/*.sh tests/run.sh tests/lib.sh tests/stub/sesshin tests/test_*.sh
```

[recipes-spec.md](recipes-spec.md) is the design.

## History

shingi was a Python CLI for units of work: a koan folder for each unit's tasks and a working folder for its notes. koan now has folders with notes and material, and binds worktrees itself, so that job is done. The tool and its specs stay in history at the `v0.4.0` tag, its last release.

If you used it, what it left is yours to keep or remove by hand: its tree under `~/shingi-root`, and `/shingi` in koan. Running `scripts/install.sh --uninstall` from a `v0.4.0` checkout removes its permission rules.
