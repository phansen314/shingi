#!/usr/bin/env bash
# Adds a git worktree for a branch and binds it to a koan folder, together.
# See README.md beside this file. Refusals exit 0 and begin NOT DONE.
set -uo pipefail

here=$(cd "$(dirname "$0")" && pwd -P)
# shellcheck source=recipes/lib.sh
. "$here/../lib.sh"

if [ $# -lt 1 ] || [ $# -gt 3 ]; then
	usage "worktree.sh <folder> [branch] [dir]"
fi
folder=$1
branch=${2:-}
dir=${3:-}

say=stop
require_koan || exit 0
if ! command -v git >/dev/null; then
	stop "git isn't on PATH. Tell the user."
	exit 0
fi

if ! common=$(git rev-parse --git-common-dir 2>/dev/null); then
	stop "this isn't a git repository. Run it from the repository the worktree is for."
	exit 0
fi

if ! where=$(koan where "$folder" 2>/dev/null); then
	stop "koan has no folder $folder. Tell the user; nothing was made."
	printf '%s\n' "$where"
	exit 0
fi
if [ "$(jq -r .result.kind <<<"$where")" != folder ]; then
	stop "$folder isn't a folder. Tell the user; nothing was made."
	exit 0
fi

if [ -z "$branch" ]; then
	branch=$(koan show "$folder" 2>/dev/null | jq -r '.result.folder.name // empty')
	if [ -z "$branch" ]; then
		stop "$folder has no name to use as a branch, so give one. Tell the user; nothing was made."
		exit 0
	fi
fi

# By default where Claude Code keeps worktrees, so a session can use EnterWorktree:
# ~/code/api and feature/x make ~/code/api/.claude/worktrees/feature-x.
checkout=
if [ -z "$dir" ]; then
	common=$(cd "$common" && pwd -P)
	checkout=$(dirname "$common")
	dir=$checkout/.claude/worktrees/$(printf '%s' "$branch" | tr / -)
fi
if [ -e "$dir" ]; then
	stop "$dir already exists. Tell the user; nothing was made."
	exit 0
fi

made_branch=
if git show-ref --verify --quiet "refs/heads/$branch"; then
	added=$(git worktree add "$dir" "$branch" 2>&1)
	status=$?
else
	added=$(git worktree add -b "$branch" "$dir" 2>&1)
	status=$?
	made_branch=1
fi
if [ "$status" -ne 0 ]; then
	stop "git couldn't add the worktree. Tell the user, quoting git's message."
	printf '%s\n' "$added"
	exit 0
fi
dir=$(cd "$dir" && pwd -P)

if ! bound=$(koan bind "$folder" "$dir" 2>/dev/null); then
	git worktree remove --force "$dir" >/dev/null 2>&1
	if [ -n "$made_branch" ]; then
		git branch -D "$branch" >/dev/null 2>&1
	fi
	stop "koan couldn't bind the worktree, so it was removed again. Tell the user, quoting koan's message."
	printf '%s\n' "$bound"
	exit 0
fi

# Inside the checkout, git would list it as untracked, and git add -A would take it.
if [ -n "$checkout" ] && ! git -C "$checkout" check-ignore -q .claude/worktrees/; then
	exclude=$common/info/exclude
	mkdir -p "$common/info"
	if [ -s "$exclude" ] && [ -n "$(tail -c 1 "$exclude")" ]; then
		printf '\n' >>"$exclude"
	fi
	printf '.claude/worktrees/\n' >>"$exclude"
fi

printf 'Worktree at %s, on %s, bound to %s.\n\n' "$dir" "$branch" "$(jq -r .result.ref <<<"$where")"
(cd "$dir" && koan context --here --limit 20 2>/dev/null)
