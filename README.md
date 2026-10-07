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

### The rules file

shingi reads its roots and kinds from `shingi.toml` in its config directory: `$XDG_CONFIG_HOME/shingi`, or `~/.config/shingi`, on Linux; `~/Library/Application Support/shingi` on macOS. There is no `init`; write it by hand, for example:

```toml
schema = 1

[roots]
koan    = "/work"      # a koan folder only shingi uses
working = "~/work"     # must already exist

[kind.group]
description = "Work gathered under one name: a project, a story, an epic, a research phase."
suggests    = ["group", "branch"]

[kind.branch]
description = "Work on one branch of one repository."
suggests    = []
```

`shingi kinds` reads it and nothing else, so it is the quick check. See [The rules file](design-spec.md#the-rules-file) for every field.

## Use it from Claude Code and OpenCode

The [shingi skill](claude/skills/shingi/SKILL.md) teaches the agent the hierarchy, the kinds, and how to create and coordinate units. Claude Code gets it from the `shingi` plugin (the repo is a Claude Code plugin marketplace):

```sh
claude plugin marketplace add phansen314/shingi
claude plugin install shingi@shingi
```

Then, from a clone of this repo, add the permission rules, which let `where`, `context`, `list`, `kinds`, and `version` run without a prompt while `create` and `adopt`, which change things, still ask:

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
    "ask": ["Bash(shingi create:*)", "Bash(shingi adopt:*)"]
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
      "shingi adopt*": "ask"
    }
  }
}
```

For OpenCode, link the skill too: `ln -s "$PWD/claude/skills/shingi" ~/.config/opencode/skills/shingi` from the clone. Not in `~/.claude/skills`: OpenCode reads that as well, and Claude Code would load the skill a second time next to the plugin's.

OpenCode also asks before its file tools touch anything outside the project, which includes a unit's notes, `uow.md`. To let it read and edit notes without asking, add your working root, for example `"external_directory": { "~/work/*": "allow" }` under `"permission"`.

## Specs

- [design-spec.md](design-spec.md): units, kinds, the rules file, and how shingi fits with koan and sesshin.
- [operations.md](operations.md): every operation's input, output, errors, and warnings.
- [cli-spec.md](cli-spec.md): how commands and options map to operations.
