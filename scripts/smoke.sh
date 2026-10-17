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
tmp=$(cd "$(mktemp -d)" && pwd -P)  # its real path: macOS's /var is /private/var
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
# Where shingi looks for shingi.toml and hooks.json: macOS ignores XDG_CONFIG_HOME.
if [[ $(uname) == Darwin ]]; then config=$HOME/Library/Application\ Support/shingi; else config=$XDG_CONFIG_HOME/shingi; fi
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
check "kinds: no rules file, so the built-in two" 0 '[.result.kinds[].name] == ["branch", "group"]' -- kinds
check "a missing --config file" 1 '.error.kind == "invalid-rules" and .error.details.reason == "missing"' -- kinds --config "$tmp/nope.toml"
check "no command" 2 '.error.kind == "usage"' --
check "unknown command" 2 '.error.details.problems[0].argument == "init"' -- init
expect "--help" '[[ $("$SHINGI" --help) == "Usage: shingi <command>"* ]]'
expect "unwritable stdout is exit 3" '(exec 1>&-; "$SHINGI" version 2>/dev/null); [[ $? == 3 ]]'

echo "== rules"
koan init
mkdir -p "$config"
check "no units before the first create" 0 '.result.units == []' -- list
printf 'schema = 1\n[kind.group]\nsugests = []\n' >"$config/shingi.toml"
check "a typo in the rules" 1 '.error.details.problems == [{field: "kind.group.sugests", reason: "unknown field"}]' -- kinds
cat >"$config/shingi.toml" <<'EOF'
schema = 1

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
check "where it lives" 0 '.result | .koan_folder == "/shingi/HOME-1" and .working_folder == "'"$HOME"'/shingi-root/HOME-1" and .notes_path == "'"$HOME"'/shingi-root/HOME-1/uow.md"' \
	-- where HOME-1
check "where reports what create did" 0 '.result | .start.id == '"$p_start"' and .done.id == '"$p_done" -- where HOME-1
expect "manifest and notes on disk" '[[ -f $HOME/shingi-root/HOME-1/uow.json && $(cat "$HOME/shingi-root/HOME-1/uow.md") == "# Payment retries" ]]'
expect "nothing hidden left behind" '[[ -z $(ls -A "$HOME/shingi-root/HOME-1" | grep "^\.") ]]'
check "title defaults to the name" 0 '.result.unit.title == "HOME-2"' -- create HOME-2 group
check "notes from stdin" 0 '.ok' -- create HOME-3 group --title 'Notes' --notes-file - <<<'Story: retry failed payments.'
expect "notes below the title" '[[ $(cat "$HOME/shingi-root/HOME-3/uow.md") == $'"'"'# Notes\n\nStory: retry failed payments.'"'"' ]]'
koan delete-folder -r /shingi/HOME-3 && rm -rf "$HOME/shingi-root/HOME-3"  # out of the way of list's checks
check "--notes with --notes-file" 2 '.error.kind == "usage"' -- create HOME-7 group --notes a --notes-file -
check "again: unit-exists" 1 '.error.kind == "unit-exists"' -- create HOME-1 group
check "unknown kind" 1 '.error.details | .kind == "story" and .defined == ["branch", "group"]' -- create HOME-3 story
check "bad name" 1 '.error.kind == "invalid-name" and .error.details.field == "/path"' -- create bad- group
check "missing parent" 1 '.error.details == {parent: "HOME-9/x", missing: "HOME-9"}' -- create HOME-9/x/y group
check "missing kind" 2 '.error.kind == "usage"' -- create HOME-3
check "empty title" 1 '.error.details.problems == [{field: "/title", reason: "must not be empty"}]' -- create HOME-3 group --title ''

