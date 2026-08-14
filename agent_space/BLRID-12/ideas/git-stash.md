# Idea One-Pager: Git Stash for MiniGit

**Issue:** BLRID-12  
**Date:** 2026-08-14

## How Might We

How might we let MiniGit users temporarily park staged changes so they can switch context (branch, pull, review) and restore that work later—without creating a commit?

## User

MiniGit learners and contributors using the CLI or Flask web UI who need to context-switch while keeping uncommitted staged work safe.

## Success Criteria

- Save staged files to a persistent LIFO stash stack with optional message
- List, apply, pop, and drop stashes from CLI and web UI
- Staging area cleared on save; restored on apply/pop
- Errors when staging is empty (save) or non-empty (apply/pop)
- `make check` passes; architecture boundaries respected

## Direction

Add a **repo-scoped stash stack** backed by a new SQLite `stashes` table. Each entry stores a JSON snapshot of the current `staging` table rows plus timestamp and optional message. Operations live in `frontend/operations.py`; persistence in `backend/sqlite_client.py`. Expose via CLI subcommands (`stash save|list|apply|pop|drop`) and web UI (save button, list page, apply/drop, diff preview).

**MVP:** staged-files-only stash (no working-directory dirty state). LIFO index 0 = newest.

## Assumptions

- Stash captures **staged** files only (matches ticket Notes; simpler than real Git)
- Stash is repo-scoped, not branch-scoped
- Apply/pop require empty staging area (conflict prevention per AC)
- Existing `staging` table schema (`path`, `action`, `blob_hash`) is the snapshot format
- No merge-conflict handling on apply (educational scope)

## Not Doing

- Working-directory (unstaged) file snapshots
- Branch-scoped stashes
- Interactive conflict resolution on apply
- Stash branching or named stash refs beyond optional message
- Real Git interoperability

## Duplicate Check

**Likely duplicate:** [BLRID-10](https://redhat.atlassian.net/browse/BLRID-10) — "Add a stash feature" (In Progress, `sdlc:agent-ready` + `sdlc:human-ready`). Overlapping scope. BLRID-12 has a more detailed AC/spec in the description. Recommend coordinating with BLRID-10 owner to avoid double implementation; BLRID-12 can proceed as the canonical detailed ticket if BLRID-10 is closed or narrowed.

## Already Covered

**None.** Repo scan found no `stash` references in `src/` or `tests/`. Staging infrastructure exists (`SQLiteClient.stage_file`, `get_staged`, `clear_staging`; `Operations.get_staged`) — **reuse**, do not rebuild.
