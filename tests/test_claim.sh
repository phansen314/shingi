#!/usr/bin/env bash
set -uo pipefail
# shellcheck source=tests/lib.sh
. "$(dirname "$0")/lib.sh"

test_case "claims, says so, and loads nothing"
id=$(new_task 'Fix the thing' --notes secret-notes)
run "$claim" "$id"
exit_is 0
lacks 'NOT DONE'
has "@$id (/) is claimed: Fix the thing"
has "Notes: $(koan show "$id" | jq -r .result.task.notes_path)"
lacks secret-notes
lacks '## Task record'
equals "$(claim_extra "$id")" '{"shingi":{"by":"claude"}}'

test_case "records the job when there is one"
id=$(new_task task)
SESSHIN_JOB=api run "$claim" "@$id"
exit_is 0
lacks 'NOT DONE'
equals "$(claim_extra "$id")" '{"shingi":{"by":"claude","job":"api"}}'

test_case "a claim made under this session's job is this session's"
id=$(new_task task --notes secret-notes)
koan claim "$id" --extra '{"shingi":{"by":"dispatch","job":"koan-1"}}' >/dev/null
SESSHIN_JOB=koan-1 run "$claim" "$id"
exit_is 0
lacks 'NOT DONE'
has "@$id (/) is claimed"
lacks secret-notes
equals "$(claim_extra "$id")" '{"shingi":{"by":"dispatch","job":"koan-1"}}'

test_case "a claim made under another job is refused"
id=$(new_task task)
koan claim "$id" --extra '{"shingi":{"job":"koan-1"}}' >/dev/null
SESSHIN_JOB=other run "$claim" "$id"
stopped
has 'already claimed'

test_case "already claimed is refused, and the claim is untouched"
id=$(new_task task --notes secret-notes)
koan claim "$id" --extra '{"mine":true}' >/dev/null
run "$claim" "$id"
stopped
has 'already claimed'
has "/shingi:claim $id --start"
has '"rule":"claimed"'
lacks secret-notes
equals "$(claim_extra "$id")" '{"mine":true}'

test_case "complete is refused"
id=$(new_task task)
koan complete "$id" >/dev/null
run "$claim" "$id"
stopped
has 'needs reopening'
has '"rule":"already-complete"'

test_case "not found is refused, with koan's envelope"
run "$claim" 999
stopped
has "wasn't claimed"
has '"kind":"not-found"'

test_case "blocked is claimed, reserved ahead, and says so"
first=$(new_task first)
id=$(new_task second --blocked-by "$first" --notes secret-notes)
run "$claim" "$id"
exit_is 0
lacks 'NOT DONE'
has "blocked by @$first"
lacks secret-notes
equals "$(claim_extra "$id")" '{"shingi":{"by":"claude"}}'

test_case "koan missing is refused by name"
only_tools jq
run "$claim" 1
stopped
has "koan isn't on PATH"

test_case "bad usage exits 2"
run "$claim"
exit_is 2
run "$claim" abc
exit_is 2

test_case "--start may come first"
id=$(new_task task --notes body)
run "$claim" --start "$id"
not_refused
has body

test_case "--start's first line says to start, and a plain claim's doesn't"
id=$(new_task task)
run "$claim" "$id"
case $out in
START:*) fail "a plain claim says START" ;;
esac
run "$claim" "$id" --start
case $out in
START:*) ;;
*) fail "expected a first line beginning START:" ;;
esac

test_case "--start: a claimed task prints its record, notes and folder brief, in order"
koan folder create /work >/dev/null
id=$(new_task 'Fix the thing' --folder /work --notes 'the notes body')
koan claim "$id" >/dev/null
run "$claim" "$id" --start
not_refused
has "@$id (/work) is claimed: Fix the thing"
has '## Task record'
has 'the notes body'
has '## Folder brief'
has '"path":"/work"'
case $out in
*'## Task record'*'## Notes'*'the notes body'*'## Folder brief'*) ;;
*) fail "sections out of order" ;;
esac

test_case "--start: @42 works as well as 42"
id=$(new_task task --notes body)
koan claim "$id" >/dev/null
run "$claim" "@$id" --start
not_refused
has body

test_case "--start: a task in the root has no folder brief"
id=$(new_task task --notes body)
koan claim "$id" >/dev/null
run "$claim" "$id" --start
not_refused
lacks '## Folder brief'

test_case "--start: unclaimed is claimed, and prints the brief"
id=$(new_task task --notes body)
run "$claim" "$id" --start
not_refused
has "@$id (/) is claimed: task"
has body
has '"claim":{'
equals "$(claim_extra "$id")" '{"shingi":{"by":"claude"}}'

test_case "--start: unclaimed records the job when there is one"
id=$(new_task task)
SESSHIN_JOB=api run "$claim" "$id" --start
not_refused
equals "$(claim_extra "$id")" '{"shingi":{"by":"claude","job":"api"}}'

test_case "--start: claim, then start, is the same work in two steps"
id=$(new_task task --notes body)
"$claim" "$id" >/dev/null
run "$claim" "$id" --start
not_refused
has body
equals "$(claim_extra "$id")" '{"shingi":{"by":"claude"}}'

test_case "--start: complete is refused"
id=$(new_task task --notes secret-notes)
koan complete "$id" >/dev/null
run "$claim" "$id" --start
refused
has 'needs reopening'
lacks secret-notes