echo "== input"
check "where from stdin" 0 '.result.path == "HOME-1"' -- where -i - <<<'{"unit": "HOME-1"}'
check "every problem" 1 '[.error.details.problems[].field] == ["/extra", "/path"]' -- create -i - <<<'{"kind": "group", "extra": 1}'
check "not one object" 1 '.error.details.problems[0].field == ""' -- kinds -i - <<<'{} {}'
check "input with arguments" 2 '.error.kind == "usage"' -- create HOME-3 group -i - <<<'{}'

echo "== nesting"
check "child a" 0 '.result.unit | .parent == "HOME-1" and .koan_folder == "/shingi/HOME-1/a" and .start.readiness == "blocked"' -- create HOME-1/a branch
a_done=$(jq .result.unit.done.id <<<"$out")
check "child b" 0 '.result.unit.parent == "HOME-1"' -- create HOME-1/b branch
b_done=$(jq .result.unit.done.id <<<"$out")
check "the parent knows its children" 0 '.result.children == [{path: "HOME-1/a", kind: "branch"}, {path: "HOME-1/b", kind: "branch"}]' -- where HOME-1
expect "the parent's done task waits on both" \
	'[[ $("$KOAN" show '"$p_done"' | jq -c .result.task.blocked_by) == "[$p_start,$a_done,$b_done]" ]]'
koan done "$p_start"
check "parent started" 0 '.result.state == "started"' -- where HOME-1
check "a child is ready once its parent starts" 0 '.result.start.readiness == "ready"' -- where HOME-1/a

echo "== order between units"
check "a unit to come after" 0 '.ok' -- create HOME-8 group
o_start=$(jq .result.unit.start.id <<<"$out")
check "a first child" 0 '.ok' -- create HOME-8/research group
r_done=$(jq .result.unit.done.id <<<"$out")
check "--after, a list and repeated" 0 '.result.unit.start.readiness == "blocked" and .warnings == []' \
	-- create HOME-8/implementation group --after HOME-8/research --after HOME-1/a,HOME-1/b
i_start=$(jq .result.unit.start.id <<<"$out")
expect "its start task waits on its parent's start task and each done task" \
	'[[ $("$KOAN" show '"$i_start"' | jq -c .result.task.blocked_by) == "[$a_done,$b_done,$o_start,$r_done]" ]]'
check "after itself" 1 '.error.kind == "after-lineage" and .error.details == {field: "/after/0", after: "HOME-8/x", relation: "self"}' \
	-- create HOME-8/x group --after HOME-8/x
check "after an ancestor" 1 '.error.details == {field: "/after/1", after: "HOME-8", relation: "ancestor"}' \
	-- create HOME-8/x group --after HOME-8/research,HOME-8
check "after a unit that isn't one" 1 '.error.kind == "after-not-found" and .error.details == {field: "/after/0", after: "HOME-8/nope", missing: "HOME-8/nope"}' \
	-- create HOME-8/x group --after HOME-8/nope
check "after a bad name" 1 '.error.kind == "invalid-name" and .error.details.field == "/after/0"' -- create HOME-8/x group --after -bad
check "after the same unit twice" 1 '.error.details.problems[0].field == "/after/1"' -- create HOME-8/x group --after HOME-1/a,HOME-1/a
expect "nothing made by a refusal" '[[ ! -e $HOME/shingi-root/HOME-8/x ]]'
check "adopt has no --after" 2 '.error.kind == "usage"' -- adopt HOME-8/x group --after HOME-1/a
check "after a path beneath it" 1 '.error.details == {field: "/after/0", after: "HOME-8/x/y", relation: "descendant"}' \
	-- create HOME-8/x group --after HOME-8/x/y
koan delete-folder -r /shingi/HOME-8 && rm -rf "$HOME/shingi-root/HOME-8"  # out of the way of list's checks

