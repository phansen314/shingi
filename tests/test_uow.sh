#!/usr/bin/env bash
set -uo pipefail
# shellcheck source=tests/lib.sh
. "$(dirname "$0")/lib.sh"

# frontier_of FOLDER: the refs of what's ready under FOLDER, space-separated.
frontier_of() {
	koan frontier "$1" --fields ref | jq -r '[.result.tasks[].ref | sub("^@[0-9]+ "; "")] | join(" ")'
}

frontier() {
	frontier_of /ABC-123
}

# complete_ref REF: completes the task or gate that REF names.
complete_ref() {
	koan complete "$(koan where "$1" | jq -r .result.id)" >/dev/null
}

# phase_task PHASE: the ID of the phase's own task.
phase_task() {
	koan task list "/ABC-123/$1" --direct --fields gate --limit null | jq -r '[.result.tasks[] | select(.gate == null)][0].id'
}

test_case "makes the folder, the phases and a task in each"
run "$uow" implementation ABC-123 Fix the login bug
exit_is 0
lacks 'NOT DONE'
has 'Scaffolded /ABC-123, a unit of type implementation: Fix the login bug'
equals "$(koan show /ABC-123 | jq -r .result.folder.title)" 'Fix the login bug'
equals "$(koan show /ABC-123 | jq -c .result.folder.extra)" '{"shingi":{"uow":{"type":"implementation","v":1}}}'
equals "$(koan show /ABC-123/setup | jq -c .result.folder.extra)" '{}'
for phase in setup research implementation review cleanup; do
	koan show "/ABC-123/$phase" >/dev/null || fail "no folder for $phase"
done
equals "$(koan show "$(phase_task setup)" | jq -r .result.task.title)" 'Set up ABC-123'
equals "$(koan show "$(phase_task research)" | jq -r .result.task.title)" 'Research ABC-123'
equals "$(koan show "$(phase_task implementation)" | jq -r .result.task.title)" 'Implement ABC-123'
equals "$(koan show "$(phase_task review)" | jq -r .result.task.title)" 'Review ABC-123'
equals "$(koan show "$(phase_task cleanup)" | jq -r .result.task.title)" 'Clean up ABC-123'
has "@$(phase_task setup)  Set up ABC-123"
has "@$(phase_task cleanup)  Clean up ABC-123"
has '/ABC-123/setup.start'
has 'a gate to complete'

test_case "only the setup task's notes say how to make the worktree"
"$uow" implementation ABC-123 >/dev/null
setup_notes=$(cat "$(koan show "$(phase_task setup)" | jq -r .result.task.notes_path)")
out=$setup_notes
has '/shingi:worktree /ABC-123'
has '.claude/worktrees/ABC-123'
out=$(cat "$(koan show "$(phase_task research)" | jq -r .result.task.notes_path)" 2>/dev/null)
lacks '/shingi:worktree'

test_case "the title is optional, and may hold shell characters"
run "$uow" implementation ABC-1
exit_is 0
equals "$(koan show /ABC-1 | jq -r .result.folder.title)" null
run "$uow" implementation ABC-2 "it's \$HOME"
exit_is 0
equals "$(koan show /ABC-2 | jq -r .result.folder.title)" "it's \$HOME"

test_case "completes nothing, and the phases open one at a time, in order"
"$uow" implementation ABC-123 >/dev/null
equals "$(koan task list /ABC-123 --state complete --limit 1 --fields id | jq -r .result.total)" 0
for phase in setup research implementation review cleanup; do
	equals "$(frontier)" "(/ABC-123/$phase.start)"
	complete_ref "/ABC-123/$phase.start"
	equals "$(frontier)" "(/ABC-123/$phase)"
	koan complete "$(phase_task "$phase")" >/dev/null
	equals "$(frontier)" "(/ABC-123/$phase.done)"
	complete_ref "/ABC-123/$phase.done"
done
equals "$(frontier)" ""
equals "$(koan show /ABC-123 | jq -r .result.folder.finished)" true

test_case "a task joined later waits in the phase's order"
"$uow" implementation ABC-123 >/dev/null
late=$(new_task 'Read the logs' --folder /ABC-123/research --join /ABC-123/research)
equals "$(koan show "$late" | jq -r .result.task.readiness)" blocked
equals "$(frontier)" "(/ABC-123/setup.start)"

test_case "an existing folder refuses, and changes nothing"
"$uow" implementation ABC-123 >/dev/null
before=$(koan task list /ABC-123 --limit 1 --fields id | jq -r .result.total)
run "$uow" implementation ABC-123
stopped
has '"rule":"exists"'
equals "$(koan task list /ABC-123 --limit 1 --fields id | jq -r .result.total)" "$before"

test_case "a key that can't name one folder refuses, and makes nothing"
for key in A/B ../x 'a b' a.start ''; do
	run "$uow" implementation "$key"
	stopped
done
equals "$(koan folder list --limit 1 --fields id | jq -r .result.total)" 0
equals "$(koan task list --limit 1 --fields id | jq -r .result.total)" 0

test_case "a title koan refuses makes nothing"
run "$uow" implementation ABC-123 "$(printf 'one\ntwo')"
stopped
has '"ok":false'
equals "$(koan folder list --limit 1 --fields id | jq -r .result.total)" 0

