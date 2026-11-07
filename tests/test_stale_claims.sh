#!/usr/bin/env bash
set -uo pipefail
# shellcheck source=tests/lib.sh
. "$(dirname "$0")/lib.sh"

# live_jobs JOB...: what the stub's list reports as live.
live_jobs() {
	jq -cn --args '{ok: true, result: {sessions: ($ARGS.positional | map({id: 1, session_id: "x", job: .}) + [{id: 2, session_id: "y", job: null}]), total: 1, truncated: false}, warnings: []}' "$@" >"$HOME/list-out"
}

# stale_refs: the refs under result.stale, comma-joined.
stale_refs() {
	jq -r '[.result.stale[].ref] | join(",")' <<<"$out"
}

test_case "a job with no live session is stale; a live one isn't"
stub_sesshin
gone=$(new_task gone)
here=$(new_task here)
koan claim "$gone" --extra '{"shingi":{"job":"koan-gone"}}' >/dev/null
koan claim "$here" --extra '{"shingi":{"job":"koan-here"}}' >/dev/null
live_jobs koan-here
run "$stale"
exit_is 0
equals "$(stale_refs)" "@$gone (/)"
equals "$(jq -r '.result.stale[0].job' <<<"$out")" koan-gone
equals "$(jq -c .result.no_job <<<"$out")" '[]'

test_case "a job's case doesn't matter, as in sesshin"
stub_sesshin
id=$(new_task task)
koan claim "$id" --extra '{"shingi":{"job":"Koan-1"}}' >/dev/null
live_jobs koan-1
run "$stale"
exit_is 0
equals "$(stale_refs)" ""

test_case "a claim with no job can't be judged, and is listed apart"
stub_sesshin
id=$(new_task task)
koan claim "$id" --extra '{"mine":true}' >/dev/null
live_jobs
run "$stale"
exit_is 0
equals "$(stale_refs)" ""
equals "$(jq -r '.result.no_job[0].ref' <<<"$out")" "@$id (/)"

test_case "it changes nothing"
stub_sesshin
id=$(new_task task)
koan claim "$id" --extra '{"shingi":{"job":"koan-gone"}}' >/dev/null
live_jobs
run "$stale"
equals "$(claim_extra "$id")" '{"shingi":{"job":"koan-gone"}}'

test_case "no claims at all"
stub_sesshin
new_task task >/dev/null
run "$stale"
exit_is 0
equals "$(jq -c .result <<<"$out")" '{"stale":[],"no_job":[]}'

test_case "sesshin missing says so, as a recipe that starts no work"
only_tools jq koan
run "$stale"
stopped
has "sesshin isn't on PATH"

test_case "a list that isn't JSON says so, and exits 0"
stub_sesshin
printf 'not json\n' >"$HOME/list-out"
run "$stale"
exit_is 0
stopped
has "the list of sessions wasn't JSON"

test_case "bad usage exits 2"
stub_sesshin
run "$stale" extra
exit_is 2

finish
