---
name: claim
description: Claim a koan task and start work on it in this session, with its notes loaded.
disable-model-invocation: true
argument-hint: <task>
allowed-tools: Bash(${CLAUDE_PLUGIN_ROOT}/recipes/claim/claim.sh:*)
---
!`"${CLAUDE_PLUGIN_ROOT}/recipes/claim/claim.sh" $0`

If the output above begins with DON'T START, don't start: tell the user what it says. Otherwise start work on the task now, following its notes, and keep its notes file up to date as you go. You're a worker: don't run `koan complete` or `koan unclaim`, and don't change anything in koan but this task's notes. When it's done, or you stop early, say so, with any follow-ups, and the coordinator session or the user will take it from there.
