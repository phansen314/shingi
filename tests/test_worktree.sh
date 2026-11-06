#!/usr/bin/env bash
set -uo pipefail
# shellcheck source=tests/lib.sh
. "$(dirname "$0")/lib.sh"

# new_repo: a git repository at $HOME/code/api with a commit, and we're in it.
new_repo() {
	mkdir -p "$HOME/code/api"
	cd "$HOME/code/api" || exit 1
	git init -q .
	git -c user.name=t -c user.email=t@example.com commit -q --allow-empty -m first
}

# folder_of DIR: the folder koan finds from DIR.
folder_of() {
	koan where --file "$1" | jq -r .result.folder.path
}

test_case "adds a worktree in .claude/worktrees on a new branch, binds it, and briefs it"
koan folder create /work/api >/dev/null
new_repo
run "$worktree" /work/api feature
exit_is 0
lacks 'NOT DONE'
has "Worktree at $HOME/code/api/.claude/worktrees/feature, on feature, bound to"
has '"path":"/work/api"'
[ -d "$HOME/code/api/.claude/worktrees/feature" ] || fail "no worktree"
equals "$(folder_of "$HOME/code/api/.claude/worktrees/feature")" /work/api
equals "$(git -C "$HOME/code/api/.claude/worktrees/feature" branch --show-current)" feature

test_case "the branch defaults to the folder's name"
koan folder create /ABC-123 >/dev/null
new_repo
run "$worktree" /ABC-123
exit_is 0
lacks 'NOT DONE'
has "Worktree at $HOME/code/api/.claude/worktrees/ABC-123, on ABC-123, bound to"
equals "$(git -C "$HOME/code/api/.claude/worktrees/ABC-123" branch --show-current)" ABC-123
equals "$(folder_of "$HOME/code/api/.claude/worktrees/ABC-123")" /ABC-123

test_case "git's status stays clean, and the exclude is added once"
koan folder create /work/api >/dev/null
new_repo
"$worktree" /work/api one >/dev/null
"$worktree" /work/api two >/dev/null
equals "$(git status --short)" ""
equals "$(grep -c '^\.claude/worktrees/$' .git/info/exclude)" 1

test_case "an exclude with no final newline keeps its last line"
koan folder create /work/api >/dev/null
new_repo
printf 'keep-me' >.git/info/exclude
"$worktree" /work/api one >/dev/null
equals "$(head -n 1 .git/info/exclude)" keep-me
equals "$(git status --short)" ""

test_case "a repository that already ignores .claude isn't changed"
koan folder create /work/api >/dev/null
new_repo
printf '.claude/\n' >.gitignore
before=$(cat .git/info/exclude)
run "$worktree" /work/api one
exit_is 0
equals "$(cat .git/info/exclude)" "$before"

test_case "an explicit directory leaves the exclude alone"
koan folder create /work/api >/dev/null
new_repo
before=$(cat .git/info/exclude)
run "$worktree" /work/api one "$HOME/elsewhere"
exit_is 0
equals "$(cat .git/info/exclude)" "$before"

test_case "a slash in the branch doesn't nest the default directory"
koan folder create /work/api >/dev/null
new_repo
run "$worktree" /work/api feature/x
exit_is 0
[ -d "$HOME/code/api/.claude/worktrees/feature-x" ] || fail "no worktree"

test_case "from a subdirectory, the default is still in the checkout"
koan folder create /work/api >/dev/null
new_repo
mkdir sub
cd sub || exit 1
run "$worktree" /work/api one
exit_is 0
[ -d "$HOME/code/api/.claude/worktrees/one" ] || fail "not in the checkout"
equals "$(git status --short)" ""

test_case "uses an existing branch, and an explicit directory"
koan folder create /work/api >/dev/null
new_repo
git branch already
run "$worktree" /work/api already "$HOME/elsewhere"
exit_is 0
equals "$(git -C "$HOME/elsewhere" branch --show-current)" already
equals "$(folder_of "$HOME/elsewhere")" /work/api

test_case "from inside a worktree, the default is still in the main checkout"
koan folder create /work/api >/dev/null
new_repo
"$worktree" /work/api one >/dev/null
cd "$HOME/code/api/.claude/worktrees/one" || exit 1
run "$worktree" /work/api two
exit_is 0
[ -d "$HOME/code/api/.claude/worktrees/two" ] || fail "not in the main checkout"

test_case "no such folder makes nothing"
new_repo
run "$worktree" /nope feature
stopped
[ ! -e "$HOME/code/api/.claude/worktrees/feature" ] || fail "a worktree was made"
git show-ref --verify --quiet refs/heads/feature && fail "a branch was made"

test_case "a task isn't a folder"
id=$(new_task task)
new_repo
run "$worktree" "$id" feature
stopped
has "isn't a folder"

test_case "a directory that exists makes nothing"
koan folder create /work/api >/dev/null
new_repo
mkdir -p "$HOME/code/api/.claude/worktrees/feature"
run "$worktree" /work/api feature
stopped
has 'already exists'
git show-ref --verify --quiet refs/heads/feature && fail "a branch was made"

test_case "git refusing is reported: a branch checked out elsewhere"
koan folder create /work/api >/dev/null
new_repo
current=$(git branch --show-current)
run "$worktree" /work/api "$current" "$HOME/elsewhere"
stopped
has "git couldn't add the worktree"

test_case "koan refusing the bind removes the worktree and the new branch"
koan folder create /work/api >/dev/null
new_repo
run "$worktree" /work/api feature "$HOME/koan-root/inside"
stopped
has "removed again"
[ ! -e "$HOME/koan-root/inside" ] || fail "the worktree stayed"
git show-ref --verify --quiet refs/heads/feature && fail "the branch stayed"

test_case "koan refusing the bind keeps a branch that was already there"
koan folder create /work/api >/dev/null
new_repo
git branch already
run "$worktree" /work/api already "$HOME/koan-root/inside"
stopped
git show-ref --verify --quiet refs/heads/already || fail "the branch went"

test_case "outside a repository says so"
koan folder create /work/api >/dev/null
run "$worktree" /work/api feature
stopped
has "isn't a git repository"

test_case "bad usage exits 2"
run "$worktree"
exit_is 2
run "$worktree" /work/api branch dir extra
exit_is 2

finish
