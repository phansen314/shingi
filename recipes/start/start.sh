#!/usr/bin/env bash
# Prints a claimed task's brief: its record, its notes, its folder's brief.
# See README.md beside this file. Refusals exit 0 and begin DON'T START.
set -uo pipefail

here=$(cd "$(dirname "$0")" && pwd -P)
# shellcheck source=recipes/lib.sh
. "$here/../lib.sh"

# Claude Code collapses a !command's output above about 30,000 characters to a
# 2KB preview, which would lose the notes.
limit=25000

[ $# -eq 1 ] || usage "start.sh <task>"
id=$(task_id "$1") || usage "start.sh <task>, where <task> is an ID, 42 or @42"

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

if [ "$(field .claim)" = null ]; then
	refuse "$ref isn't claimed. Tell the user, who can run /shingi:claim $id."
	exit 0
fi

holder=$(field '.claim.extra.shingi.job // empty')
if [ -n "${SESSHIN_JOB:-}" ] && [ -n "$holder" ] && [ "$holder" != "$SESSHIN_JOB" ]; then
	refuse "$ref is held by the session with job $holder, and this one's job is $SESSHIN_JOB. Tell the user."
	exit 0
fi

if [ "$(field .readiness)" = blocked ]; then
	refuse "$ref is blocked by $(field '[.blocked_by[] | select(.state == "open") | .ref] | join(", ")'). It stays claimed. Tell the user."
	exit 0
fi

header="$ref is claimed: $(field .title)"
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
