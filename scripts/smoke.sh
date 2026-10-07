#!/usr/bin/env bash
# Smoke test: runs shingi from a shell, as a user would, in a throwaway
# home, so it never touches your real config, units, or tasks.
#
#   scripts/smoke.sh                          # installs shingi from this repo
#   SHINGI=~/.local/bin/shingi scripts/smoke.sh   # tests that install instead
#
# Needs jq, uv, and koan on PATH. Exits 0 when every check passes, 1 otherwise.
set -uo pipefail

repo=$(cd "$(dirname "$0")/.." && pwd)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

command -v jq >/dev/null || { echo "smoke.sh needs jq"; exit 1; }
KOAN=$(command -v koan) || { echo "smoke.sh needs koan on PATH"; exit 1; }

# Install before HOME changes: uv keeps its caches under the real home.
if [[ -z ${SHINGI:-} ]]; then
	UV_TOOL_DIR=$tmp/tools UV_TOOL_BIN_DIR=$tmp/bin uv tool install --quiet --from "$repo" shingi \
		|| { echo "install failed"; exit 1; }
	SHINGI=$tmp/bin/shingi
fi

export HOME=$tmp/home XDG_CONFIG_HOME=$tmp/home/.config
mkdir -p "$HOME"
cd "$HOME"

pass=0 fail=0
out=""

# check DESC WANT_EXIT JQ_EXPR -- ARGS...: runs shingi with ARGS (stdin passes
# through), then checks the exit code, that the output is exactly one line,
# and that JQ_EXPR is true of it. The output is left in $out.
check() {
	local desc=$1 want=$2 expr=$3
	shift 4
	local code=0
	out=$("$SHINGI" "$@" 2>/dev/null) || code=$?
	local lines
	lines=$(printf '%s\n' "$out" | wc -l)
	if [[ $code -ne $want ]]; then
		why="exit $code, want $want"
	elif [[ $lines -ne 1 ]]; then
		why="$lines lines of output, want 1"
	elif ! jq -e "$expr" >/dev/null 2>&1 <<<"$out"; then
		why="not true: $expr"
	else
		pass=$((pass + 1))
		printf 'ok    %s\n' "$desc"
		return
	fi
	fail=$((fail + 1))
	printf 'FAIL  %s\n      shingi %s\n      %s\n      %s\n' "$desc" "$*" "$why" "$out"
}

# expect DESC CONDITION: a check of something besides shingi's output.
expect() {
	if eval "$2"; then
		pass=$((pass + 1))
		printf 'ok    %s\n' "$1"
	else
		fail=$((fail + 1))
		printf 'FAIL  %s\n      not true: %s\n' "$1" "$2"
	fi
}

# koan ARGS...: runs koan quietly, for setting up and changing tasks.
koan() { "$KOAN" "$@" >/dev/null; }

echo "== before rules"
check "version" 0 '.ok and (.result.version | type == "string")' -- version
check "kinds: no rules file" 1 '.error.kind == "invalid-rules" and .error.details.reason == "missing"' -- kinds
check "no command" 2 '.error.kind == "usage"' --
check "unknown command" 2 '.error.details.problems[0].argument == "init"' -- init

echo "== rules"
koan init '~/tasks'
mkdir -p "$HOME/work" "$XDG_CONFIG_HOME/shingi"
cat >"$XDG_CONFIG_HOME/shingi/shingi.toml" <<'EOF'
schema = 1

[roots]
koan    = "/work"
working = "~/work"

[kind.group]
description = "Work gathered under one name."
suggests    = ["group", "branch"]

[kind.branch]
description = "Work on one branch of one repository."
EOF
check "kinds, in name order" 0 '[.result.kinds[].name] == ["branch", "group"]' -- kinds
check "a kind's fields" 0 '.result.kinds[1] == {name: "group", description: "Work gathered under one name.", suggests: ["group", "branch"]}' -- kinds
check "suggests defaults to []" 0 '.result.kinds[0].suggests == []' -- kinds

echo "== create"
check "a top-level group" 0 '.result.unit | .path == "HOME-1" and .kind == "group" and .title == "Payment retries" and .state == "not-started" and .parent == null' \
	-- create HOME-1 group --title 'Payment retries'
