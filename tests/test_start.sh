#!/usr/bin/env bash
set -uo pipefail
# shellcheck source=tests/lib.sh
. "$(dirname "$0")/lib.sh"

test_case "a claimed task prints its record, notes and folder brief, in order"
koan folder create /work >/dev/null
id=$(new_task 'Fix the thing' --folder /work --notes 'the notes body')
koan claim "$id" >/dev/null
run "$start" "$id"
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

test_case "@42 works as well as 42"
id=$(new_task task --notes body)
koan claim "$id" >/dev/null
run "$start" "@$id"
not_refused
has body

test_case "a task in the root has no folder brief"
id=$(new_task task --notes body)
koan claim "$id" >/dev/null
run "$start" "$id"
not_refused
lacks '## Folder brief'

test_case "unclaimed is refused, and points at claim"
id=$(new_task task --notes secret-notes)
run "$start" "$id"
refused
has "/shingi:claim $id"
lacks secret-notes

test_case "not found is refused, with koan's envelope"
run "$start" 999
refused
has '"kind":"not-found"'

test_case "a folder's ID is refused"
id=$(koan folder create /work | jq -r .result.id)
run "$start" "$id"
refused
has "isn't a task"

test_case "another job's claim is refused"
id=$(new_task task --notes secret-notes)
koan claim "$id" --extra '{"shingi":{"job":"koan-1"}}' >/dev/null
SESSHIN_JOB=other run "$start" "$id"
refused
has 'job koan-1'
lacks secret-notes

test_case "this job's claim loads"
id=$(new_task task --notes body)
koan claim "$id" --extra '{"shingi":{"job":"koan-1"}}' >/dev/null
SESSHIN_JOB=koan-1 run "$start" "$id"
not_refused
has body

test_case "no job on either side skips the check"
id=$(new_task task --notes body)
koan claim "$id" --extra '{"shingi":{"job":"koan-1"}}' >/dev/null
run "$start" "$id"
not_refused
SESSHIN_JOB=koan-2
export SESSHIN_JOB
other=$(new_task other --notes body)
koan claim "$other" >/dev/null
run "$start" "$other"
not_refused

test_case "blocked is refused, naming the blocker, and stays claimed"
first=$(new_task first)
id=$(new_task second --blocked-by "$first" --notes secret-notes)
koan claim "$id" >/dev/null
run "$start" "$id"
refused
has "blocked by @$first"
has 'stays claimed'
lacks secret-notes
[ "$(claim_extra "$id")" != null ] || fail "the claim went away"

test_case "missing notes say so"
id=$(new_task task --notes body)
koan claim "$id" >/dev/null
rm "$(koan show "$id" | jq -r .result.task.notes_path)"
run "$start" "$id"
not_refused
has '(no notes yet)'

test_case "empty notes say so"
id=$(new_task task)
koan claim "$id" >/dev/null
run "$start" "$id"
not_refused
has '(no notes yet)'

test_case "notes over the limit give their path, and stay under it"
id=$(new_task task)
koan claim "$id" >/dev/null
path=$(koan show "$id" | jq -r .result.task.notes_path)
head -c 40000 /dev/zero | tr '\0' x >"$path"
run "$start" "$id"
not_refused
has "Read $path in full"
lacks xxxxxxxxxx
[ "${#out}" -le 25000 ] || fail "output is ${#out} characters"

test_case "notes that fit are printed whole, however near the limit"
id=$(new_task task)
koan claim "$id" >/dev/null
path=$(koan show "$id" | jq -r .result.task.notes_path)
{ head -c 20000 /dev/zero | tr '\0' x; printf 'THE-END\n'; } >"$path"
run "$start" "$id"
not_refused
has THE-END

test_case "a folder brief over the limit says how to get it, notes first"
koan folder create /work --notes "$(head -c 20000 /dev/zero | tr '\0' y)" >/dev/null
id=$(new_task task --folder /work)
koan claim "$id" >/dev/null
path=$(koan show "$id" | jq -r .result.task.notes_path)
{ head -c 10000 /dev/zero | tr '\0' x; printf 'THE-END\n'; } >"$path"
run "$start" "$id"
not_refused
has THE-END
lacks yyyyyyyyyy
folder=$(koan show "$id" | jq -r .result.task.folder.id)
has "Run koan context $folder --limit 20"
[ "${#out}" -le 25000 ] || fail "output is ${#out} characters"

test_case "koan missing is refused by name"
only_tools jq
run "$start" 1
refused
has "koan isn't on PATH"

test_case "jq missing is refused by name"
only_tools
run "$start" 1
refused
has "jq isn't on PATH"

test_case "an old koan is refused by version"
mkdir "$HOME/bin"
printf '#!/usr/bin/env bash\necho %s\n' "'{\"ok\":true,\"result\":{\"version\":\"v0.12.9\"}}'" >"$HOME/bin/koan"
chmod +x "$HOME/bin/koan"
PATH=$HOME/bin:$PATH run "$start" 1
refused
has 'found v0.12.9'

test_case "a development build's version passes the check"
mkdir "$HOME/bin"
printf '#!/usr/bin/env bash\necho %s\n' "'{\"ok\":true,\"result\":{\"version\":\"(devel)\"}}'" >"$HOME/bin/koan"
chmod +x "$HOME/bin/koan"
PATH=$HOME/bin:$PATH run "$start" 1
lacks 'v0.13.0 or later'

test_case "bad usage exits 2"
run "$start"
exit_is 2
run "$start" 1 2
exit_is 2
run "$start" /work/api
exit_is 2

finish
