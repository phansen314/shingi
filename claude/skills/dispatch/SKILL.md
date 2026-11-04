---
name: dispatch
description: Claim a koan task and start a new Claude session for it with sesshin.
disable-model-invocation: true
argument-hint: <task> [dir] [-- <sesshin spawn options>]
allowed-tools: Bash(${CLAUDE_PLUGIN_ROOT}/recipes/dispatch/dispatch.sh:*)
---
!`"${CLAUDE_PLUGIN_ROOT}/recipes/dispatch/dispatch.sh" $ARGUMENTS`

Report to the user what happened above, in a sentence or two. Don't start work on the task yourself: the new session does that.
