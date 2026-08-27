# One-time Git history purge

The proprietary `Plants Vs Zombies Game of the Year Edition/` directory has already been removed from the current working tree and is ignored by `.gitignore`. Older commits still contain that path until history is rewritten.

Use `scripts/purge-game-history.ps1` once from a clean local clone on Windows.

## Before running

1. Ensure all wanted work is pushed.
2. Make sure collaborators know commit SHAs will change.
3. Install `git-filter-repo`:

```powershell
pip install git-filter-repo
```

## Run

```powershell
.\scripts\purge-game-history.ps1
```

The script removes the game directory from all rewritten history, verifies the path is absent, and force-pushes branches and tags.

After the rewrite, old clones should be discarded and cloned again to avoid accidentally reintroducing the old object history.
