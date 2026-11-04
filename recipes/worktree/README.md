# worktree

Add a git worktree for a branch and bind it to a koan folder, together. Run it from the repository, or any worktree of it.

```sh
recipes/worktree/worktree.sh /work/api feature/x                # beside the checkout: ~/code/api-feature-x
recipes/worktree/worktree.sh /work/api feature/x ~/wt/x         # there
/shingi:worktree /work/api feature/x                            # the skill, in Claude Code
```

The branch is used if it exists, and made from `HEAD` if it doesn't. Pass the path to [`dispatch`](../dispatch/README.md) to start a session there.

**Needs:** koan v0.13.0 or later, `git` and `jq`.

**Writes:** a git worktree, perhaps a branch, and koan's marker in the worktree. No `extra`.

**Prints:** where the worktree is, then `koan context --here --limit 20` from inside it.

**Refuses**, with a first line beginning `NOT DONE:` and exit 0, when this isn't a git repository, the folder doesn't exist, the directory already exists, or git refuses. If koan refuses the bind, the worktree is removed again, and the branch too if this run made it.

Bad usage exits 2.
