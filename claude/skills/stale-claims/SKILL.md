---
name: stale-claims
description: List koan claims whose sesshin session is gone, for the user to decide on unclaiming.
disable-model-invocation: true
allowed-tools: Bash(${CLAUDE_PLUGIN_ROOT}/recipes/stale-claims/stale-claims.sh:*)
---
!`"${CLAUDE_PLUGIN_ROOT}/recipes/stale-claims/stale-claims.sh"`

Show the user the stale claims above, and the claims with no job, which can't be judged, separately. A session still waiting at a workspace-trust dialog also shows as stale. Don't unclaim anything unless the user says which.
