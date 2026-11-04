# shellcheck shell=bash
# Shared by the recipes: refusals, version checks, task IDs. Sourced, never run.

# refuse MESSAGE: the first line of everything a skill must not start work on.
refuse() {
	printf "DON'T START: %s\n" "$1"
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

# require_koan: true when jq and a new enough koan are here; else prints what isn't.
require_koan() {
	local version
	if ! command -v jq >/dev/null; then
		refuse "jq isn't on PATH. Tell the user to install it."
		return 1
	fi
	if ! command -v koan >/dev/null; then
		refuse "koan isn't on PATH. Tell the user to install v0.13.0 or later."
		return 1
	fi
	version=$(koan version 2>/dev/null | jq -r '.result.version // empty' 2>/dev/null)
	if [ -z "$version" ]; then
		refuse "koan version didn't report a version. Tell the user."
		return 1
	fi
	if ! version_at_least "$version" 0.13.0; then
		refuse "this needs koan v0.13.0 or later, and found $version. Tell the user."
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
