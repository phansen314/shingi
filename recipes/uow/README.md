# uow

Scaffold a unit of work in koan: a folder named for its key, marked with its type, holding the type's tasks in order. An epic holds other units. It starts nothing and completes nothing. You work through the tasks from a coordinator session, with [`claim`](../claim/README.md) and [`dispatch`](../dispatch/README.md).

```sh
recipes/uow/uow.sh implementation ABC-123 'Fix the login bug'
recipes/uow/uow.sh epic PAY-1 'Payments rework'
recipes/uow/uow.sh research PAY-2 --in /PAY-1 'Which gateway'
/shingi:uow implementation ABC-123 'Fix the login bug'    # the skill, in Claude Code
/shingi:uow a research spike PAY-2 under the payments epic   # or say it, and the session settles the arguments
```

The title is optional, and becomes the folder's title. In the skill, you can give the arguments as above or say what you want: the session works out the type, key, epic and title, asks for a missing type or key, and runs the script once. It never makes up a key or a title.

## The types

**implementation:** five phase folders that run in order, with one task in each.

```
/ABC-123
  /setup           Set up ABC-123
  /research        Research ABC-123
  /implementation  Implement ABC-123
  /review          Review ABC-123
  /cleanup         Clean up ABC-123
```

Each task is joined to its phase, and each phase's start gate waits on the previous phase's done gate, so `koan frontier /ABC-123` shows only the current phase. A task you add later with `--join /ABC-123/research` falls into the same order. The setup task's notes say to run [`/shingi:worktree /ABC-123`](../worktree/README.md), which makes one worktree for the whole unit, on the branch `ABC-123`, in the repository's `.claude/worktrees/ABC-123`. Every phase's worker can share it. The coordinator session or you run it, because a worker changes nothing in koan.

Outside an epic, the unit's folder has no gates of its own, since nothing joins the phases to it: the first gate is `/ABC-123/setup.start`, and the unit is done when `/ABC-123/cleanup` is. Inside an epic, the phases are joined to the unit, so it has `.start` and `.done` gates that enclose them.

**research:** three tasks in the unit's folder, one after another, and no worktree: `Scope`, `Investigate` and `Write up`. The write-up's notes ask for the findings there. The tasks are joined to the unit, so it has `.start` and `.done` gates, in or out of an epic.

**epic:** the folder alone. Add units to it with `--in`.

## Epics

`--in <epic>` puts the unit inside an epic, which is named by its path or ID and must be one, not just any folder. The unit is joined to the epic: it waits on the epic's start gate, and the epic's done gate waits on it. An implementation unit's phases are joined to the unit in turn, so its gates enclose them. The units of an epic run side by side; to order two, `koan block /PAY-1/PAY-3.start --blocked-by /PAY-1/PAY-2`. An epic may hold an epic.

## The type is data

The unit's folder gets `extra.shingi.uow`, `{"type": "implementation", "v": 1}`, where `v` is the version of the type's template. Nothing else is stored: the key is the folder's name, the title is its title, a unit's epic is the nearest folder above it with a unit of type `epic`, and the times are its tasks'. koan keeps `extra` when work is archived, so finished units can be read back, say for feedback on how each type goes:

```sh
koan folder list --limit null --fields path,title,extra,open,complete | jq '.result.folders[] | select(.extra.shingi.uow)'
```

**Completing:** koan doesn't complete gates by itself. The coordinator or you complete them, and each start gate is the point to decide whether that work should begin.

**Needs:** koan v0.14.0 or later, and `jq`. Not sesshin.

**Writes:** the folders, tasks and gates above, and `extra.shingi.uow` on the unit's folder.

**Prints:** the unit, each task's ID, and what's ready now under the unit: its first gate. In an epic that hasn't started, that's the epic's start gate instead. Other units' work in the epic isn't listed.

**Refuses**, with a first line beginning `NOT DONE:`, koan's envelope where it refused, and exit 0, when the key holds anything but letters, digits and hyphens, `--in` names no folder or one that isn't an epic, or koan refuses the batch, for instance because the folder exists. Nothing is made then. A batch can't make an edge between gates, so an implementation's phase edges follow it: if one fails, the folders and tasks stay, and the output says which edge is missing.

An unknown type, or `--in` given twice or with nothing after it, is bad usage, which exits 2.
