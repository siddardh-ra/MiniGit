"""Tests for stash functionality."""

import json
import os
import shutil
import tempfile

import pytest

from backend.sqlite_client import SQLiteClient
from frontend.operations import Operations


class TestStashSQLite:
    """Verify stash persistence in SQLite."""

    def setup_method(self) -> None:
        self.fd, self.db_path = tempfile.mkstemp(suffix=".db")
        self.db = SQLiteClient(self.db_path)

    def teardown_method(self) -> None:
        self.db.close()
        os.close(self.fd)
        os.unlink(self.db_path)

    def test_save_and_list_stash(self) -> None:
        """Saved stash appears in list newest first."""
        snapshot = json.dumps([{"path": "a.txt", "action": "add", "blob_hash": "a" * 64}])
        self.db.save_stash("WIP", snapshot)
        stashes = self.db.list_stashes()
        assert len(stashes) == 1
        assert stashes[0]["message"] == "WIP"

    def test_get_stash_by_index(self) -> None:
        """get_stash returns correct entry by logical index."""
        self.db.save_stash("first", json.dumps([]))
        self.db.save_stash("second", json.dumps([]))
        assert self.db.get_stash(0)["message"] == "second"
        assert self.db.get_stash(1)["message"] == "first"

    def test_delete_stash_reindexes(self) -> None:
        """Deleting a stash removes it and remaining entries are accessible."""
        self.db.save_stash("a", json.dumps([]))
        self.db.save_stash("b", json.dumps([]))
        self.db.delete_stash(0)
        assert len(self.db.list_stashes()) == 1
        assert self.db.get_stash(0)["message"] == "a"

    def test_get_stash_out_of_range(self) -> None:
        """Out-of-range index returns None."""
        assert self.db.get_stash(0) is None

    def test_delete_stash_out_of_range_raises(self) -> None:
        """Deleting out-of-range index raises ValueError."""
        with pytest.raises(ValueError, match="out of range"):
            self.db.delete_stash(0)


class TestStashOperations:
    """Verify stash operations in the frontend layer."""

    def setup_method(self) -> None:
        self.tmpdir = tempfile.mkdtemp()
        with open(os.path.join(self.tmpdir, "README.md"), "w") as f:
            f.write("# Test\n")
        with open(os.path.join(self.tmpdir, "notes.txt"), "w") as f:
            f.write("notes\n")
        self.db_path = os.path.join(self.tmpdir, ".minigit", "minigit.db")

    def teardown_method(self) -> None:
        shutil.rmtree(self.tmpdir)

    def _init_ops(self) -> Operations:
        ops = Operations(self.tmpdir, self.db_path)
        ops.init_repo(author="Tester", message="init")
        return ops

    def test_stash_save_multiple_files(self) -> None:
        """stash_save captures multiple staged files."""
        ops = self._init_ops()
        ops.add("README.md")
        ops.add("notes.txt")
        index = ops.stash_save("WIP")
        assert index == 0
        assert len(ops.get_staged()) == 0
        stashes = ops.stash_list()
        assert len(stashes) == 1
        assert stashes[0]["file_count"] == 2

    def test_stash_save_empty_raises(self) -> None:
        """Saving with empty staging raises ValueError."""
        ops = self._init_ops()
        with pytest.raises(ValueError, match="Nothing staged"):
            ops.stash_save()

    def test_stash_apply_preserves_content(self) -> None:
        """Applying a stash restores staged files with blob content."""
        ops = self._init_ops()
        ops.add("README.md")
        ops.stash_save()
        ops.stash_apply(0)
        staged = ops.get_staged()
        assert len(staged) == 1
        assert staged[0]["path"] == "README.md"
        content = ops.get_blob_content(staged[0]["blob_hash"])
        assert content == "# Test\n"

    def test_stash_apply_keeps_stash(self) -> None:
        """Apply does not remove the stash from the stack."""
        ops = self._init_ops()
        ops.add("README.md")
        ops.stash_save()
        ops.stash_apply(0)
        assert len(ops.stash_list()) == 1

    def test_stash_pop_removes_from_stack(self) -> None:
        """Pop applies and removes the most recent stash."""
        ops = self._init_ops()
        ops.add("README.md")
        ops.stash_save()
        ops.stash_pop()
        assert len(ops.stash_list()) == 0
        assert len(ops.get_staged()) == 1

    def test_stash_pop_no_stashes_raises(self) -> None:
        """Pop with no stashes raises ValueError."""
        ops = self._init_ops()
        with pytest.raises(ValueError, match="No stashes"):
            ops.stash_pop()

    def test_stash_apply_non_empty_staging_raises(self) -> None:
        """Apply to non-empty staging raises ValueError."""
        ops = self._init_ops()
        ops.add("README.md")
        ops.stash_save()
        ops.add("notes.txt")
        with pytest.raises(ValueError, match="not empty"):
            ops.stash_apply(0)

    def test_stash_pop_non_empty_staging_raises(self) -> None:
        """Pop with non-empty staging raises ValueError."""
        ops = self._init_ops()
        ops.add("README.md")
        ops.stash_save()
        ops.add("notes.txt")
        with pytest.raises(ValueError, match="not empty"):
            ops.stash_pop()

    def test_stash_apply_bad_index_raises(self) -> None:
        """Apply with out-of-range index raises ValueError."""
        ops = self._init_ops()
        with pytest.raises(ValueError, match="out of range"):
            ops.stash_apply(0)

    def test_stash_drop_reindexes(self) -> None:
        """Dropping a stash re-indexes remaining entries."""
        ops = self._init_ops()
        ops.add("README.md")
        ops.stash_save("first")
        ops.add("notes.txt")
        ops.stash_save("second")
        ops.stash_drop(0)
        stashes = ops.stash_list()
        assert len(stashes) == 1
        assert stashes[0]["message"] == "first"

    def test_stash_list_newest_first(self) -> None:
        """Stash list orders newest first (index 0 = most recent)."""
        ops = self._init_ops()
        ops.add("README.md")
        ops.stash_save("older")
        ops.add("notes.txt")
        ops.stash_save("newer")
        stashes = ops.stash_list()
        assert stashes[0]["message"] == "newer"
        assert stashes[1]["message"] == "older"

    def test_stash_persists_across_sessions(self) -> None:
        """Stashes survive closing and reopening the database."""
        ops = self._init_ops()
        ops.add("README.md")
        ops.stash_save("persist")
        ops.db.close()
        ops2 = Operations(self.tmpdir, self.db_path)
        assert len(ops2.stash_list()) == 1
        ops2.db.close()
