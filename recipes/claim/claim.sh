#!/usr/bin/env bash
# Claims a task, then prints its brief through start.sh.
# See README.md beside this file. Refusals exit 0 and begin DON'T START.
set -uo pipefail

here=$(cd "$(dirname "$0")" && pwd -P)
# shellcheck source=recipes/lib.sh
. "$here/../lib.sh"

[ $# -eq 1 ] || usage "claim.sh <task>"
id=$(task_id "$1") || usage "claim.sh <task>, where <task> is an ID, 42 or @42"

require_koan || exit 0

extra=$(jq -nc --arg job "${SESSHIN_JOB:-}" \
	'{shingi: ({by: "claude"} + (if $job == "" then {} else {job: $job} end))}')

if ! claimed=$(koan claim "$id" --extra "$extra" 2>/dev/null); then
	case $(jq -r '[.error.kind, .error.rule] | join("/")' 2>/dev/null <<<"$claimed") in
	conflict/claimed)
		refuse "@$id is already claimed. Tell the user; if it's this session's, /shingi:start $id loads it."
		;;
	conflict/already-complete)
		refuse "@$id is complete. It needs reopening first, if the user wants it worked on."
		;;
	*)
		refuse "@$id wasn't claimed. Tell the user, quoting koan's message."
		;;
	esac
	printf '%s\n' "$claimed"
	exit 0
fi

"$here/../start/start.sh" "$id"
