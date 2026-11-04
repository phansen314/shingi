#!/usr/bin/env bash
set -uo pipefail
# shellcheck source=tests/lib.sh
. "$(dirname "$0")/lib.sh"

test_case "claims, and prints the brief"
id=$(new_task 'Fix the thing' --notes 'the notes body')
run "$claim" "$id"
not_refused
has "@$id (/) is claimed: Fix the thing"
has 'the notes body'
equals "$(claim_extra "$id")" '{"shingi":{"by":"claude"}}'

test_case "records the job when there is one"
id=$(new_task task)
SESSHIN_JOB=api run "$claim" "@$id"
not_refused
equals "$(claim_extra "$id")" '{"shingi":{"by":"claude","job":"api"}}'

test_case "already claimed is refused, and the claim is untouched"
id=$(new_task task --notes secret-notes)
koan claim "$id" --extra '{"mine":true}' >/dev/null
run "$claim" "$id"
refused
has 'already claimed'
has "/shingi:start $id"
has '"rule":"claimed"'
lacks secret-notes
equals "$(claim_extra "$id")" '{"mine":true}'

test_case "complete is refused"
id=$(new_task task)
koan complete "$id" >/dev/null
run "$claim" "$id"
refused
has 'needs reopening'
has '"rule":"already-complete"'

test_case "not found is refused, with koan's envelope"
run "$claim" 999
refused
has "wasn't claimed"
has '"kind":"not-found"'

test_case "blocked is claimed, reserved ahead, and not started"
first=$(new_task first)
id=$(new_task second --blocked-by "$first" --notes secret-notes)
run "$claim" "$id"
refused
has "blocked by @$first"
lacks secret-notes
equals "$(claim_extra "$id")" '{"shingi":{"by":"claude"}}'

test_case "koan missing is refused by name"
only_tools jq
run "$claim" 1
refused
has "koan isn't on PATH"

test_case "bad usage exits 2"
run "$claim"
exit_is 2
run "$claim" abc
exit_is 2

finish
