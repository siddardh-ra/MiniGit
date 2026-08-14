# Plan: BLRID-12 Git Stash

**Branch:** `aiagent/BLRID-12` (created at implement start)  
**Spec:** `agent_space/BLRID-12/specs/git-stash.md`

## Architecture

```
cli.py / app.py
    └── frontend/operations.py  (stash_save, stash_list, stash_apply, stash_pop, stash_drop)
            └── backend/sqlite_client.py  (stashes table + CRUD)
```

No `components/` changes. Reuse existing staging helpers.

## Task Breakdown

| # | Task | Size | Type | Files |
|---|------|------|------|-------|
| T1 | Add `stashes` table + SQLite methods | S | build | `sqlite_client.py` |
| T2 | Add stash operations in frontend | M | build | `operations.py` |
| T3 | CLI `stash` subcommand group | M | build | `cli.py` |
| T4 | Tests for stash backend + operations | M | build | `tests/test_stash.py` |
| T5 | Web UI: save button + stash list routes | M | build | `app.py`, templates |
| T6 | Web UI: diff preview for stash contents | S | build | templates, `app.py` |
| T7 | Final verify + docs touch-up if needed | S | verify | `make check`, optional `CLAUDE.md` |

## Checkpoints

- **CP1 (after T2):** Stash save/list/apply/pop/drop work via Python REPL or unit tests
- **CP2 (after T4):** `make test` green for stash; coverage maintained
- **CP3 (after T6):** Full `make check` + manual CLI + web smoke test

## Vertical Slices

1. **Slice 1 (T1–T2):** Core stash stack in backend + frontend
2. **Slice 2 (T3–T4):** CLI + automated tests
3. **Slice 3 (T5–T6):** Web UI integration

## Risks

- Index-based stash addressing after drop requires consistent newest-first ordering
- BLRID-10 duplicate work — coordinate before merge

## PR Strategy

Single PR on `aiagent/BLRID-12` with all slices; checker pass separate from maker.
