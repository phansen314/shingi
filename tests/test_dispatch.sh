#!/usr/bin/env bash
set -uo pipefail
# shellcheck source=tests/lib.sh
. "$(dirname "$0")/lib.sh"

# spawn_gives RC JSON: what the stub's spawn will do.
spawn_gives() {
	printf '%s\n' "$1" >"$HOME/spawn-rc"
	printf '%s\n' "$2" >"$HOME/spawn-out"
}

# spawn_args: the stub's recorded arguments, on one line.
spawn_args() {
	tr '\n' ' ' <"$HOME/spawn-args"
}

no_window() {
	[ ! -e "$HOME/spawn-args" ] || fail "spawn ran: $(spawn_args)"
}

test_case "claims, then spawns with exactly these arguments"
stub_sesshin
id=$(new_task task)
run "$dispatch" "@$id" --start
not_refused
has "Dispatched @$id to the session with job koan-$id"
equals "$(claim_extra "$id")" "{\"shingi\":{\"by\":\"dispatch\",\"job\":\"koan-$id\"}}"
equals "$(spawn_args)" "--job koan-$id --prompt /shingi:claim $id --start "

test_case "without --start, the new session gets a plain /shingi:claim, and dispatch still claims first"
stub_sesshin
id=$(new_task task)
run "$dispatch" "$id"
not_refused
has "first prompt is /shingi:claim $id"
equals "$(claim_extra "$id")" "{\"shingi\":{\"by\":\"dispatch\",\"job\":\"koan-$id\"}}"
equals "$(spawn_args)" "--job koan-$id --prompt /shingi:claim $id "

test_case "the new session's /shingi:claim accepts dispatch's claim"
stub_sesshin
id=$(new_task task)
"$dispatch" "$id" >/dev/null
SESSHIN_JOB=koan-$id run "$claim" "$id"
exit_is 0
lacks 'NOT DONE'
has "@$id (/) is claimed"

test_case "the new session's /shingi:claim --start accepts dispatch's claim"
stub_sesshin
id=$(new_task task --notes body)
"$dispatch" "$id" --start >/dev/null
SESSHIN_JOB=koan-$id run "$claim" "$id" --start
not_refused
has body

test_case "a directory becomes --cwd, resolved"
stub_sesshin
id=$(new_task task)
mkdir "$HOME/there"
run "$dispatch" "$id" --start "$HOME/there/../there"
not_refused
equals "$(spawn_args)" "--job koan-$id --cwd $HOME/there --prompt /shingi:claim $id --start "

test_case "options after -- pass through, with no --cwd to beat a template's"
stub_sesshin
id=$(new_task task)
run "$dispatch" "$id" --start -- --template opus --type split -- --model opus
not_refused
equals "$(spawn_args)" "--job koan-$id --prompt /shingi:claim $id --start --template opus --type split -- --model opus "

test_case "a directory and options together"
stub_sesshin
id=$(new_task task)
mkdir "$HOME/there"
run "$dispatch" "$id" --start "$HOME/there" -- --type split
not_refused
equals "$(spawn_args)" "--job koan-$id --cwd $HOME/there --prompt /shingi:claim $id --start --type split "

test_case "a directory that isn't there is refused, before claiming"
stub_sesshin
id=$(new_task task)
run "$dispatch" "$id" --start "$HOME/nope"
refused
equals "$(claim_extra "$id")" null
no_window

test_case "blocked is refused, unclaimed, and opens no window"
stub_sesshin
first=$(new_task first)
id=$(new_task second --blocked-by "$first")
run "$dispatch" "$id" --start
refused
has "blocked by @$first"
equals "$(claim_extra "$id")" null
no_window

test_case "already claimed is refused, the claim untouched, no window"
stub_sesshin
id=$(new_task task)
koan claim "$id" --extra '{"mine":true}' >/dev/null
run "$dispatch" "$id" --start
refused
has 'already claimed'
has '"rule":"claimed"'
equals "$(claim_extra "$id")" '{"mine":true}'
no_window

