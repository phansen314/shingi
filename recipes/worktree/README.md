# worktree

Add a git worktree for a branch and bind it to a koan folder, together. Run it from the repository, or any worktree of it.

```sh
recipes/worktree/worktree.sh /ABC-123                  # branch ABC-123, in ~/code/api/.claude/worktrees/ABC-123
recipes/worktree/worktree.sh /work/api feature/x       # branch feature/x, in .claude/worktrees/feature-x
recipes/worktree/worktree.sh /work/api feature/x ~/wt/x   # there
/shingi:worktree /ABC-123                              # the skill, in Claude Code
/shingi:worktree for ABC-123                           # or say it: the session finds the folder, even inside an epic
```

The branch defaults to the folder's name. It's used if it exists, and made from `HEAD` if it doesn't.

The directory defaults to `.claude/worktrees/` in the repository, where Claude Code keeps worktrees. A session in the repository can go there with `EnterWorktree` and its `path`, and you can pass the path to [`dispatch`](../dispatch/README.md) to start a session there.

**Needs:** koan v0.13.0 or later, `git` and `jq`.

**Writes:** a git worktree, perhaps a branch, and koan's marker in the worktree. In the default directory, if git doesn't already ignore `.claude/worktrees/`, it also adds that to the repository's `.git/info/exclude`, which is local and not committed, so the worktree can't be committed by accident. No `extra`.

**Prints:** where the worktree is, then `koan context --here --limit 20` from inside it.

**Refuses**, with a first line beginning `NOT DONE:` and exit 0, when this isn't a git repository, the folder doesn't exist, the directory already exists, or git refuses. If koan refuses the bind, the worktree is removed again, and the branch too if this run made it.

Bad usage exits 2.
