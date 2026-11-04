# dispatch

Claim a task and start a new Claude session for it.

```sh
recipes/dispatch/dispatch.sh 42                          # in the working directory
recipes/dispatch/dispatch.sh 42 ~/code/api-feature       # in that directory
recipes/dispatch/dispatch.sh 42 -- --template opus       # options for sesshin spawn
/shingi:dispatch 42 ~/code/api-feature                   # the skill, in Claude Code
```

**Needs:** koan v0.13.0 or later, sesshin v1.2.0 or later with kitty or iTerm2 set up for `spawn`, and `jq`. The new session needs the shingi plugin, installed for the user rather than a project, so that it has `/shingi:start`.

**Writes:** the claim's `extra`, `{"shingi":{"by":"dispatch","job":"koan-42"}}`, and the session's sesshin job, `koan-42`.

**The handle:** `sesshin focus koan-42`, `sesshin show koan-42` and `sesshin send koan-42 --text '…'` reach the session.

**The directory:** `--cwd` is passed only when you give one, so a template's directory applies otherwise, and then the working directory. Two dispatches with no directory share a checkout, so give each its own, such as one from [`worktree`](../worktree/README.md).

**Refuses**, with a first line beginning `DON'T START:` and exit 0, and with no window opened, when the task is blocked, already claimed, complete or not found, or the directory isn't there. A blocked task isn't claimed.

**When spawn fails:** the claim is undone, since nothing started. The exception is `launch-unknown`, when a window may have opened: the claim stays and the output says how to check. A `not-started` warning keeps the claim too, and the session may be waiting at Claude's workspace-trust dialog.

Bad usage exits 2.
