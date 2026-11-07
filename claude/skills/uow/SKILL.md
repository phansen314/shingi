---
name: uow
description: Scaffold a unit of work in koan, of type epic, implementation or research, perhaps inside an epic, with the type's tasks in order.
disable-model-invocation: true
argument-hint: <epic|implementation|research> <key> [--in <epic>] [title], or say what you want
allowed-tools: Bash(${CLAUDE_PLUGIN_ROOT}/recipes/uow/uow.sh:*), Bash(koan show:*), Bash(koan folder list:*)
---
The user wants a unit of work: `$ARGUMENTS`

Your job is to settle the script's arguments, then run it once. The script makes everything and checks everything; you don't run any koan command that writes.

Settle these, from the arguments and the conversation:

- **type:** `implementation` for a ticket, story, feature or fix: work that changes code, in phases, with a worktree. `research` for a spike, investigation or question to answer, with no worktree. `epic` for a container of several units. If what they said fits more than one, ask.
- **key:** the folder's name, often a ticket key like `ABC-123`. Letters, digits and hyphens only. Use the key they gave; never make one up.
- **epic** (`--in`), optional: only if they want the unit inside an epic. If they name one loosely, find it with `koan folder list --limit null --fields path,title,extra` and look for a folder whose `extra.shingi.uow.type` is `epic`. If none or several fit, ask.
- **title**, optional: what they said the work is, if they said. Don't invent one.

If the type or key is missing or unclear, ask for everything still missing in one message, and wait. Otherwise don't ask for confirmation.

Then run this once, with the title as a single quoted argument after `--`, escaping any quote in it for the shell (`'Fix user'\''s login'`):

```sh
"${CLAUDE_PLUGIN_ROOT}/recipes/uow/uow.sh" <type> <key> [--in <epic>] [-- '<title>']
```

Report what happened in a sentence or two, with the command you ran. If the output begins with NOT DONE, tell the user what it says, and don't run it again with other arguments unless they ask. Don't claim, start or complete anything. Gates are completed by the coordinator session or the user, never claimed, so say that the ready gate is the next step, and that the tasks it opens can then be taken with /shingi:claim or /shingi:dispatch. For an epic, say that units are added to it with --in.
