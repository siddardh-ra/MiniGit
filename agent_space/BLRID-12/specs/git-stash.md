# Spec: Git Stash for MiniGit

**Issue:** BLRID-12  
**Idea:** `agent_space/BLRID-12/ideas/git-stash.md`

## Assumptions

1. Stash operates on the **staging area** only (not working-directory files).
2. Stashes are stored in SQLite and survive repo close/reopen.
3. Stack ordering: index `0` = most recent; `pop` operates on index `0`.
4. `apply` / `pop` fail if staging is non-empty.
5. `save` fails if staging is empty.
6. Duplicate ticket BLRID-10 exists; implementation should follow BLRID-12 AC unless outer loop redirects.

## Already Covered / Reuse

| Area | Status | Action |
|------|--------|--------|
| Staging read/write | Exists in `sqlite_client.py` + `operations.py` | Reuse `get_staged`, `clear_staging`, `stage_file` |
| Blob storage | Exists | Reuse for diff preview |
| CLI framework | Exists in `cli.py` | Extend with `stash` subparser group |
| Web UI patterns | Exists in `app.py` + templates | Extend staging/working-dir pages |
| Stash feature | **Not built** | Build |

## Objective

Implement Git-like stash for staged changes: save, list, apply, pop, drop via CLI and web UI, persisted in SQLite, respecting MiniGit layer boundaries.

## Commands (CLI)

```
python src/cli.py stash save [message]
python src/cli.py stash list
python src/cli.py stash apply <index>
python src/cli.py stash pop
python src/cli.py stash drop <index>
```

## Structure

### Backend (`src/backend/sqlite_client.py`)

New table:

```sql
CREATE TABLE IF NOT EXISTS stashes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    message TEXT,
    staged_snapshot_json TEXT NOT NULL
);
```

Methods (parameterized SQL only):

- `save_stash(message, snapshot_json) -> int` (returns row id)
- `list_stashes() -> list[dict]` (newest first)
- `get_stash(index: int) -> dict | None`
- `delete_stash(index: int) -> None` (delete by logical index, re-index after drop)

### Frontend (`src/frontend/operations.py`)

- `stash_save(message: str | None) -> int`
- `stash_list() -> list[dict]`
- `stash_apply(index: int) -> None`
- `stash_pop() -> None`
- `stash_drop(index: int) -> None`

Snapshot format: JSON array of `{path, action, blob_hash}` matching `get_staged()` output.

### CLI (`src/cli.py`)

`stash` subcommand group with `save`, `list`, `apply`, `pop`, `drop`.

### Web UI (`src/app.py`, templates)

- Save button on staging/working-dir page
- Stash list route with apply/drop actions
- Diff preview per stash entry

## Style

- Type annotations on all public functions
- Error messages consistent with existing CLI patterns
- Functions <50 lines; files <300 lines
- No components-layer changes

## Testing

New `tests/test_stash.py` (or extend existing test modules):

- Save multiple files; verify snapshot content
- Apply preserves file content in staging
- Pop removes stash from stack
- Empty staging on save → error
- Non-empty staging on apply/pop → error
- Drop re-indexes correctly
- Maintain coverage ≥60%

Verify: `make check`

## Boundaries

- `components/` — no changes
- `backend/` — no imports from frontend/components
- `frontend/` — orchestrates backend only
- `cli.py` / `app.py` — thin layers over frontend

## Success Criteria

Maps to BLRID-12 acceptance criteria sections 1–10:

1. Save captures staged files, clears staging, returns index, errors if empty
2. List shows index/timestamp/message/file count, newest first
3. Apply restores staging, keeps stash, errors on bad index or non-empty staging
4. Pop applies index 0 and removes it
5. Drop deletes and re-indexes
6. SQLite `stashes` table with parameterized queries
7. Correct layer placement; `make boundaries` passes
8. Test coverage per above
9. CLI subcommands with help text
10. Web UI save/list/apply/drop/diff preview

## Open Questions

- **BLRID-10 overlap:** Should BLRID-10 be closed in favor of BLRID-12? (Outer-loop decision.)
- **Web UI diff preview:** Compare stash snapshot against current HEAD tree, or show raw staged paths only? Default: show file list + blob content diff where blobs exist.
