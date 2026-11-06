# claim

Claim a task for this session. On its own it does nothing more, and the session waits for you, so you can work on the task with it. With `--start`, it also loads the task's notes and starts work.

```sh
recipes/claim/claim.sh 42            # or @42: claim, and wait
recipes/claim/claim.sh 42 --start    # claim if need be, and start work
/shingi:claim 42                     # the skill, in Claude Code
/shingi:claim 42 --start
```

You can take the steps one at a time: `/shingi:claim 42`, then `/shingi:claim 42 --start` in the same session when you're ready.

**Needs:** koan v0.13.0 or later, and `jq`.

**Reads:** the task's claim, and its `extra.shingi.job` when present. **Writes:** when the task is unclaimed, the claim's `extra`: `{"shingi":{"by":"claude"}}`, plus `"job"` when `SESSHIN_JOB` is set.

**Prints:** a line naming the task, and where its notes are. It doesn't load them. A blocked task is claimed, which reserves it ahead, and the output says what it waits on.

**Prints with `--start`:** a first line beginning `START:` and naming the task, its record from `koan show`, its notes file, and `koan context` for its folder unless it sits in the root. Notes or a folder's brief that would take the output past 25,000 characters are replaced by where to read them, since Claude Code collapses longer output to a preview.

**A session's own claim:** a claim already made under this session's `SESSHIN_JOB` counts as success and is left as it is. That's how a session from [`dispatch`](../dispatch/README.md), which claims first, runs this.

**Refuses**, with exit 0:

- Without `--start`, with a first line beginning `NOT DONE:` and koan's envelope, when the task is claimed by anything else, is complete, or can't be claimed for any other reason.
- With `--start`, with a first line beginning `DON'T START:`, when the task isn't found, is complete, is blocked, or is claimed under a different job than this session's `SESSHIN_JOB`. A blocked task it refuses isn't claimed, and one that was claimed stays so. The job check is skipped when either is unset, and a claim doesn't say who made it, so a session with no job can start any claimed task.

Bad usage exits 2.