echo "== a whole tree at once"
check "create-batch needs --input" 2 '.error.kind == "usage"' -- create-batch
check "no units: nothing happens" 0 '.result.units == [] and .warnings == []' -- create-batch -i - <<<'{"units": []}'
check "a story, in any order" 0 '[.result.units[].path] == ["HOME-9", "HOME-9/implementation", "HOME-9/implementation/1-schema", "HOME-9/research", "HOME-9/review", "HOME-9/setup"] and .warnings == []' \
	-- create-batch -i - <<'EOF'
{"units": [
  {"path": "HOME-9/review", "kind": "group", "after": ["HOME-9/implementation"]},
  {"path": "HOME-9/implementation/1-schema", "kind": "branch", "title": "foo: schema changes"},
  {"path": "HOME-9", "kind": "group", "title": "A story", "notes": "Story: all of it."},
  {"path": "HOME-9/research", "kind": "group", "after": ["HOME-9/setup"]},
  {"path": "HOME-9/implementation", "kind": "group", "after": ["HOME-9/research"]},
  {"path": "HOME-9/setup", "kind": "group"}
]}
EOF
batch=$out
s9() { jq ".result.units[] | select(.path == \"$1\") | .$2.id" <<<"$batch"; }
expect "research waits on its parent's start and setup's done" \
	'[[ $("$KOAN" show '"$(s9 HOME-9/research start)"' | jq -c .result.task.blocked_by) == "[$(s9 HOME-9 start),$(s9 HOME-9/setup done)]" ]]'
expect "the story is done when its children are" \
	'[[ $("$KOAN" show '"$(s9 HOME-9 done)"' | jq -c ".result.task.blocked_by | length") == 5 ]]'
expect "the notes" '[[ $(cat "$HOME/shingi-root/HOME-9/uow.md") == $'"'"'# A story\n\nStory: all of it.'"'"' ]]'
check "more of it, after a unit already there" 0 '.result.units[0].start.readiness == "blocked" and .warnings == []' \
	-- create-batch -i - <<<'{"units": [{"path": "HOME-9/followup", "kind": "group", "after": ["HOME-9/review"]}]}'
expect "added to the story's done task" \
	'[[ $("$KOAN" show '"$(s9 HOME-9 done)"' | jq -c ".result.task.blocked_by | length") == 6 ]]'
check "the same path twice, in another case" 1 '.error.kind == "duplicate-path" and .error.details == {fields: ["/units/0/path", "/units/1/path"], paths: ["X", "x"], reason: "case"}' \
	-- create-batch -i - <<<'{"units": [{"path": "X", "kind": "group"}, {"path": "x", "kind": "group"}]}'
check "an entry's error says which" 1 '.error.kind == "after-not-found" and .error.details.field == "/units/1/after/0"' \
	-- create-batch -i - <<<'{"units": [{"path": "X", "kind": "group"}, {"path": "Y", "kind": "group", "after": ["Z"]}]}'
check "afters that can never be met" 1 '.error.kind == "after-cycle" and .error.details.cycle == ["X", "Y"]' \
	-- create-batch -i - <<<'{"units": [{"path": "X", "kind": "group", "after": ["Y"]}, {"path": "Y", "kind": "group", "after": ["X"]}]}'
expect "nothing made by a refusal" '[[ ! -e $HOME/shingi-root/X && ! -e $HOME/shingi-root/Y ]]'
koan delete-folder -r /shingi/HOME-9 && rm -rf "$HOME/shingi-root/HOME-9"  # out of the way of list's checks

echo "== where from a directory"
mkdir -p "$HOME/shingi-root/HOME-1/a/logs/2026" "$HOME/shingi-root/scratch"
cd "$HOME/shingi-root/HOME-1/a"
check "in a working folder" 0 '.result.path == "HOME-1/a"' -- where
cd "$HOME/shingi-root/HOME-1/a/logs/2026"
check "in working material" 0 '.result.path == "HOME-1/a"' -- where
cd "$HOME/shingi-root"
check "the working root: no unit" 1 '.error.details.reason == "no-unit"' -- where
cd "$HOME/shingi-root/scratch"
check "a plain folder: no unit" 1 '.error.details.reason == "no-unit"' -- where
cd "$HOME"
check "outside the working root" 1 '.error.details.reason == "outside-root"' -- where
check "a path that isn't a unit" 1 '.error.details | .reason == "not-a-unit" and .missing == "scratch"' -- where scratch

