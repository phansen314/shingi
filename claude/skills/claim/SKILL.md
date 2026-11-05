---
name: claim
description: Claim a koan task for this session and wait, or with --start, load its notes and start work on it.
disable-model-invocation: true
argument-hint: <task> [--start]
allowed-tools: Bash(${CLAUDE_PLUGIN_ROOT}/recipes/claim/claim.sh:*)
---
!`"${CLAUDE_PLUGIN_ROOT}/recipes/claim/claim.sh" $ARGUMENTS`

Go by how the output above begins:

- `NOT DONE` or `DON'T START`: don't start. Tell the user what it says.
- `START:`: start work on the task now, following its notes, and keep its notes file up to date as you go.
- Anything else: the task is claimed and nothing more. Tell the user in a sentence or two, then stop and wait for them. Don't start work on it, or read its notes, until they ask.

Whenever you work on the task, you're a worker: don't run `koan complete` or `koan unclaim`, and don't change anything in koan but this task's notes. When it's done, or you stop early, say so, with any follow-ups, and the coordinator session or the user will take it from there.
