#!/usr/bin/env bash
set -uo pipefail
# shellcheck source=tests/lib.sh
. "$(dirname "$0")/lib.sh"

# frontier: the refs of what's ready under /ABC-123, space-separated.
frontier() {
	koan frontier /ABC-123 --fields ref | jq -r '[.result.tasks[].ref | sub("^@[0-9]+ "; "")] | join(" ")'
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
run "$story" ABC-123 Fix the login bug
exit_is 0
lacks 'NOT DONE'
has 'Scaffolded /ABC-123: Fix the login bug'
equals "$(koan show /ABC-123 | jq -r .result.folder.title)" 'Fix the login bug'
for phase in setup research implementation review cleanup; do
	koan show "/ABC-123/$phase" >/dev/null || fail "no folder for $phase"
done
equals "$(koan show "$(phase_task setup)" | jq -r .result.task.title)" 'Set up ABC-123'
equals "$(koan show "$(phase_task research)" | jq -r .result.task.title)" 'Research ABC-123'
equals "$(koan show "$(phase_task implementation)" | jq -r .result.task.title)" 'Implement ABC-123'
equals "$(koan show "$(phase_task review)" | jq -r .result.task.title)" 'Review ABC-123'
equals "$(koan show "$(phase_task cleanup)" | jq -r .result.task.title)" 'Clean up ABC-123'
has "setup           @$(phase_task setup)"
has "cleanup         @$(phase_task cleanup)"
has '/ABC-123/setup.start'
has 'a gate to complete'

test_case "the title is optional, and may hold shell characters"
run "$story" ABC-1
exit_is 0
equals "$(koan show /ABC-1 | jq -r .result.folder.title)" null
run "$story" ABC-2 "it's \$HOME"
exit_is 0
equals "$(koan show /ABC-2 | jq -r .result.folder.title)" "it's \$HOME"

test_case "completes nothing, and the phases open one at a time, in order"
"$story" ABC-123 >/dev/null
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
"$story" ABC-123 >/dev/null
late=$(new_task 'Read the logs' --folder /ABC-123/research --join /ABC-123/research)
equals "$(koan show "$late" | jq -r .result.task.readiness)" blocked
equals "$(frontier)" "(/ABC-123/setup.start)"

test_case "an existing folder refuses, and changes nothing"
"$story" ABC-123 >/dev/null
before=$(koan task list /ABC-123 --limit 1 --fields id | jq -r .result.total)
run "$story" ABC-123
stopped
has '"rule":"exists"'
equals "$(koan task list /ABC-123 --limit 1 --fields id | jq -r .result.total)" "$before"

test_case "a key that can't name one folder refuses, and makes nothing"
for key in A/B ../x 'a b' a.start ''; do
	run "$story" "$key"
	stopped
done
equals "$(koan folder list --limit 1 --fields id | jq -r .result.total)" 0
equals "$(koan task list --limit 1 --fields id | jq -r .result.total)" 0

test_case "a title koan refuses makes nothing"
run "$story" ABC-123 "$(printf 'one\ntwo')"
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
PATH=$scratch/refuse:$PATH run "$story" ABC-123
stopped
has "research doesn't wait on setup"
has '"kind":"busy"'
koan show /ABC-123 >/dev/null || fail "the folder should stay"

test_case "koan missing"
only_tools jq
run "$story" ABC-123
stopped
has "koan isn't on PATH"

test_case "bad usage exits 2"
run "$story"
exit_is 2

finish