echo "== context"
check "the unit, as where" 0 '.result.unit == ('"$("$SHINGI" where HOME-1/a | jq -c .result)"')' -- context HOME-1/a
check "its ancestors" 0 '.result.ancestors == [{path: "HOME-1", id: .result.ancestors[0].id, kind: "group", title: "Payment retries"}]' -- context HOME-1/a
check "its and its parent's notes" 0 '.result.notes == "# a\n" and .result.parent_notes == "# Payment retries\n"' -- context HOME-1/a
check "its open tasks, start task first" 0 '[.result.tasks[] | .tags[1]] == ["shingi-start", "shingi-done"]' -- context HOME-1/a
cd "$HOME/shingi-root/HOME-1/a"
check "from its working folder" 0 '.result.unit.path == "HOME-1/a"' -- context
cd "$HOME"
check "a top-level unit" 0 '.result.ancestors == [] and .result.parent_notes == null' -- context HOME-1

echo "== bind"
tree=$tmp/worktree
mkdir -p "$tree/src"
check "bind a worktree" 0 '.result.unit.path == "HOME-1/a" and .result.marker == "'"$tree"'/.shingi/unit.json"' -- bind HOME-1/a "$tree"
expect "it ignores itself" '[[ $(cat "$tree/.shingi/.gitignore") == "*" ]]'
cd "$tree/src"
check "where from a bound worktree" 0 '.result.path == "HOME-1/a"' -- where
check "context from a bound worktree" 0 '.result.unit.path == "HOME-1/a"' -- context
check "another unit is bound-elsewhere" 1 '.error.kind == "bound-elsewhere" and .error.details.unit == "HOME-1/a"' -- bind HOME-1/b "$tree"
check "a working folder needs no marker" 1 '.error.kind == "inside-root"' -- bind HOME-1/a "$HOME/shingi-root/HOME-1/a"
check "unbind from a subdirectory: no marker" 1 '.error.details.reason == "no-marker"' -- unbind
cd "$tree"
check "unbind" 0 '.result.removed | length == 3' -- unbind
check "and it's gone" 1 '.error.details.reason == "outside-root"' -- where
cd "$HOME"

echo "== list"
check "every unit, in path order" 0 '[.result.units[].path] == ["HOME-1", "HOME-1/a", "HOME-1/b", "HOME-2"] and .result.root == null' -- list
check "states" 0 '[.result.units[].state] == ["started", "not-started", "not-started", "not-started"]' -- list
check "one subtree" 0 '.result.root == "HOME-1" and [.result.units[].path] == ["HOME-1", "HOME-1/a", "HOME-1/b"]' -- list HOME-1
check "list and where agree" 0 '.result.units[1] == ('"$("$SHINGI" where HOME-1/a | jq -c .result)"')' -- list
rm -rf "$HOME/shingi-root/HOME-2"
check "a removed unit's tasks are orphans" 0 '[.result.units[].path] == ["HOME-1", "HOME-1/a", "HOME-1/b"] and [.warnings[] | .kind, .details.folder] == ["orphan-task", "/shingi/HOME-2", "orphan-task", "/shingi/HOME-2"]' -- list
check "list of a unit that isn't one" 1 '.error.kind == "not-found"' -- list HOME-2

