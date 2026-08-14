# Todo: BLRID-12 Git Stash

PR branch: `aiagent/BLRID-12`

## T1 — SQLite stashes table + methods

- **Acceptance:** `stashes` table created on init; `save_stash`, `list_stashes`, `get_stash`, `delete_stash` use parameterized SQL; snapshot stored as JSON string
- **Verify:** Unit tests in `tests/test_stash.py` for table creation and CRUD
- **Files:** `src/backend/sqlite_client.py`
- **Size:** S | **Type:** build

## T2 — Frontend stash operations

- **Acceptance:** `stash_save` snapshots `get_staged()`, clears staging, returns index; `stash_list` newest-first; `stash_apply`/`stash_pop` restore staging with guards; `stash_drop` removes and re-indexes; errors match AC
- **Verify:** Unit tests mocking or using `tmp_path` repo
- **Files:** `src/frontend/operations.py`
- **Size:** M | **Type:** build
- **Checkpoint:** CP1

## T3 — CLI stash subcommands

- **Acceptance:** `stash save [message]`, `list`, `apply <index>`, `pop`, `drop <index>` with help text; error output matches existing CLI style
- **Verify:** Manual CLI smoke + existing CLI test patterns if any
- **Files:** `src/cli.py`
- **Size:** M | **Type:** build

## T4 — Stash test suite

- **Acceptance:** Tests cover save (multi-file), apply (content preserved), pop (removed), empty-save error, non-empty-apply error, drop re-index
- **Verify:** `pytest tests/test_stash.py -v`; `make test` passes
- **Files:** `tests/test_stash.py`
- **Size:** M | **Type:** build
- **Checkpoint:** CP2

## T5 — Web UI stash save + list

- **Acceptance:** Save button on staging page; `/stashes` list with apply/drop per entry; flash messages for errors
- **Verify:** Manual browser test on `python src/app.py`
- **Files:** `src/app.py`, `src/templates/` (new or extended)
- **Size:** M | **Type:** build

## T6 — Web UI diff preview

- **Acceptance:** Each stash entry shows file list and content preview/diff
- **Verify:** Manual browser test with multi-file stash
- **Files:** `src/app.py`, templates
- **Size:** S | **Type:** build
- **Checkpoint:** CP3

## T7 — Final verification

- **Acceptance:** `make check` passes (lint, typecheck, test, boundaries); optional CLAUDE.md stash command note
- **Verify:** `make check`
- **Files:** repo-wide
- **Size:** S | **Type:** verify
