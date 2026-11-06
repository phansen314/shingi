# story

Scaffold a ticket in koan: a folder named for its key, five phase folders that run in order, and one task in each. It starts nothing and completes nothing. You work through the tasks from a coordinator session, with [`claim`](../claim/README.md) and [`dispatch`](../dispatch/README.md).

```sh
recipes/story/story.sh ABC-123 'Fix the login bug'
/shingi:story ABC-123 'Fix the login bug'             # the skill, in Claude Code
```

The title is optional, and becomes the folder's title. Quote it in the skill if it holds an apostrophe or other shell characters.

```
/ABC-123
  /setup           Set up ABC-123
  /research        Research ABC-123
  /implementation  Implement ABC-123
  /review          Review ABC-123
  /cleanup         Clean up ABC-123
```

**Order:** each task is joined to its phase, so it waits on the phase's start gate, and the done gate waits on it. Each start gate waits on the previous phase's done gate, so `koan frontier /ABC-123` shows only the current phase. A task you add later with `--join /ABC-123/research` falls into the same order.

**The worktree:** the setup task's notes say to run [`/shingi:worktree /ABC-123`](../worktree/README.md), which makes one worktree for the whole ticket, on the branch `ABC-123`, in the repository's `.claude/worktrees/ABC-123`. Every phase's worker can share it, since the phases run in order. The coordinator session or you run it, because a worker changes nothing in koan.

**Completing:** koan doesn't complete gates by itself, so a phase takes three completions: its start gate, its task and its done gate. The coordinator or you make them. The start gate is the point to decide whether a phase should begin.

**Needs:** koan v0.13.0 or later, and `jq`. Not sesshin.

**Writes:** the folders, tasks and gates above. No `extra`.

**Prints:** the folder, each phase's task ID, and what's ready now.

**Refuses**, with a first line beginning `NOT DONE:`, koan's envelope where it refused, and exit 0, when the key holds anything but letters, digits and hyphens, or koan refuses the batch, for instance because the folder exists. Nothing is made then. A batch can't make an edge between gates, so those edges follow it: if one fails, the folders and tasks stay, and the output says which edge is missing.

Bad usage exits 2.