test_case "a refused edge says what's left, and keeps what was made"
mkdir -p "$scratch/refuse"
real_koan=$(command -v koan)
cat >"$scratch/refuse/koan" <<EOF
#!/usr/bin/env bash
if [ "\$1" = block ]; then
	printf '%s\n' '{"ok":false,"error":{"kind":"busy","message":"held"},"warnings":[]}'
	exit 1
fi
exec "$real_koan" "\$@"
EOF
chmod +x "$scratch/refuse/koan"
PATH=$scratch/refuse:$PATH run "$uow" implementation ABC-123
stopped
has "research doesn't wait on setup"
has '"kind":"busy"'
koan show /ABC-123 >/dev/null || fail "the folder should stay"

test_case "research: three tasks in the unit's folder, one after another"
run "$uow" research R-1 Why is it slow
exit_is 0
lacks 'NOT DONE'
equals "$(koan show /R-1 | jq -c .result.folder.extra)" '{"shingi":{"uow":{"type":"research","v":1}}}'
equals "$(koan folder list /R-1 --limit 1 --fields id | jq -r .result.total)" 0
equals "$(koan task list /R-1 --fields gate,title --limit null | jq -r '[.result.tasks[] | select(.gate == null) | .title] | join(",")')" 'Scope R-1,Investigate R-1,Write up R-1'
for step in Scope Investigate 'Write up'; do
	ready=$(koan frontier /R-1 --fields title | jq -r '[.result.tasks[].title] | join(",")')
	case $ready in
	Start) koan complete /R-1.start >/dev/null ;;
	esac
	id=$(koan frontier /R-1 --fields title | jq -r '.result.tasks[0].id')
	equals "$(koan show "$id" | jq -r .result.task.title)" "$step R-1"
	koan complete "$id" >/dev/null
done
equals "$(frontier_of /R-1)" "(/R-1.done)"
out=$(cat "$(koan task list /R-1 --state open,complete --fields title,notes_path --limit null | jq -r '.result.tasks[] | select(.title == "Write up R-1") | .notes_path')")
has 'findings'

test_case "epic: a marked folder and nothing else"
run "$uow" epic BIG-1 Payments rework
exit_is 0
has 'Scaffolded /BIG-1, a unit of type epic: Payments rework'
has '--in /BIG-1'
equals "$(koan show /BIG-1 | jq -c .result.folder.extra)" '{"shingi":{"uow":{"type":"epic","v":1}}}'
equals "$(koan task list --limit 1 --fields id | jq -r .result.total)" 0

test_case "units in an epic wait on its start, and its done waits on them"
"$uow" epic BIG-1 >/dev/null
run "$uow" implementation ABC-1 --in /BIG-1 Fix login
exit_is 0
has 'Scaffolded /BIG-1/ABC-1, a unit of type implementation: Fix login'
has '/BIG-1.start'
"$uow" research R-1 --in "$(koan show /BIG-1 | jq -r .result.folder.id)" >/dev/null
koan show /BIG-1/R-1 >/dev/null || fail "--in should take the epic's ID too"
equals "$(frontier_of /BIG-1)" "(/BIG-1.start)"
complete_ref /BIG-1.start
equals "$(frontier_of /BIG-1)" "(/BIG-1/ABC-1.start) (/BIG-1/R-1.start)"
complete_ref /BIG-1/ABC-1.start
equals "$(frontier_of /BIG-1/ABC-1)" "(/BIG-1/ABC-1/setup.start)"
equals "$(koan show /BIG-1.done | jq -r '[.result.task.blocked_by[].ref | sub("^@[0-9]+ "; "")] | sort | join(" ")')" "(/BIG-1/ABC-1.done) (/BIG-1/R-1.done)"
equals "$(koan show /BIG-1/ABC-1.done | jq -r '.result.task.blocked_by | length')" 5

test_case "an epic may hold an epic"
"$uow" epic BIG-1 >/dev/null
run "$uow" epic BIG-2 --in /BIG-1
exit_is 0
equals "$(koan show /BIG-1.done | jq -r '.result.task.blocked_by[0].ref | sub("^@[0-9]+ "; "")')" "(/BIG-1/BIG-2.done)"

test_case "--in refuses what isn't an epic, and makes nothing"
"$uow" implementation ABC-1 >/dev/null
koan folder create /plain >/dev/null
before=$(koan folder list --limit 1 --fields id | jq -r .result.total)
for where in /ABC-1 /plain /nope "$(new_task loose)"; do
	run "$uow" research R-1 --in "$where"
	stopped
done
equals "$(koan folder list --limit 1 --fields id | jq -r .result.total)" "$before"

test_case "an unknown type, or --in twice or bare, is bad usage"
for args in "bogus X" "story X" "research R-1 --in /a --in /b" "research R-1 --in"; do
	# shellcheck disable=SC2086 # split on purpose
	run "$uow" $args
	exit_is 2
done

test_case "koan missing"
only_tools jq
run "$uow" implementation ABC-123
stopped
has "koan isn't on PATH"

test_case "bad usage exits 2"
run "$uow"
exit_is 2

finish