test_case "--start: blocked and unclaimed is refused, and isn't claimed"
first=$(new_task first)
id=$(new_task second --blocked-by "$first" --notes secret-notes)
run "$claim" "$id" --start
refused
has "blocked by @$first"
has "wasn't claimed"
lacks secret-notes
equals "$(claim_extra "$id")" null

test_case "--start: not found is refused, with koan's envelope"
run "$claim" 999 --start
refused
has '"kind":"not-found"'

test_case "--start: a folder's ID is refused"
id=$(koan folder create /work | jq -r .result.id)
run "$claim" "$id" --start
refused
has "isn't a task"

test_case "--start: another job's claim is refused"
id=$(new_task task --notes secret-notes)
koan claim "$id" --extra '{"shingi":{"job":"koan-1"}}' >/dev/null
SESSHIN_JOB=other run "$claim" "$id" --start
refused
has 'job koan-1'
lacks secret-notes

test_case "--start: this job's claim loads"
id=$(new_task task --notes body)
koan claim "$id" --extra '{"shingi":{"job":"koan-1"}}' >/dev/null
SESSHIN_JOB=koan-1 run "$claim" "$id" --start
not_refused
has body

test_case "--start: no job on either side skips the check"
id=$(new_task task --notes body)
koan claim "$id" --extra '{"shingi":{"job":"koan-1"}}' >/dev/null
run "$claim" "$id" --start
not_refused
SESSHIN_JOB=koan-2
export SESSHIN_JOB
other=$(new_task other --notes body)
koan claim "$other" >/dev/null
run "$claim" "$other" --start
not_refused

test_case "--start: blocked is refused, naming the blocker, and stays claimed"
first=$(new_task first)
id=$(new_task second --blocked-by "$first" --notes secret-notes)
koan claim "$id" >/dev/null
run "$claim" "$id" --start
refused
has "blocked by @$first"
has 'stays claimed'
lacks secret-notes
[ "$(claim_extra "$id")" != null ] || fail "the claim went away"

test_case "--start: missing notes say so"
id=$(new_task task --notes body)
koan claim "$id" >/dev/null
rm "$(koan show "$id" | jq -r .result.task.notes_path)"
run "$claim" "$id" --start
not_refused
has '(no notes yet)'

test_case "--start: empty notes say so"
id=$(new_task task)
koan claim "$id" >/dev/null
run "$claim" "$id" --start
not_refused
has '(no notes yet)'

test_case "--start: notes over the limit give their path, and stay under it"
id=$(new_task task)
koan claim "$id" >/dev/null
path=$(koan show "$id" | jq -r .result.task.notes_path)
head -c 40000 /dev/zero | tr '\0' x >"$path"
run "$claim" "$id" --start
not_refused
has "Read $path in full"
lacks xxxxxxxxxx
[ "${#out}" -le 25000 ] || fail "output is ${#out} characters"

test_case "--start: notes that fit are printed whole, however near the limit"
id=$(new_task task)
koan claim "$id" >/dev/null
path=$(koan show "$id" | jq -r .result.task.notes_path)
{ head -c 20000 /dev/zero | tr '\0' x; printf 'THE-END\n'; } >"$path"
run "$claim" "$id" --start
not_refused
has THE-END

test_case "--start: a folder brief over the limit says how to get it, notes first"
koan folder create /work --notes "$(head -c 20000 /dev/zero | tr '\0' y)" >/dev/null
id=$(new_task task --folder /work)
koan claim "$id" >/dev/null
path=$(koan show "$id" | jq -r .result.task.notes_path)
{ head -c 10000 /dev/zero | tr '\0' x; printf 'THE-END\n'; } >"$path"
run "$claim" "$id" --start
not_refused
has THE-END
lacks yyyyyyyyyy
folder=$(koan show "$id" | jq -r .result.task.folder.id)
has "Run koan context $folder --limit 20"
[ "${#out}" -le 25000 ] || fail "output is ${#out} characters"

test_case "--start: koan missing is refused by name"
only_tools jq
run "$claim" 1 --start
refused
has "koan isn't on PATH"

test_case "--start: jq missing is refused by name"
only_tools
run "$claim" 1 --start
refused
has "jq isn't on PATH"

test_case "--start: an old koan is refused by version"
mkdir "$HOME/bin"
printf '#!/usr/bin/env bash\necho %s\n' "'{\"ok\":true,\"result\":{\"version\":\"v0.12.9\"}}'" >"$HOME/bin/koan"
chmod +x "$HOME/bin/koan"
PATH=$HOME/bin:$PATH run "$claim" 1 --start
refused
has 'found v0.12.9'

test_case "--start: a development build's version passes the check"
mkdir "$HOME/bin"
printf '#!/usr/bin/env bash\necho %s\n' "'{\"ok\":true,\"result\":{\"version\":\"(devel)\"}}'" >"$HOME/bin/koan"
chmod +x "$HOME/bin/koan"
PATH=$HOME/bin:$PATH run "$claim" 1 --start
lacks 'v0.13.0 or later'

test_case "--start: bad usage exits 2"
run "$claim" --start
exit_is 2
run "$claim" 1 2 --start
exit_is 2
run "$claim" /work/api --start
exit_is 2

finish
