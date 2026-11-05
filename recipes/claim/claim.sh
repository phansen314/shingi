#!/usr/bin/env bash
# Claims a task and says so. With --start, it also prints the brief to start work
# from: the task's record, its notes, its folder's brief.
# See README.md beside this file. Refusals exit 0, and begin NOT DONE, or DON'T START
# with --start.
set -uo pipefail

here=$(cd "$(dirname "$0")" && pwd -P)
# shellcheck source=recipes/lib.sh
. "$here/../lib.sh"

# Claude Code collapses a !command's output above about 30,000 characters to a
# 2KB preview, which would lose the notes.
limit=25000

text="claim.sh <task> [--start], where <task> is an ID, 42 or @42"
id=
start=
for arg in "$@"; do
	case $arg in
	--start) start=1 ;;
	*)
		[ -z "$id" ] || usage "$text"
		id=$(task_id "$arg") || usage "$text"
		;;
	esac
done
[ -n "$id" ] || usage "$text"

if [ -z "$start" ]; then
	say=stop
	require_koan || exit 0
	claim_here "$id" || exit 0

	show=$(koan show "$id" 2>/dev/null)
	jq -r '.result.task | "\(.ref) is claimed: \(.title)\nNotes: \(.notes_path)"' <<<"$show"
	if [ "$(jq -r .result.task.readiness <<<"$show")" = blocked ]; then
		printf 'It is blocked by %s, so it is reserved ahead, and --start refuses it until then.\n' \
			"$(jq -r '[.result.task.blocked_by[] | select(.state == "open") | .ref] | join(", ")' <<<"$show")"
	fi
	exit 0
fi

require_koan || exit 0

if ! show=$(koan show "$id" 2>/dev/null); then
	refuse "@$id wasn't loaded. Tell the user, quoting koan's message."
	printf '%s\n' "$show"
	exit 0
fi
if ! jq -e '.result.task' >/dev/null <<<"$show"; then
	refuse "@$id isn't a task. Tell the user."
	printf '%s\n' "$show"
	exit 0
fi

field() {
	jq -r ".result.task | $1" <<<"$show"
}

ref=$(field .ref)

if [ "$(field .state)" = complete ]; then
	refuse "$ref is complete. It needs reopening first, if the user wants it worked on."
	exit 0
fi

holder=$(field '.claim.extra.shingi.job // empty')
if [ -n "${SESSHIN_JOB:-}" ] && [ -n "$holder" ] && [ "$holder" != "$SESSHIN_JOB" ]; then
	refuse "$ref is held by the session with job $holder, and this one's job is $SESSHIN_JOB. Tell the user."
	exit 0
fi

# Before claiming: nothing can start, so nothing should be reserved.
if [ "$(field .readiness)" = blocked ]; then
	if [ "$(field .claim)" = null ]; then
		held="It wasn't claimed."
	else
		held="It stays claimed."
	fi
	refuse "$ref is blocked by $(field '[.blocked_by[] | select(.state == "open") | .ref] | join(", ")'). $held Tell the user."
	exit 0
fi

if [ "$(field .claim)" = null ]; then
	claim_here "$id" || exit 0
	show=$(koan show "$id" 2>/dev/null)
fi

# START: is what tells the skill to start work.
header="START: $ref is claimed: $(field .title)"
used=$((${#header} + ${#show}))

printf '%s\n\n## Task record\n\n%s\n\n## Notes\n\n' "$header" "$show"

notes_path=$(field .notes_path)
notes=$(cat "$notes_path" 2>/dev/null)
if [ -z "$notes" ]; then
	printf '(no notes yet)\n'
elif [ $((used + ${#notes})) -le "$limit" ]; then
	printf '%s\n' "$notes"
	used=$((used + ${#notes}))
else
	printf '(Too long to print here, at %s characters. Read %s in full before you start.)\n' "${#notes}" "$notes_path"
fi

folder=$(field '.folder.id // empty')
if [ -n "$folder" ]; then
	context=$(koan context "$folder" --limit 20 2>/dev/null)
	printf '\n## Folder brief\n\n'
	if [ $((used + ${#context})) -le "$limit" ]; then
		printf '%s\n' "$context"
	else
		printf '(Too long to print here. Run koan context %s --limit 20 and read it before you start.)\n' "$folder"
	fi
fi
