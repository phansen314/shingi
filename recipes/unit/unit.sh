#!/usr/bin/env bash
# Scaffolds a unit of work in koan: a folder marked with its type, and the
# type's tasks, perhaps inside an epic. See README.md beside this file.
# Refusals exit 0 and begin NOT DONE.
set -uo pipefail

here=$(cd "$(dirname "$0")" && pwd -P)
# shellcheck source=recipes/lib.sh
. "$here/../lib.sh"

synopsis="unit.sh <epic|implementation|research> <key> [--in <epic>] [title]"
phases=(setup research implementation review cleanup)

[ $# -ge 2 ] || usage "$synopsis"
type=$1
key=$2
shift 2
case $type in
epic | implementation | research) ;;
*) usage "$synopsis" ;;
esac

parent=
words=()
while [ $# -gt 0 ]; do
	case $1 in
	--in)
		[ $# -ge 2 ] && [ -z "$parent" ] || usage "$synopsis"
		parent=$2
		shift 2
		;;
	--)
		shift
		words+=("$@")
		break
		;;
	*)
		words+=("$1")
		shift
		;;
	esac
done
title=${words[*]:-}

say=stop
require_koan || exit 0

# Checked here because a slash would make nested folders that koan accepts.
case $key in
'' | *[!A-Za-z0-9-]*)
	stop "the key $key can hold only letters, digits and hyphens, since it names a folder. Tell the user; nothing was made."
	exit 0
	;;
esac

if [ -n "$parent" ]; then
	if ! shown=$(koan show "$parent" 2>/dev/null) || [ "$(jq -r '.result.folder.path // empty' <<<"$shown")" = "" ]; then
		stop "$parent isn't a folder, so it can't hold the unit. Tell the user; nothing was made."
		printf '%s\n' "$shown"
		exit 0
	fi
	if [ "$(jq -r '.result.folder.extra.shingi.unit.type // empty' <<<"$shown")" != epic ]; then
		stop "$parent isn't an epic, so it can't hold the unit. Make one with /shingi:unit epic <key>. Tell the user; nothing was made."
		exit 0
	fi
	parent=$(jq -r .result.folder.path <<<"$shown")
fi
root=$parent/$key

# jq's output is built apart from the batch, so that a failure here can't look like koan's.
input=$(jq -n --arg type "$type" --arg root "$root" --arg key "$key" --arg title "$title" --arg parent "$parent" '
	def nested: if $parent == "" then {} else {join: [$parent]} end;
	({path: $root, extra: {shingi: {unit: {type: $type, v: 1}}}}
		+ (if $title == "" then {} else {title: $title} end) + nested) as $unit
	| if $type == "epic" then
		{folders: [$unit], tasks: []}
	elif $type == "research" then
		{folders: [$unit], folder: $root, join: [$root], tasks: [
			{label: "$scope", title: "Scope \($key)"},
			{label: "$investigate", title: "Investigate \($key)", blocked_by: ["$scope"]},
			{title: "Write up \($key)", blocked_by: ["$investigate"],
				notes: "Write the findings in this task'"'"'s notes, for the coordinator or the user to read.\n"}]}
	else
		[["setup", "Set up"], ["research", "Research"], ["implementation", "Implement"], ["review", "Review"], ["cleanup", "Clean up"]]
		| map({path: "\($root)/\(.[0])", verb: .[1]}) as $phases
		| {
			folders: ([$unit] + ($phases | map({path} + (if $parent == "" then {} else {join: [$root]} end)))),
			tasks: ($phases | map({title: "\(.verb) \($key)", folder: .path, join: [.path]}
				+ (if .verb == "Set up" then {notes: "Make the worktree for this unit. The coordinator session or the user runs /shingi:worktree \($root) from the repository, which makes the branch \($key) in .claude/worktrees/\($key) and binds it to \($root). A worker can'"'"'t do this, since it changes nothing in koan: report that it needs doing.\n"} else {} end)))
		}
	end')

if ! made=$(koan batch -i - 2>/dev/null <<<"$input"); then
	if jq -e '.ok == false' >/dev/null 2>&1 <<<"$made"; then
		stop "koan refused the scaffold, so nothing was made. Tell the user, quoting koan's message."
	else
		stop "koan's outcome is unknown. Run koan show $root before trying again, and tell the user."
	fi
	printf '%s\n' "$made"
	exit 0
fi

# A batch can't make an edge between gates, so these follow it, one by one.
if [ "$type" = implementation ]; then
	previous=
	for phase in "${phases[@]}"; do
		if [ -n "$previous" ] && ! blocked=$(koan block "$root/$phase.start" --blocked-by "$root/$previous" 2>/dev/null); then
			stop "$root and its tasks were made, but $phase doesn't wait on $previous, nor any later phase on the one before it. Tell the user, quoting koan's message: running this again won't fix it, since the folder now exists."
			printf '%s\n' "$blocked"
			exit 0
		fi
		previous=$phase
	done
fi

printf 'Scaffolded %s, a unit of type %s' "$root" "$type"
[ -z "$title" ] || printf ': %s' "$title"
printf '\n'

if [ "$type" = epic ]; then
	printf '\nAdd units to it with /shingi:unit <type> <key> --in %s. They run side by side, unless one is made to wait on another with koan block.\n' "$root"
	exit 0
fi

printf '\n'
jq -r --argjson made "$made" '[.tasks, $made.result.tasks_made] | transpose[] | "@\(.[1])  \(.[0].title)"' <<<"$input"

# Inside an epic, what's ready may be the epic's own gate.
scope=${parent:-$root}
ready=$(koan frontier "$scope" --fields ref,title 2>/dev/null | jq -r '.result.tasks[]? | "\(.ref) \(.title)"')
if [ -n "$ready" ]; then
	printf '\nReady now under %s, a gate to complete when that work should begin, not a task to claim:\n%s\n' "$scope" "$ready"
else
	printf '\nNothing under %s is ready yet: it waits on work outside it.\n' "$scope"
fi
