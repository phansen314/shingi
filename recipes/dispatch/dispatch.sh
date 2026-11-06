#!/usr/bin/env bash
# Claims a task and starts a new Claude session for it through sesshin.
# See README.md beside this file. Refusals exit 0 and begin DON'T START.
set -uo pipefail

here=$(cd "$(dirname "$0")" && pwd -P)
# shellcheck source=recipes/lib.sh
. "$here/../lib.sh"

text="dispatch.sh <task> [--start] [dir] [-- <sesshin spawn options>]"
[ $# -ge 1 ] || usage "$text"
id=$(task_id "$1") || usage "$text"
shift

prompt="/shingi:claim $id"
dir=
while [ $# -ge 1 ] && [ "$1" != -- ]; do
	case $1 in
	--start) prompt="/shingi:claim $id --start" ;;
	-*) usage "$text" ;;
	*)
		[ -z "$dir" ] || usage "$text"
		dir=$1
		;;
	esac
	shift
done
if [ $# -ge 1 ]; then
	shift
fi

require_koan || exit 0
require_sesshin || exit 0

job=koan-$id

# --cwd only when asked for, so a template's directory still applies.
cwd=()
if [ -n "$dir" ]; then
	if ! resolved=$(cd "$dir" 2>/dev/null && pwd -P); then
		refuse "$dir isn't a directory. Tell the user. @$id wasn't claimed."
		exit 0
	fi
	cwd=(--cwd "$resolved")
fi

# Blocked: no window opens only to refuse.
if ! show=$(koan show "$id" 2>/dev/null); then
	refuse "@$id wasn't dispatched. Tell the user, quoting koan's message."
	printf '%s\n' "$show"
	exit 0
fi
if ! jq -e '.result.task' >/dev/null <<<"$show"; then
	refuse "@$id isn't a task. Tell the user."
	printf '%s\n' "$show"
	exit 0
fi
if [ "$(jq -r .result.task.readiness <<<"$show")" = blocked ]; then
	blockers=$(jq -r '[.result.task.blocked_by[] | select(.state == "open") | .ref] | join(", ")' <<<"$show")
	refuse "@$id is blocked by $blockers. It wasn't claimed, and no session started. Tell the user."
	exit 0
fi

extra=$(jq -nc --arg job "$job" '{shingi: {by: "dispatch", job: $job}}')
if ! claimed=$(koan claim "$id" --extra "$extra" 2>/dev/null); then
	case $(jq -r '[.error.kind, .error.rule] | join("/")' 2>/dev/null <<<"$claimed") in
	conflict/claimed)
		refuse "@$id is already claimed, and no session started. Tell the user."
		;;
	conflict/already-complete)
		refuse "@$id is complete, and no session started. It needs reopening first, if the user wants it worked on."
		;;
	*)
		refuse "@$id wasn't claimed, and no session started. Tell the user, quoting koan's message."
		;;
	esac
	printf '%s\n' "$claimed"
	exit 0
fi

# ${a[@]+...}: an empty array is an unset variable to macOS's bash 3.2.
spawned=$(sesshin spawn --job "$job" ${cwd[@]+"${cwd[@]}"} --prompt "$prompt" "$@" 2>/dev/null)
status=$?

if [ "$status" -ne 0 ]; then
	if [ "$(jq -r '.error.details.reason // empty' 2>/dev/null <<<"$spawned")" = launch-unknown ]; then
		refuse "A window may have opened: check with sesshin focus $job. @$id stays claimed."
	elif koan unclaim "$id" >/dev/null 2>&1; then
		refuse "No session started; @$id is unclaimed again."
	else
		refuse "No session started, and @$id couldn't be unclaimed, so it's still claimed. Tell the user."
	fi
	printf '%s\n' "$spawned"
	exit 0
fi

printf 'Dispatched @%s to the session with job %s, whose first prompt is %s.\n' "$id" "$job" "$prompt"
if jq -e '.warnings | any(.kind == "not-started")' >/dev/null 2>&1 <<<"$spawned"; then
	printf "The session hasn't started yet. It may be waiting at Claude's workspace-trust dialog: accept it in the new window. @%s stays claimed.\n" "$id"
fi
printf '%s\n' "$spawned"
