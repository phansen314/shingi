# stale-claims

List koan claims whose job names no live sesshin session, for you to decide on unclaiming. It changes nothing.

```sh
recipes/stale-claims/stale-claims.sh
/shingi:stale-claims                    # the skill, in Claude Code
```

**Needs:** koan v0.14.0 or later, sesshin v1.2.0 or later, and `jq`.

**Reads:** each claim's `extra.shingi.job`, and the job of each live session. **Writes:** nothing.

**Prints** an envelope: `.result.stale`, each with `ref`, `title`, `claimed_at` and `job`; and `.result.no_job`, claims with no job, which can't be judged, such as a plain `koan claim` or `/shingi:claim` outside a sesshin job.

A session of unknown liveness counts as live. A session that hasn't started yet, such as one waiting at Claude's workspace-trust dialog, isn't in `sesshin list`, so it shows as stale.

**Refuses**, with a first line beginning `NOT DONE:` and exit 0, when a tool is missing or fails. Bad usage exits 2.
