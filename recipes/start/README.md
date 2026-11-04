# start

Load a claimed task, with its notes, and start work on it.

```sh
recipes/start/start.sh 42        # or @42
/shingi:start 42                 # the skill, in Claude Code
```

**Needs:** koan v0.13.0 or later, and `jq`.

**Reads:** the task's claim, and its `extra.shingi.job` when present. **Writes:** nothing.

**Prints**, in order: a line naming the task, its record from `koan show`, its notes file, and `koan context` for its folder unless it sits in the root. Notes or a folder's brief that would take the output past 25,000 characters are replaced by where to read them, since Claude Code collapses longer output to a preview.

**Refuses**, with a first line beginning `DON'T START:` and exit 0, when the task isn't found, isn't claimed, is blocked, or is claimed under a different job than this session's `SESSHIN_JOB`. The job check is skipped when either is unset, and a claim doesn't say who made it, so a session with no job can load any claimed task.

Bad usage exits 2.