echo "== a broken manifest"
cp "$HOME/shingi-root/HOME-1/b/uow.json" "$tmp/b.json"
echo '{' >"$HOME/shingi-root/HOME-1/b/uow.json"
check "where warns and reports what it can" 0 '.result | .id == null and .kind == null and .state == null and .title == "b"' -- where HOME-1/b
check "the warning" 0 '.warnings == [{kind: "unsupported-manifest", message: .warnings[0].message, unit: "HOME-1/b", ids: [], details: {path: "'"$HOME"'/shingi-root/HOME-1/b/uow.json", reason: "corrupt"}}]' -- where HOME-1/b
check "a child's kind is null" 0 '.result.children[1] == {path: "HOME-1/b", kind: null} and .warnings == []' -- where HOME-1
check "list goes on past it" 0 '[.result.units[].path] == ["HOME-1", "HOME-1/a", "HOME-1/b"] and [.warnings[].kind] == ["orphan-task", "orphan-task", "unsupported-manifest"]' -- list HOME-1
echo '{"schema": 2, "id": "x", "kind": "group"}' >"$HOME/shingi-root/HOME-1/b/uow.json"
check "a newer schema" 0 '.warnings[0].details.reason == "unsupported-format"' -- where HOME-1/b
check "create under it leaves both links out" 0 '[.warnings[] | .kind, .details.role] == ["parent-unlinked", "start", "parent-unlinked", "done"]' -- create HOME-1/b/x group
cp "$tmp/b.json" "$HOME/shingi-root/HOME-1/b/uow.json"
check "fixed" 0 '.result.kind == "branch" and .warnings == []' -- where HOME-1/b

echo "== an undefined kind"
rules=$config/shingi.toml
cp "$rules" "$tmp/rules.toml"
sed -e '/^\[kind.branch\]/,$d' -e 's/"group", "branch"/"group"/' "$tmp/rules.toml" >"$rules"  # not sed -i: BSD's takes an argument
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
expect "the parent's done task is left alone" '[[ $("$KOAN" show '"$d4_done"' | jq -c .result.task.blocked_by) == "[$d4_start]" ]]'

echo "== adopting a folder"
mkdir -p "$HOME/shingi-root/HOME-5/drafts"
echo 'the plan' >"$HOME/shingi-root/HOME-5/drafts/plan.txt"
printf '# What I had\n\nnotes\n' >"$HOME/shingi-root/HOME-5/uow.md"
check "create refuses an existing folder" 1 '.error.details == {entry: "HOME-5", type: "folder"}' -- create HOME-5 group
check "adopt keeps its notes, quietly" 0 '.result.unit | .title == "What I had" and .state == "not-started"' -- adopt HOME-5 group --title 'Ignored'
check "no warnings" 0 '.warnings == []' -- where HOME-5
expect "contents untouched" '[[ $(cat "$HOME/shingi-root/HOME-5/drafts/plan.txt") == "the plan" && $(head -1 "$HOME/shingi-root/HOME-5/uow.md") == "# What I had" ]]'
mkdir "$HOME/shingi-root/HOME-5/spike"
check "a child folder without notes gets a title" 0 '.result.unit | .title == "foo: spike" and .parent == "HOME-5"' -- adopt HOME-5/spike branch --title 'foo: spike'
check "adopt again: unit-exists" 1 '.error.kind == "unit-exists"' -- adopt HOME-5 group
check "adopt a missing folder" 1 '.error.details.reason == "no-folder"' -- adopt HOME-6 group
check "adopt in another case" 1 '.error.details == {entry: "HOME-5", type: "unit"}' -- adopt home-5 group

echo "== missing tasks"
cp -r "$HOME/shingi-root/HOME-1/a" "$HOME/shingi-root/HOME-1/copy"
check "a copied unit has no tasks of its own" 0 '.result | .start == null and .done == null and .state == null' -- where HOME-1/copy
check "warned per role" 0 '[.warnings[] | .kind, .details.role] == ["missing-task", "start", "missing-task", "done"]' -- where HOME-1/copy
rm -rf "$HOME/shingi-root/HOME-1/copy"

