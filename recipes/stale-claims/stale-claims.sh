#!/usr/bin/env bash
# Lists claims whose job names no live sesshin session. Changes nothing.
# See README.md beside this file. Refusals exit 0 and begin NOT DONE.
set -uo pipefail

here=$(cd "$(dirname "$0")" && pwd -P)
# shellcheck source=recipes/lib.sh
. "$here/../lib.sh"

[ $# -eq 0 ] || usage "stale-claims.sh"

say=stop
require_koan || exit 0
require_sesshin || exit 0

if ! claims=$(koan task list --claimed --limit null --fields ref,title,claim 2>/dev/null); then
	stop "koan couldn't list the claims. Tell the user, quoting koan's message."
	printf '%s\n' "$claims"
	exit 0
fi
# Live includes liveness unknown, so a session that may be alive isn't called stale.
if ! sessions=$(sesshin list --liveness live --include-headless --fields job 2>/dev/null); then
	stop "sesshin couldn't list the sessions. Tell the user, quoting sesshin's message."
	printf '%s\n' "$sessions"
	exit 0
fi

# sesshin treats jobs that differ only in case as the same job.
jq -cn --argjson claims "$claims" --argjson sessions "$sessions" '
	[$sessions.result.sessions[].job | select(. != null) | ascii_downcase] as $live
	| [$claims.result.tasks[]
		| {ref, title, claimed_at: .claim.claimed_at, job: .claim.extra.shingi.job}] as $all
	| {ok: true,
		result: {
			stale: [$all[] | select(.job != null and ((.job | ascii_downcase) as $job | $live | index($job) | not))],
			no_job: [$all[] | select(.job == null) | del(.job)]
		},
		warnings: []}'