p_start=$(jq .result.unit.start.id <<<"$out")
p_done=$(jq .result.unit.done.id <<<"$out")
check "where it lives" 0 '.result | .koan_folder == "/work/HOME-1" and .working_folder == "'"$HOME"'/work/HOME-1" and .notes_path == "'"$HOME"'/work/HOME-1/uow.md"' \
	-- where HOME-1
check "where reports what create did" 0 '.result | .start.id == '"$p_start"' and .done.id == '"$p_done" -- where HOME-1
expect "manifest and notes on disk" '[[ -f $HOME/work/HOME-1/uow.json && $(cat "$HOME/work/HOME-1/uow.md") == "# Payment retries" ]]'
expect "nothing hidden left behind" '[[ -z $(ls -A "$HOME/work/HOME-1" | grep "^\.") ]]'
check "title defaults to the name" 0 '.result.unit.title == "HOME-2"' -- create HOME-2 group
check "notes from stdin" 0 '.ok' -- create HOME-3 group --title 'Notes' --notes-file - <<<'Story: retry failed payments.'
expect "notes below the title" '[[ $(cat "$HOME/work/HOME-3/uow.md") == $'"'"'# Notes\n\nStory: retry failed payments.'"'"' ]]'
koan delete-folder -r /work/HOME-3 && rm -rf "$HOME/work/HOME-3"  # out of the way of list's checks
check "--notes with --notes-file" 2 '.error.kind == "usage"' -- create HOME-7 group --notes a --notes-file -
check "again: unit-exists" 1 '.error.kind == "unit-exists"' -- create HOME-1 group
check "unknown kind" 1 '.error.details | .kind == "story" and .defined == ["branch", "group"]' -- create HOME-3 story
check "bad name" 1 '.error.kind == "invalid-name"' -- create bad- group
check "missing parent" 1 '.error.details == {parent: "HOME-9/x", missing: "HOME-9"}' -- create HOME-9/x/y group
check "missing kind" 2 '.error.kind == "usage"' -- create HOME-3
check "empty title" 1 '.error.details.problems == [{field: "/title", reason: "must not be empty"}]' -- create HOME-3 group --title ''

echo "== input"
check "where from stdin" 0 '.result.path == "HOME-1"' -- where -i - <<<'{"unit": "HOME-1"}'
check "every problem" 1 '[.error.details.problems[].field] == ["/extra", "/path"]' -- create -i - <<<'{"kind": "group", "extra": 1}'
check "not one object" 1 '.error.details.problems[0].field == ""' -- kinds -i - <<<'{} {}'
check "input with arguments" 2 '.error.kind == "usage"' -- create HOME-3 group -i - <<<'{}'

echo "== nesting"
check "child a" 0 '.result.unit | .parent == "HOME-1" and .koan_folder == "/work/HOME-1/a" and .start.readiness == "blocked"' -- create HOME-1/a branch
a_done=$(jq .result.unit.done.id <<<"$out")
check "child b" 0 '.result.unit.parent == "HOME-1"' -- create HOME-1/b branch
b_done=$(jq .result.unit.done.id <<<"$out")
check "the parent knows its children" 0 '.result.children == [{path: "HOME-1/a", kind: "branch"}, {path: "HOME-1/b", kind: "branch"}]' -- where HOME-1
expect "the parent's done task waits on both" \
	'[[ $("$KOAN" show '"$p_done"' | jq -c .result.tasks[0].blocked_by) == "[$p_start,$a_done,$b_done]" ]]'
koan done "$p_start"
check "parent started" 0 '.result.state == "started"' -- where HOME-1
check "a child is ready once its parent starts" 0 '.result.start.readiness == "ready"' -- where HOME-1/a

echo "== where from a directory"
mkdir -p "$HOME/work/HOME-1/a/logs/2026" "$HOME/work/scratch"
cd "$HOME/work/HOME-1/a"
check "in a working folder" 0 '.result.path == "HOME-1/a"' -- where
cd "$HOME/work/HOME-1/a/logs/2026"
check "in working material" 0 '.result.path == "HOME-1/a"' -- where
cd "$HOME/work"
check "the working root: no unit" 1 '.error.details.reason == "no-unit"' -- where
cd "$HOME/work/scratch"
check "a plain folder: no unit" 1 '.error.details.reason == "no-unit"' -- where
cd "$HOME"
check "outside the working root" 1 '.error.details.reason == "outside-root"' -- where
check "a path that isn't a unit" 1 '.error.details | .reason == "not-a-unit" and .missing == "scratch"' -- where scratch

