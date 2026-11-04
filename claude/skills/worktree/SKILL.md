---
name: worktree
description: Add a git worktree for a branch and bind it to a koan folder.
disable-model-invocation: true
argument-hint: <folder> <branch> [dir]
allowed-tools: Bash(${CLAUDE_PLUGIN_ROOT}/recipes/worktree/worktree.sh:*)
---
!`"${CLAUDE_PLUGIN_ROOT}/recipes/worktree/worktree.sh" $ARGUMENTS`

Report to the user what happened above, in a sentence or two. If it worked, mention that /shingi:dispatch takes the worktree's path as its directory. Don't start work there yourself.