test_case "complete is refused, no window"
stub_sesshin
id=$(new_task task)
koan complete "$id" >/dev/null
run "$dispatch" "$id" --start
refused
has 'needs reopening'
no_window

test_case "not found is refused, no window"
stub_sesshin
run "$dispatch" 999 --start
refused
has '"kind":"not-found"'
no_window

test_case "a folder's ID is refused, no window"
stub_sesshin
id=$(koan folder create /work | jq -r .result.id)
run "$dispatch" "$id" --start
refused
has "isn't a task"
no_window

test_case "job-taken undoes the claim"
stub_sesshin
id=$(new_task task)
spawn_gives 1 '{"ok":false,"error":{"kind":"conflict","message":"taken","details":{"rule":"job-taken"}},"warnings":[]}'
run "$dispatch" "$id" --start
refused
has 'unclaimed again'
has '"job-taken"'
equals "$(claim_extra "$id")" null

test_case "launch-failed undoes the claim"
stub_sesshin
id=$(new_task task)
spawn_gives 1 '{"ok":false,"error":{"kind":"terminal","message":"no","details":{"reason":"launch-failed"}},"warnings":[]}'
run "$dispatch" "$id" --start
refused
has 'unclaimed again'
equals "$(claim_extra "$id")" null

test_case "a template that isn't there undoes the claim"
stub_sesshin
id=$(new_task task)
spawn_gives 1 '{"ok":false,"error":{"kind":"not-found","message":"no template","details":{"templates":[]}},"warnings":[]}'
run "$dispatch" "$id" --start -- --template nope
refused
has 'unclaimed again'
equals "$(claim_extra "$id")" null

test_case "launch-unknown keeps the claim, and says where to look"
stub_sesshin
id=$(new_task task)
spawn_gives 1 '{"ok":false,"error":{"kind":"terminal","message":"maybe","details":{"reason":"launch-unknown"}},"warnings":[]}'
run "$dispatch" "$id" --start
refused
has "sesshin focus koan-$id"
has 'stays claimed'
has '"launch-unknown"'
[ "$(claim_extra "$id")" != null ] || fail "the claim went away"

test_case "a not-started warning keeps the claim, and mentions the dialog"
stub_sesshin
id=$(new_task task)
spawn_gives 0 '{"ok":true,"result":{"job":"j","placement":{},"session":null},"warnings":[{"kind":"not-started","message":"late"}]}'
run "$dispatch" "$id" --start
not_refused
has 'workspace-trust'
has "Dispatched @$id"
[ "$(claim_extra "$id")" != null ] || fail "the claim went away"

test_case "other warnings don't mention the dialog"
stub_sesshin
id=$(new_task task)
spawn_gives 0 '{"ok":true,"result":{"job":"j","placement":{},"session":{"id":1}},"warnings":[{"kind":"unusable-file","message":"x"}]}'
run "$dispatch" "$id" --start
not_refused
lacks 'workspace-trust'

test_case "sesshin missing is refused by name, unclaimed"
id=$(new_task task)
only_tools jq koan
run "$dispatch" "$id" --start
refused
has "sesshin isn't on PATH"
PATH=$real_path
equals "$(claim_extra "$id")" null

test_case "an old sesshin is refused by version, unclaimed"
stub_sesshin
id=$(new_task task)
STUB_SESSHIN_VERSION='{"ok":true,"result":{"version":"v1.1.9"}}' run "$dispatch" "$id" --start
refused
has 'found v1.1.9'
equals "$(claim_extra "$id")" null
no_window

test_case "bad usage exits 2"
stub_sesshin
run "$dispatch"
exit_is 2
run "$dispatch" abc --start
exit_is 2
run "$dispatch" --start
exit_is 2
run "$dispatch" 1 --nope
exit_is 2
run "$dispatch" 1 --start dir extra
exit_is 2

finish
