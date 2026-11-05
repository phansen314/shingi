#!/usr/bin/env bash
# Scaffolds a ticket in koan: a folder, five phases in order, a task in each.
# See README.md beside this file. Refusals exit 0 and begin NOT DONE.
set -uo pipefail

here=$(cd "$(dirname "$0")" && pwd -P)
# shellcheck source=recipes/lib.sh
. "$here/../lib.sh"

phases=(setup research implementation review cleanup)

[ $# -ge 1 ] || usage "story.sh <ticket-key> [title]"
key=$1
shift
title=$*

say=stop
require_koan || exit 0

# Checked here because a slash would make nested folders that koan accepts.
case $key in
'' | *[!A-Za-z0-9-]*)
	stop "the ticket key $key can hold only letters, digits and hyphens, since it names a folder. Tell the user; nothing was made."
	exit 0
	;;
esac
root=/$key

# jq's output is built apart from the batch, so that a failure here can't look like koan's.
input=$(jq -n --arg root "$root" --arg key "$key" --arg title "$title" '
	[["setup", "Set up"], ["research", "Research"], ["implementation", "Implement"], ["review", "Review"], ["cleanup", "Clean up"]]
	| map({path: "\($root)/\(.[0])", verb: .[1]}) as $phases
	| {
		folders: ([{path: $root} + (if $title == "" then {} else {title: $title} end)] + ($phases | map({path}))),
		tasks: ($phases | map({title: "\(.verb) \($key)", folder: .path, join: [.path]}))
	}')

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
previous=
for phase in "${phases[@]}"; do
	if [ -n "$previous" ] && ! blocked=$(koan block "$root/$phase.start" --blocked-by "$root/$previous" 2>/dev/null); then
		stop "$root and its tasks were made, but $phase doesn't wait on $previous, nor any later phase on the one before it. Tell the user, quoting koan's message: running this again won't fix it, since the folder now exists."
		printf '%s\n' "$blocked"
		exit 0
	fi
	previous=$phase
done

printf 'Scaffolded %s' "$root"
[ -z "$title" ] || printf ': %s' "$title"
printf '\n\n'
jq -r '.result.tasks_made[]' <<<"$made" | {
	for phase in "${phases[@]}"; do
		read -r id
		printf '%-15s @%s\n' "$phase" "$id"
	done
}
printf '\nReady now, a gate to complete when this phase should begin, not a task to claim:\n'
koan frontier "$root" --fields ref,title 2>/dev/null | jq -r '.result.tasks[]? | "\(.ref) \(.title)"'