echo "== koan failing"
mkdir -p "$tmp/badbin"
printf '#!/bin/sh\nexit 5\n' >"$tmp/badbin/koan" && chmod +x "$tmp/badbin/koan"
PATH=$tmp/badbin:$PATH check "where still reports the unit" 0 '.result | .path == "HOME-1/a" and .start == null and .state == null' -- where HOME-1/a
PATH=$tmp/badbin:$PATH check "with koan-failed" 0 '.warnings == [{kind: "koan-failed", message: .warnings[0].message, unit: "HOME-1/a", ids: [], details: {call: "list", exit: 5, error: null}}]' -- where HOME-1/a
PATH=$tmp/badbin:$PATH check "list: one koan-failed, no orphans" 0 '[.warnings[].kind] == ["koan-failed"] and all(.result.units[]; .state == null)' -- list HOME-1
PATH=$tmp/badbin:$PATH check "create: an error, nothing made" 1 '.error.kind == "koan-failed" and (.error | has("partial") | not)' -- create HOME-1/c group
expect "nothing made" '[[ ! -e $HOME/shingi-root/HOME-1/c ]]'

echo "== finishing"
koan done "$(jq .result.start.id <<<"$("$SHINGI" where HOME-1/a)")"
koan done "$a_done"
check "a done" 0 '.result.state == "done"' -- where HOME-1/a
check "what's left" 0 '[.result.units[] | select(.state != "done") | .path] == ["HOME-1", "HOME-1/b", "HOME-1/b/x"]' -- list HOME-1

echo "== deleting"
check "a unit with children is refused" 1 '.error.kind == "has-children" and .error.details.children == ["HOME-1/b/x"]' -- delete HOME-1/b
check "delete a leaf" 0 '.result | .path == "HOME-1/b/x" and (.tasks | length) == 2 and .unblocked == []' -- delete HOME-1/b/x
expect "its folder and notes stay, its manifest goes" '[[ -f $HOME/shingi-root/HOME-1/b/x/uow.md && ! -e $HOME/shingi-root/HOME-1/b/x/uow.json ]]'
check "no longer a unit" 1 '.error.kind == "not-found"' -- delete HOME-1/b/x
p_done=$(jq .result.done.id <<<"$("$SHINGI" where HOME-1)")
check "its parent, which the top unit waited on" 0 '.result.unblocked == ['"$p_done"']' -- delete HOME-1/b
check "nothing left over" 0 '[.result.units[].path] == ["HOME-1", "HOME-1/a"] and .warnings == []' -- list HOME-1
check "adopt brings it back" 0 '.result.unit | .path == "HOME-1/b" and .kind == "group"' -- adopt HOME-1/b group

echo "== hooks"
cat >"$config/hooks.json" <<'EOF'
{ "schema": 1, "hooks": { "create": [{ "command": "echo nope >&2; exit 3", "description": "smoke" }] } }
EOF
check "a failing hook is a warning, and create succeeds" 0 '.result.unit.path == "HOME-8" and [.warnings[] | .kind, .details.exit, .details.stderr] == ["hook-failed", 3, "nope\n"]' -- create HOME-8 group
cat >"$config/hooks.json" <<'EOF'
{ "schema": 1, "hooks": { "create-batch": [{ "command": "exit 4" }] } }
EOF
check "a batch fires its own event, once" 0 '[.result.units[].path] == ["HOME-8/a", "HOME-8/b"] and [.warnings[] | .kind, .unit, .details.event] == ["hook-failed", null, "create-batch"]' \
	-- create-batch -i - <<<'{"units": [{"path": "HOME-8/a", "kind": "group"}, {"path": "HOME-8/b", "kind": "group"}]}'
echo '{' >"$config/hooks.json"
check "a broken hooks file stops create" 1 '.error.kind == "invalid-hooks"' -- create HOME-9 group
expect "and made nothing" '[[ ! -e $HOME/shingi-root/HOME-9 ]]'
check "and create-batch" 1 '.error.kind == "invalid-hooks"' -- create-batch -i - <<<'{"units": [{"path": "HOME-9", "kind": "group"}]}'
check "reads ignore it" 0 '.ok' -- where HOME-8
rm "$config/hooks.json"

echo
echo "$pass passed, $fail failed"
[[ $fail -eq 0 ]]
