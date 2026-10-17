# shingi

One name and one place for every piece of work. A **unit of work** is a node in a hierarchy (a story, the branches it is split into, a long-lived project), and its path names both its tasks in [koan](https://github.com/phansen314/koan) and its working folder on disk. shingi creates units with a start and a done task, and tells you or your agent where everything for one of them lives. Every command prints one line of JSON, in koan's envelope, so it is built to be driven by an agent such as Claude Code or OpenCode, with `jq` for anything a person reads.

Linux and macOS only.

## Install

Needs Python 3.11 or later (macOS's system Python is too old: use one from uv, Homebrew, or python.org) and [koan](https://github.com/phansen314/koan), on `PATH`. Install shingi into its own environment with either of:

```sh
uv tool install git+https://github.com/phansen314/shingi    # or a clone's path
pipx install git+https://github.com/phansen314/shingi
```

Both put `shingi` in `~/.local/bin`, which must be on `PATH` (`uv tool update-shell` or `pipx ensurepath`). shingi is pinned to the Python it was installed with: if that Python goes away, reinstall (`uv tool install --reinstall …`, `pipx reinstall shingi`).

### Where things live

Nothing needs setting up. The tree is always in the same two places, and the first `shingi create` makes both:

- **`~/shingi-root`:** each unit's working folder, with its `uow.json`, its `uow.md`, and whatever else you keep there. To keep the tree somewhere else, make `~/shingi-root` a symlink to it first.
- **`/shingi` in koan:** each unit's tasks.

### Kinds

A unit's kind is a label for what it is. Two are built in:

- **`group`:** work gathered under one name: a project, a story, an epic, a research phase.
- **`branch`:** work on one branch of one repository.

To define your own, write `shingi.toml` in shingi's config directory: `$XDG_CONFIG_HOME/shingi`, or `~/.config/shingi`, on Linux; `~/Library/Application Support/shingi` on macOS. It replaces the built-in two, so copy them in to keep them:

```toml
schema = 1

[kind.group]
description = "Work gathered under one name: a project, a story, an epic, a research phase."
suggests    = ["group", "branch"]

[kind.branch]
description = "Work on one branch of one repository."
suggests    = []

[kind.spike]
description = "A throwaway experiment."
```

`shingi kinds` shows the kinds in effect. See [The rules file](design-spec.md#the-rules-file) for every field.

### Hooks

To have shingi run a command of yours whenever units are created, adopted, or deleted, write `hooks.json` in the same config directory as `shingi.toml`. Each command fires its own event, so `create-batch` runs a hook once for the whole batch, not `create`'s for each unit:

```json
{
  "schema": 1,
  "hooks": {
    "create": [
      { "command": "~/bin/branch-setup.sh", "description": "Give a branch unit a plan.md from a template" }
    ],
    "create-batch": [
      { "command": "~/bin/branch-setup.sh", "description": "The same, for each unit of a batch" }
    ]
  }
}
```

A hook runs once the command has succeeded, and reads what it did as JSON on stdin: its input, its result, and its warnings. This one gives every new `branch` unit a plan to fill in, reading one unit from `create` and every unit from `create-batch`:

```sh
#!/bin/sh
# branch-setup.sh: give each new branch unit a plan.md, from a template.
jq -c '.result.unit // .result.units[]' | while read -r unit; do
	[ "$(printf '%s' "$unit" | jq -r .kind)" = branch ] || continue
	plan=$(printf '%s' "$unit" | jq -r .working_folder)/plan.md
	[ -e "$plan" ] || cp ~/templates/branch-plan.md "$plan"      # never over one already there
done
```

A hook can't stop a command or change its result: one that fails, or runs past its timeout (10 seconds unless you set `timeout`), is a warning in the command's output. A `hooks.json` shingi can't use, unreadable or with a mistake in it, stops `create`, `adopt`, `create-batch`, and `delete` before they change anything. An agent's `shingi create` runs your hooks too. See the [hooks spec](hooks-spec.md) for every field and rule.

## Use it from Claude Code and OpenCode

The [shingi skill](claude/skills/shingi/SKILL.md) teaches the agent the hierarchy, the kinds, and how to create and coordinate units. Claude Code gets it from the `shingi` plugin (the repo is a Claude Code plugin marketplace):

```sh
claude plugin marketplace add phansen314/shingi
claude plugin install shingi@shingi
```

Then, from a clone of this repo, add the permission rules, which let `where`, `context`, `list`, `kinds`, and `version` run without a prompt while `create`, `adopt`, `create-batch`, and `delete`, which change things, still ask:

```sh
scripts/install.sh               # every agent whose CLI is on PATH
scripts/install.sh --opencode    # or name them: --claude, --opencode
scripts/install.sh --uninstall   # take it all out again
```

It needs `jq`, backs a settings file up (to `.bak.<timestamp>`, a new one each time) before changing it, touches only shingi's rules, and is safe to rerun. Uninstalling leaves the `jq` rule, which koan and sesshin use too. The read commands are allowed by name rather than all of `shingi` at once, so a command added later asks until the script allows it. For OpenCode it also links the skill into `~/.config/opencode/skills/shingi`, so OpenCode's skill comes from this clone: `git pull` updates it. Claude Code's comes from the plugin: `claude plugin update shingi@shingi` picks up changes, or turn on auto-update for the `shingi` marketplace in `/plugin`. To try an edited skill in Claude Code before pushing, run `claude --plugin-dir .` in a clone.

### The rules, to add by hand

Claude Code, in `~/.claude/settings.json`:

```json
{
  "permissions": {
    "allow": ["Bash(shingi where:*)", "Bash(shingi context:*)", "Bash(shingi list:*)", "Bash(shingi kinds:*)", "Bash(shingi version:*)", "Bash(jq:*)"],
    "ask": ["Bash(shingi create:*)", "Bash(shingi adopt:*)", "Bash(shingi create-batch:*)", "Bash(shingi delete:*)"]
  }
}
```

OpenCode, in `~/.config/opencode/opencode.json` (the script leaves an `opencode.jsonc`, or a file with comments, alone, and prints these for you to add). In OpenCode the last matching rule wins, so order matters: these go after any other rule that matches shingi:

```json
{
  "permission": {
    "bash": {
      "shingi where*": "allow",
      "shingi context*": "allow",
      "shingi list*": "allow",
      "shingi kinds*": "allow",
      "shingi version*": "allow",
      "jq *": "allow",
      "shingi create*": "ask",
      "shingi adopt*": "ask",
      "shingi create-batch*": "ask",
      "shingi delete*": "ask"
    }
  }
}
```

For OpenCode, link the skill too: `ln -s "$PWD/claude/skills/shingi" ~/.config/opencode/skills/shingi` from the clone. Not in `~/.claude/skills`: OpenCode reads that as well, and Claude Code would load the skill a second time next to the plugin's.

OpenCode also asks before its file tools touch anything outside the project, which includes a unit's notes, `uow.md`. To let it read and edit notes without asking, add `"external_directory": { "~/shingi-root/*": "allow" }` under `"permission"`.

## Specs

- [design-spec.md](design-spec.md): units, kinds, the rules file, and how shingi fits with koan and sesshin.
- [operations.md](operations.md): every operation's input, output, errors, and warnings.
- [cli-spec.md](cli-spec.md): how commands and options map to operations.
- [hooks-spec.md](hooks-spec.md): hooks, the hooks file, and what a hook is told.
