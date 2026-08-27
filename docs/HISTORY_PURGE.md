# Git history purge

The proprietary `Plants Vs Zombies Game of the Year Edition/` directory was removed from the working tree and then purged from rewritten `main` history during the pre-Phase-3 cleanup on 27 August 2026.

Verification against the rewritten default-branch history returned no commits for that path.

`scripts/purge-game-history.ps1` is retained only as a manual recovery/reference script. It should **not** be run again on the normal repository unless the proprietary game directory is accidentally recommitted in the future.

## Important clone note

Because the cleanup rewrote commit SHAs, any clone made before the history purge should be discarded and cloned again, or carefully hard-reset to the rewritten history. Pushing an old local branch can reintroduce obsolete object history.
