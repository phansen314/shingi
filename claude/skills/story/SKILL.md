---
name: story
description: Scaffold a ticket in koan, with setup, research, implementation, review and cleanup phases in order and a task in each.
disable-model-invocation: true
argument-hint: <ticket-key> [title]
allowed-tools: Bash(${CLAUDE_PLUGIN_ROOT}/recipes/story/story.sh:*)
---
!`"${CLAUDE_PLUGIN_ROOT}/recipes/story/story.sh" $ARGUMENTS`

Report to the user what happened above, in a sentence or two. Don't claim, start or complete anything. Gates are completed by the coordinator session or the user, never claimed, so say that the ready gate is the next step, and that the phase's task can then be taken with /shingi:claim or /shingi:dispatch.
