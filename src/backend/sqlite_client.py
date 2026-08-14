"""SQLite persistence layer for MiniGit objects (blobs, trees, commits, refs)."""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

_HEX_HASH = re.compile(r"^[0-9a-f]{64}$")
_REF_NAME = re.compile(r"^[A-Za-z0-9_.\-/]+$")


def _validate_hash(value: str, label: str = "hash") -> None:
    """Raise ValueError if *value* is not a valid 64-char hex hash."""
    if not isinstance(value, str) or not _HEX_HASH.match(value):
        raise ValueError(f"Invalid {label}: expected 64-char hex string, got {value!r}")


def _validate_ref_name(name: str) -> None:
    """Raise ValueError if *name* is not a valid ref name."""
    if not isinstance(name, str) or not _REF_NAME.match(name):
        raise ValueError(
            f"Invalid ref name: must be alphanumeric/dash/underscore/dot, got {name!r}"
        )


def _validate_str(value: str, label: str, max_len: int = 10000) -> None:
    """Raise TypeError/ValueError if *value* is not a string within limits."""
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string, got {type(value).__name__}")
    if len(value) > max_len:
        raise ValueError(f"{label} exceeds max length of {max_len}")


class SQLiteClient:
    """Manages a SQLite database storing MiniGit objects.

    Tables: blobs, trees, commits, refs, staging.
    All write operations validate inputs before executing queries.
    """

    def __init__(self, db_path: str) -> None:
        logger.debug("opening_database", path=db_path)
        self.conn: sqlite3.Connection = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.cursor: sqlite3.Cursor = self.conn.cursor()
        self._init_tables()

    def _init_tables(self) -> None:
        """Create tables if they do not already exist."""
        self.cursor.executescript("""
            CREATE TABLE IF NOT EXISTS blobs (
                hash TEXT PRIMARY KEY,
                data TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS trees (
                hash TEXT PRIMARY KEY,
                entries TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS commits (
                hash TEXT PRIMARY KEY,
                tree_hash TEXT NOT NULL,
                parent_hash TEXT,
                author TEXT NOT NULL,
                message TEXT NOT NULL,
                timestamp TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS refs (
                name TEXT PRIMARY KEY,
                commit_hash TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS staging (
                path TEXT PRIMARY KEY,
                action TEXT NOT NULL,
                blob_hash TEXT
            );
            CREATE TABLE IF NOT EXISTS stashes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                message TEXT,
                staged_snapshot_json TEXT NOT NULL
            );
        """)
        self.conn.commit()

    def store_blob(self, hash: str, data: str) -> None:
        """Persist a blob by its hash. Ignores duplicates."""
        _validate_hash(hash, "blob hash")
        _validate_str(data, "blob data", max_len=10_000_000)
        self.cursor.execute(
            "INSERT OR IGNORE INTO blobs (hash, data) VALUES (?, ?)",
            (hash, data),
        )
        self.conn.commit()
        logger.debug("stored_blob", hash=hash[:8])

    def get_blob(self, hash: str) -> str | None:
        """Retrieve blob data by hash, or None if not found."""
        _validate_hash(hash, "blob hash")
        self.cursor.execute("SELECT data FROM blobs WHERE hash = ?", (hash,))
        row = self.cursor.fetchone()
        return row["data"] if row else None

    def store_tree(self, hash: str, entries_json: str) -> None:
        """Persist a tree's JSON-encoded entries. Ignores duplicates."""
        _validate_hash(hash, "tree hash")
        _validate_str(entries_json, "tree entries")
        self.cursor.execute(
            "INSERT OR IGNORE INTO trees (hash, entries) VALUES (?, ?)",
            (hash, entries_json),
        )
        self.conn.commit()

    def get_tree(self, hash: str) -> str | None:
        """Retrieve tree entries JSON by hash, or None if not found."""
        _validate_hash(hash, "tree hash")
        self.cursor.execute("SELECT entries FROM trees WHERE hash = ?", (hash,))
        row = self.cursor.fetchone()
        return row["entries"] if row else None

    def store_commit(
        self,
        hash: str,
        tree_hash: str,
        parent_hash: str | None,
        author: str,
        message: str,
        timestamp: str,
    ) -> None:
        """Persist a commit object. Validates all fields before insert."""
        _validate_hash(hash, "commit hash")
        _validate_hash(tree_hash, "tree hash")
        if parent_hash is not None:
            _validate_hash(parent_hash, "parent hash")
        _validate_str(author, "author", max_len=200)
        _validate_str(message, "commit message", max_len=5000)
        _validate_str(timestamp, "timestamp", max_len=50)
        self.cursor.execute(
            "INSERT OR IGNORE INTO commits "
            "(hash, tree_hash, parent_hash, author, message, timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (hash, tree_hash, parent_hash, author, message, timestamp),
        )
        self.conn.commit()
        logger.info("stored_commit", hash=hash[:8], message=message)

    def get_commit(self, hash: str) -> dict[str, Any] | None:
        """Retrieve a commit by hash, or None if not found."""
        _validate_hash(hash, "commit hash")
        self.cursor.execute("SELECT * FROM commits WHERE hash = ?", (hash,))
        row = self.cursor.fetchone()
        return dict(row) if row else None

    def get_all_commits(self) -> list[dict[str, Any]]:
        """Return all commits ordered by timestamp descending."""
        self.cursor.execute("SELECT * FROM commits ORDER BY timestamp DESC")
        return [dict(row) for row in self.cursor.fetchall()]

    def set_ref(self, name: str, commit_hash: str) -> None:
        """Create or update a ref (branch or HEAD)."""
        _validate_ref_name(name)
        if name == "HEAD":
            _validate_ref_name(commit_hash)
        else:
            _validate_hash(commit_hash, "commit hash")
        self.cursor.execute(
            "INSERT OR REPLACE INTO refs (name, commit_hash) VALUES (?, ?)",
            (name, commit_hash),
        )
        self.conn.commit()
        logger.debug("set_ref", name=name, target=commit_hash[:8])

    def get_ref(self, name: str) -> str | None:
        """Retrieve the commit hash a ref points to, or None if not found."""
        _validate_ref_name(name)
        self.cursor.execute("SELECT commit_hash FROM refs WHERE name = ?", (name,))
        row = self.cursor.fetchone()
        return row["commit_hash"] if row else None

    def get_all_refs(self) -> list[dict[str, str]]:
        """Return all refs as a list of {name, commit_hash} dicts."""
        self.cursor.execute("SELECT name, commit_hash FROM refs")
        return [dict(row) for row in self.cursor.fetchall()]

    def delete_ref(self, name: str) -> None:
        """Delete a ref by name."""
        _validate_ref_name(name)
        self.cursor.execute("DELETE FROM refs WHERE name = ?", (name,))
        self.conn.commit()
        logger.info("deleted_ref", name=name)

    def stage_file(self, path: str, action: str, blob_hash: str | None = None) -> None:
        """Stage a file for the next commit. Action must be 'add' or 'delete'."""
        _validate_str(path, "file path", max_len=1000)
        if action not in ("add", "delete"):
            raise ValueError(f"Invalid action: {action!r}")
        if action == "add" and blob_hash:
            _validate_hash(blob_hash, "blob hash")
        self.cursor.execute(
            "INSERT OR REPLACE INTO staging (path, action, blob_hash) VALUES (?, ?, ?)",
            (path, action, blob_hash),
        )
        self.conn.commit()

    def get_staged(self) -> list[dict[str, Any]]:
        """Return all currently staged file entries."""
        self.cursor.execute("SELECT path, action, blob_hash FROM staging")
        return [dict(row) for row in self.cursor.fetchall()]

    def clear_staging(self) -> None:
        """Remove all entries from the staging area."""
        self.cursor.execute("DELETE FROM staging")
        self.conn.commit()

    def save_stash(self, message: str | None, snapshot_json: str) -> int:
        """Persist a stash snapshot. Returns the new stash row id."""
        _validate_str(snapshot_json, "staged snapshot")
        if message is not None:
            _validate_str(message, "stash message", max_len=1000)
        timestamp = datetime.now(timezone.utc).isoformat()
        self.cursor.execute(
            "INSERT INTO stashes (timestamp, message, staged_snapshot_json) VALUES (?, ?, ?)",
            (timestamp, message, snapshot_json),
        )
        self.conn.commit()
        return int(self.cursor.lastrowid)

    def list_stashes(self) -> list[dict[str, Any]]:
        """Return all stashes ordered newest first."""
        self.cursor.execute(
            "SELECT id, timestamp, message, staged_snapshot_json "
            "FROM stashes ORDER BY id DESC"
        )
        return [dict(row) for row in self.cursor.fetchall()]

    def get_stash(self, index: int) -> dict[str, Any] | None:
        """Return stash at logical index (0 = newest), or None if out of range."""
        if not isinstance(index, int) or index < 0:
            raise ValueError(f"Invalid stash index: {index!r}")
        stashes = self.list_stashes()
        if index >= len(stashes):
            return None
        return stashes[index]

    def delete_stash(self, index: int) -> None:
        """Delete stash at logical index (0 = newest)."""
        stash = self.get_stash(index)
        if stash is None:
            raise ValueError(f"Stash index {index} out of range")
        self.cursor.execute("DELETE FROM stashes WHERE id = ?", (stash["id"],))
        self.conn.commit()

    def close(self) -> None:
        """Close the database connection."""
        self.conn.close()
        logger.debug("closed_database")
