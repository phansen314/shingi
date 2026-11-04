# claim

Claim a task and start work on it in this session, with its notes loaded.

```sh
recipes/claim/claim.sh 42        # or @42
/shingi:claim 42                 # the skill, in Claude Code
```

**Needs:** koan v0.13.0 or later, and `jq`.

**Writes:** the claim's `extra`: `{"shingi":{"by":"claude"}}`, plus `"job"` when `SESSHIN_JOB` is set.

**Prints** what [`start`](../start/README.md) prints, once the claim is made.

**Refuses**, with a first line beginning `DON'T START:`, koan's envelope, and exit 0, when the task is already claimed, is complete, or can't be claimed for any other reason. A blocked task is claimed, which reserves it ahead, and then `start` refuses it, so it stays claimed and isn't started; `koan unclaim` releases it.

Bad usage exits 2.
