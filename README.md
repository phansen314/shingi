# shingi

One file, `shingi.toml`, declares where a story's work belongs on this machine: its tasks in [koan](https://github.com/phansen314/koan), under a folder per phase, and its working files in a workspace, a directory named by the story's key. `shingi init JIRA-12345` creates both, and `shingi where` tells you or your agent every path, so nobody rebuilds one by hand. shingi runs only when asked: no hooks, no daemon, no state of its own. Every command prints one line of JSON, in koan's envelope, for `jq` and agents.

Linux and macOS only.

**Status: spec only.** [design-spec.md](design-spec.md) is the design; nothing is built yet, so the commands below describe what is planned. v1 is `where`, `init`, and `version`, with a skill for Claude Code and OpenCode.

## What you need

| | When | Why |
|---|---|---|
| **koan**, a supported version, on `PATH` | Always | shingi creates and finds tasks through koan's CLI. |
| **Python 3.11 or later** | Always | For `tomllib`. macOS's system Python is too old: use one from uv, Homebrew, or python.org. |
| **uv** or **pipx** | To install | Either one. Not needed to run shingi. |
| **Network access** | The first install | shingi has no dependencies outside the standard library, but building the package fetches its build backend from PyPI. An offline install works only once that is cached. |
| **git** | Optional | To find a session's story from its branch name. Without it, that source is skipped. |
| **jq** | To run `scripts/install.sh` | It edits your agents' settings files with it, as koan's does. |
| **The `claude` CLI** | To install the Claude Code skill | For `claude plugin marketplace add` and `claude plugin install`. |
| **sesshin** | Optional | Never run. A session spawned with `sesshin spawn --job JIRA-12345-research` names its story through `SESSHIN_JOB`. |

## Install

shingi isn't on PyPI. Install it from a clone, or from the repository:

```sh
uv tool install ~/code/shingi                                    # from a clone
uv tool install git+https://github.com/phansen314/shingi        # or from GitHub
pipx install ~/code/shingi                                       # or with pipx
```

Both put `shingi` in `~/.local/bin`. If that isn't on your `PATH`, `uv tool update-shell` or `pipx ensurepath` adds it to your shell profile. It has to be on the `PATH` of the shell your agent runs commands in, too: a session `sesshin spawn` starts gets a login shell, so a profile entry reaches it.

Then write the rules to `~/.config/shingi/shingi.toml` (`~/Library/Application Support/shingi/shingi.toml` on macOS). [The rules file](design-spec.md#the-rules-file) has a full example.

### When `shingi` stops running

uv and pipx tie `shingi` to the Python that installed it. If that Python is removed or upgraded away (a uv-managed Python cleaned up, Homebrew moving to a new version), `shingi` fails to start until it is reinstalled:

```sh
uv tool install --reinstall ~/code/shingi
pipx reinstall shingi
```

### Upgrading

`git pull` in the clone, then reinstall as above. An upgrade replaces the installed copy, so change shingi's behavior in `shingi.toml`, and its code only in the clone.

## Use it from Claude Code and OpenCode

The shingi skill teaches the agent the layout, to ask `where` instead of composing a path, and to mark a story's task in progress with `koan update <id> --extra-merge '{"status":"in-progress"}'`. You invoke it to start a story. Claude Code gets it from the `shingi` plugin (the repo is a Claude Code plugin marketplace). Until it is published, add the marketplace from a clone:

```sh
claude plugin marketplace add ~/code/shingi
claude plugin install shingi@shingi
```

Then, from the clone, add the permission rules, which let `where` and `version` run without a prompt while `init`, which creates a story, still asks:

```sh
scripts/install.sh               # every agent whose CLI is on PATH
scripts/install.sh --opencode    # or name them: --claude, --opencode
scripts/install.sh --uninstall   # take it all out again
```

It backs a settings file up (to `.bak.<timestamp>`) before changing it, touches only shingi's rules, and is safe to rerun. For OpenCode it also links the skill into `~/.config/opencode/skills/shingi`, so `git pull` updates it. A plugin can't add permission rules itself, which is why this is a separate step.

### The rules, to add by hand

Claude Code, in `~/.claude/settings.json`:

```json
{
  "permissions": {
    "allow": ["Bash(shingi where:*)", "Bash(shingi version:*)"],
    "ask": ["Bash(shingi init:*)"]
  }
}
```

OpenCode, in `~/.config/opencode/opencode.json`, after any other rule that matches shingi, since the last matching rule wins:

```json
{
  "permission": {
    "bash": {
      "shingi where*": "allow",
      "shingi version*": "allow",
      "shingi init*": "ask"
    }
  }
}
```

For OpenCode, link the skill too: `ln -s "$PWD/claude/skills/shingi" ~/.config/opencode/skills/shingi` from the clone.

## Documents

| Document | What it covers |
|---|---|
| [design-spec.md](design-spec.md) | What shingi is for, the rules file, keys, the layout, finding a session's story, and each command's contract. |