echo "== context"
check "the unit, as where" 0 '.result.unit == ('"$("$SHINGI" where HOME-1/a | jq -c .result)"')' -- context HOME-1/a
check "its ancestors" 0 '.result.ancestors == [{path: "HOME-1", id: .result.ancestors[0].id, kind: "group", title: "Payment retries"}]' -- context HOME-1/a
check "its and its parent's notes" 0 '.result.notes == "# a\n" and .result.parent_notes == "# Payment retries\n"' -- context HOME-1/a
check "its open tasks, start task first" 0 '[.result.tasks[] | .tags[1]] == ["shingi-start", "shingi-done"]' -- context HOME-1/a
cd "$HOME/work/HOME-1/a"
check "from its working folder" 0 '.result.unit.path == "HOME-1/a"' -- context
cd "$HOME"
check "a top-level unit" 0 '.result.ancestors == [] and .result.parent_notes == null' -- context HOME-1

echo "== list"
check "every unit, in path order" 0 '[.result.units[].path] == ["HOME-1", "HOME-1/a", "HOME-1/b", "HOME-2"] and .result.root == null' -- list
check "states" 0 '[.result.units[].state] == ["started", "not-started", "not-started", "not-started"]' -- list
check "one subtree" 0 '.result.root == "HOME-1" and [.result.units[].path] == ["HOME-1", "HOME-1/a", "HOME-1/b"]' -- list HOME-1
check "list and where agree" 0 '.result.units[1] == ('"$("$SHINGI" where HOME-1/a | jq -c .result)"')' -- list
rm -rf "$HOME/work/HOME-2"
check "a removed unit's tasks are orphans" 0 '[.result.units[].path] == ["HOME-1", "HOME-1/a", "HOME-1/b"] and [.warnings[] | .kind, .details.folder] == ["orphan-task", "/work/HOME-2", "orphan-task", "/work/HOME-2"]' -- list
check "list of a unit that isn't one" 1 '.error.kind == "not-found"' -- list HOME-2

echo "== a broken manifest"
cp "$HOME/work/HOME-1/b/uow.json" "$tmp/b.json"
echo '{' >"$HOME/work/HOME-1/b/uow.json"
check "where warns and reports what it can" 0 '.result | .id == null and .kind == null and .state == null and .title == "b"' -- where HOME-1/b
check "the warning" 0 '.warnings == [{kind: "unsupported-manifest", message: .warnings[0].message, unit: "HOME-1/b", ids: [], details: {path: "'"$HOME"'/work/HOME-1/b/uow.json", reason: "corrupt"}}]' -- where HOME-1/b
check "a child's kind is null" 0 '.result.children[1] == {path: "HOME-1/b", kind: null} and .warnings == []' -- where HOME-1
check "list goes on past it" 0 '[.result.units[].path] == ["HOME-1", "HOME-1/a", "HOME-1/b"] and [.warnings[].kind] == ["orphan-task", "orphan-task", "unsupported-manifest"]' -- list HOME-1
echo '{"schema": 2, "id": "x", "kind": "group"}' >"$HOME/work/HOME-1/b/uow.json"
check "a newer schema" 0 '.warnings[0].details.reason == "unsupported-format"' -- where HOME-1/b
check "create under it leaves both links out" 0 '[.warnings[] | .kind, .details.role] == ["parent-unlinked", "start", "parent-unlinked", "done"]' -- create HOME-1/b/x group
cp "$tmp/b.json" "$HOME/work/HOME-1/b/uow.json"
check "fixed" 0 '.result.kind == "branch" and .warnings == []' -- where HOME-1/b

echo "== an undefined kind"
rules=$XDG_CONFIG_HOME/shingi/shingi.toml
cp "$rules" "$tmp/rules.toml"
sed -i -e '/^\[kind.branch\]/,$d' -e 's/"group", "branch"/"group"/' "$rules"
check "where warns and reports the kind as stored" 0 '.result.kind == "branch" and .warnings == [{kind: "undefined-kind", message: .warnings[0].message, unit: "HOME-1/a", ids: [], details: {kind: "branch"}}]' -- where HOME-1/a
check "list warns once per unit" 0 '[.warnings[] | select(.kind == "undefined-kind") | .unit] == ["HOME-1/a", "HOME-1/b"]' -- list HOME-1
check "create refuses it" 1 '.error.kind == "unknown-kind" and .error.details.defined == ["group"]' -- create HOME-3 branch
cp "$tmp/rules.toml" "$rules"
check "defined again" 0 '.warnings == []' -- where HOME-1/a

