---
name: dispatch
description: Claim a koan task and start a new Claude session for it with sesshin, which waits for the user or, with --start, starts work.
disable-model-invocation: true
argument-hint: <task> [--start] [dir] [-- <sesshin spawn options>]
allowed-tools: Bash(${CLAUDE_PLUGIN_ROOT}/recipes/dispatch/dispatch.sh:*)
---
The user wants to dispatch: `$ARGUMENTS`

First settle what the new session does:

- With `--start`, it loads the task's notes and starts work right away.
- Without it, it holds the task and waits, so the user can work on it with that session.

If the arguments include `--start`, or the user has already said which they want, go by that. Otherwise ask them, and don't guess.

Then run this once, with any directory and options the user gave:

```sh
"${CLAUDE_PLUGIN_ROOT}/recipes/dispatch/dispatch.sh" <task> [--start] [dir] [-- <sesshin spawn options>]
```

Report what happened in a sentence or two. If the output begins with DON'T START, tell the user what it says. Don't start work on the task yourself: the new session does that, and you or the user complete it once it reports back.
