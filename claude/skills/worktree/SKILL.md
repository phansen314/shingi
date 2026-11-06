---
name: worktree
description: Add a git worktree in the repository's .claude/worktrees for a branch, named for the koan folder by default, and bind it to that folder.
disable-model-invocation: true
argument-hint: <folder> [branch] [dir]
allowed-tools: Bash(${CLAUDE_PLUGIN_ROOT}/recipes/worktree/worktree.sh:*)
---
!`"${CLAUDE_PLUGIN_ROOT}/recipes/worktree/worktree.sh" $ARGUMENTS`

Report to the user what happened above, in a sentence or two. If it worked, mention that /shingi:dispatch takes the worktree's path as its directory, and that this session can enter it with EnterWorktree and its path. Don't enter it or start work there unless they ask.
