---
name: uow
description: Scaffold a unit of work in koan, of type epic, implementation or research, perhaps inside an epic, with the type's tasks in order.
disable-model-invocation: true
argument-hint: <epic|implementation|research> <key> [--in <epic>] [title]
allowed-tools: Bash(${CLAUDE_PLUGIN_ROOT}/recipes/uow/uow.sh:*)
---
!`"${CLAUDE_PLUGIN_ROOT}/recipes/uow/uow.sh" $ARGUMENTS`

Report to the user what happened above, in a sentence or two. Don't claim, start or complete anything. Gates are completed by the coordinator session or the user, never claimed, so say that the ready gate is the next step, and that the tasks it opens can then be taken with /shingi:claim or /shingi:dispatch. For an epic, say that units are added to it with --in.
