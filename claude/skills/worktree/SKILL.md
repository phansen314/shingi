---
name: worktree
description: Add a git worktree in the repository's .claude/worktrees for a branch, named for the koan folder by default, and bind it to that folder.
disable-model-invocation: true
argument-hint: <folder> [branch] [dir], or say which work it's for
allowed-tools: Bash(${CLAUDE_PLUGIN_ROOT}/recipes/worktree/worktree.sh:*), Bash(koan show:*), Bash(koan folder list:*)
---
The user wants a worktree: `$ARGUMENTS`

Your job is to settle the script's arguments, then run it once. The script makes the worktree, binds it and checks everything; you don't run git or any koan command that writes.

Settle these, from the arguments and the conversation:

- **folder:** the koan folder the worktree is for, as its path or ID, such as a unit of work just made with /shingi:uow. If they give only a key like `ABC-123`, find its path with `koan folder list --limit null --fields path,title`, since it may sit inside an epic. If none or several fit, ask.
- **branch** and **dir**, optional: pass them only if the user gave them. The script defaults to a branch named for the folder, in the repository's `.claude/worktrees/`.

The script works on the repository in this session's working directory. If that isn't the repository they mean, say so and stop.

If the folder is unclear, ask, and wait. Otherwise don't ask for confirmation. Then run this once:

```sh
"${CLAUDE_PLUGIN_ROOT}/recipes/worktree/worktree.sh" <folder> [branch] [dir]
```

Report what happened in a sentence or two, with the command you ran. If the output begins with NOT DONE, tell the user what it says, and don't run it again with other arguments unless they ask. If it worked, mention that /shingi:dispatch takes the worktree's path as its directory, and that this session can enter it with EnterWorktree and its path. Don't enter it or start work there unless they ask.
