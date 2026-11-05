# shellcheck shell=bash
# Shared by the recipes: refusals, version checks, task IDs. Sourced, never run.

# refuse MESSAGE: the first line of everything a skill must not start work on.
refuse() {
	printf "DON'T START: %s\n" "$1"
}

# stop MESSAGE: the first line when a recipe that starts no work couldn't do its job.
stop() {
	printf 'NOT DONE: %s\n' "$1"
}

# usage TEXT: bad usage is the one thing that exits non-zero (recipes-spec.md, principle 6).
usage() {
	printf 'usage: %s\n' "$1" >&2
	exit 2
}

# version_at_least HAVE WANT: true when HAVE is WANT or later. A version that
# isn't numeric, such as a development build's, counts as new enough.
version_at_least() {
	local have=${1#v} want=${2#v} h1 h2 h3 w1 w2 w3
	have=${have%%-*}
	case $have in
	[0-9]*.[0-9]*.[0-9]*) ;;
	*) return 0 ;;
	esac
	case $have in
	*[!0-9.]*) return 0 ;;
	esac
	IFS=. read -r h1 h2 h3 <<<"$have"
	IFS=. read -r w1 w2 w3 <<<"$want"
	[ "$h1" -gt "$w1" ] && return 0
	[ "$h1" -lt "$w1" ] && return 1
	[ "$h2" -gt "$w2" ] && return 0
	[ "$h2" -lt "$w2" ] && return 1
	[ "$h3" -ge "$w3" ]
}

# require_koan: true when jq and a new enough koan are here; else prints what isn't,
# through refuse, or through the function a recipe that starts no work names in $say.
require_koan() {
	local version
	if ! command -v jq >/dev/null; then
		"${say:-refuse}" "jq isn't on PATH. Tell the user to install it."
		return 1
	fi
	if ! command -v koan >/dev/null; then
		"${say:-refuse}" "koan isn't on PATH. Tell the user to install v0.13.0 or later."
		return 1
	fi
	version=$(koan version 2>/dev/null | jq -r '.result.version // empty' 2>/dev/null)
	if [ -z "$version" ]; then
		"${say:-refuse}" "koan version didn't report a version. Tell the user."
		return 1
	fi
	if ! version_at_least "$version" 0.13.0; then
		"${say:-refuse}" "this needs koan v0.13.0 or later, and found $version. Tell the user."
		return 1
	fi
}

# require_sesshin: true when a new enough sesshin is here; else prints what isn't.
# Call it after require_koan, which checks jq.
require_sesshin() {
	local version
	if ! command -v sesshin >/dev/null; then
		"${say:-refuse}" "sesshin isn't on PATH. Tell the user to install v1.2.0 or later."
		return 1
	fi
	version=$(sesshin version 2>/dev/null | jq -r '.result.version // empty' 2>/dev/null)
	if [ -z "$version" ]; then
		"${say:-refuse}" "sesshin version didn't report a version. Tell the user."
		return 1
	fi
	if ! version_at_least "$version" 1.2.0; then
		"${say:-refuse}" "this needs sesshin v1.2.0 or later, and found $version. Tell the user."
		return 1
	fi
}

# task_id WORD: prints the ID in 42 or @42; false for anything else.
task_id() {
	local id=${1#@}
	case $id in
	'' | *[!0-9]*) return 1 ;;
	esac
	printf '%s' "$id"
}

# claim_here ID: true when this session holds the task's claim, just made, or made
# earlier under its SESSHIN_JOB, as dispatch does; else prints why, and koan's envelope.
claim_here() {
	local id=$1 extra claimed holder
	extra=$(jq -nc --arg job "${SESSHIN_JOB:-}" \
		'{shingi: ({by: "claude"} + (if $job == "" then {} else {job: $job} end))}')
	if claimed=$(koan claim "$id" --extra "$extra" 2>/dev/null); then
		return 0
	fi
	case $(jq -r '[.error.kind, .error.rule] | join("/")' 2>/dev/null <<<"$claimed") in
	conflict/claimed)
		holder=$(koan show "$id" 2>/dev/null | jq -r '.result.task.claim.extra.shingi.job // empty' 2>/dev/null)
		if [ -n "${SESSHIN_JOB:-}" ] && [ "$holder" = "$SESSHIN_JOB" ]; then
			return 0
		fi
		"${say:-refuse}" "@$id is already claimed. Tell the user; if it's this session's, /shingi:claim $id --start starts work on it."
		;;
	conflict/already-complete)
		"${say:-refuse}" "@$id is complete. It needs reopening first, if the user wants it worked on."
		;;
	*)
		"${say:-refuse}" "@$id wasn't claimed. Tell the user, quoting koan's message."
		;;
	esac
	printf '%s\n' "$claimed"
	return 1
}