echo "== a done parent"
check "a parent to close" 0 '.ok' -- create HOME-4 group
d4_start=$(jq .result.unit.start.id <<<"$out")
d4_done=$(jq .result.unit.done.id <<<"$out")
koan done "$d4_start"
koan done "$d4_done"
check "a late child warns parent-done" 0 '.warnings == [{kind: "parent-done", message: .warnings[0].message, unit: "HOME-4/late", ids: ['"$d4_done"'], details: {parent: "HOME-4"}}]' -- create HOME-4/late group
expect "the parent's done task is left alone" '[[ $("$KOAN" show '"$d4_done"' | jq -c .result.tasks[0].blocked_by) == "[$d4_start]" ]]'

echo "== adopting a folder"
mkdir -p "$HOME/work/HOME-5/drafts"
echo 'the plan' >"$HOME/work/HOME-5/drafts/plan.txt"
printf '# What I had\n\nnotes\n' >"$HOME/work/HOME-5/uow.md"
check "create refuses an existing folder" 1 '.error.details == {entry: "HOME-5", type: "folder"}' -- create HOME-5 group
check "adopt keeps its notes, quietly" 0 '.result.unit | .title == "What I had" and .state == "not-started"' -- adopt HOME-5 group --title 'Ignored'
check "no warnings" 0 '.warnings == []' -- where HOME-5
expect "contents untouched" '[[ $(cat "$HOME/work/HOME-5/drafts/plan.txt") == "the plan" && $(head -1 "$HOME/work/HOME-5/uow.md") == "# What I had" ]]'
mkdir "$HOME/work/HOME-5/spike"
check "a child folder without notes gets a title" 0 '.result.unit | .title == "foo: spike" and .parent == "HOME-5"' -- adopt HOME-5/spike branch --title 'foo: spike'
check "adopt again: unit-exists" 1 '.error.kind == "unit-exists"' -- adopt HOME-5 group
check "adopt a missing folder" 1 '.error.details.reason == "no-folder"' -- adopt HOME-6 group
check "adopt in another case" 1 '.error.details == {entry: "HOME-5", type: "unit"}' -- adopt home-5 group

echo "== missing tasks"
cp -r "$HOME/work/HOME-1/a" "$HOME/work/HOME-1/copy"
check "a copied unit has no tasks of its own" 0 '.result | .start == null and .done == null and .state == null' -- where HOME-1/copy
check "warned per role" 0 '[.warnings[] | .kind, .details.role] == ["missing-task", "start", "missing-task", "done"]' -- where HOME-1/copy
rm -rf "$HOME/work/HOME-1/copy"

echo "== koan failing"
mkdir -p "$tmp/badbin"
printf '#!/bin/sh\nexit 5\n' >"$tmp/badbin/koan" && chmod +x "$tmp/badbin/koan"
PATH=$tmp/badbin:$PATH check "where still reports the unit" 0 '.result | .path == "HOME-1/a" and .start == null and .state == null' -- where HOME-1/a
PATH=$tmp/badbin:$PATH check "with koan-failed" 0 '.warnings == [{kind: "koan-failed", message: .warnings[0].message, unit: "HOME-1/a", ids: [], details: {call: "list", exit: 5, error: null}}]' -- where HOME-1/a
PATH=$tmp/badbin:$PATH check "list: one koan-failed, no orphans" 0 '[.warnings[].kind] == ["koan-failed"] and all(.result.units[]; .state == null)' -- list HOME-1
PATH=$tmp/badbin:$PATH check "create: an error, nothing made" 1 '.error.kind == "koan-failed" and (.error | has("partial") | not)' -- create HOME-1/c group
expect "nothing made" '[[ ! -e $HOME/work/HOME-1/c ]]'

echo "== finishing"
koan done "$(jq .result.start.id <<<"$("$SHINGI" where HOME-1/a)")"
koan done "$a_done"
check "a done" 0 '.result.state == "done"' -- where HOME-1/a
check "what's left" 0 '[.result.units[] | select(.state != "done") | .path] == ["HOME-1", "HOME-1/b", "HOME-1/b/x"]' -- list HOME-1

echo
echo "$pass passed, $fail failed"
[[ $fail -eq 0 ]]
