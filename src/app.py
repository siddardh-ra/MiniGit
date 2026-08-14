"""MiniGit Flask web application — browse repositories, commits, trees, and diffs."""

from __future__ import annotations

import difflib
import json
import os
import sys
from typing import Any

import structlog

sys.path.insert(0, os.path.dirname(__file__))

from flask import Flask, flash, jsonify, redirect, render_template, request, url_for
from frontend.operations import Operations

logger = structlog.get_logger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get("MINIGIT_SECRET_KEY", "minigit-secret-key")

REPOS_DIR: str = os.path.join(os.path.dirname(__file__), "..", "repos")
os.makedirs(REPOS_DIR, exist_ok=True)

REGISTRY_FILE: str = os.path.join(REPOS_DIR, "repos.json")


def _load_registry() -> dict[str, str]:
    """Load the repo registry mapping names to absolute paths."""
    if os.path.isfile(REGISTRY_FILE):
        with open(REGISTRY_FILE, "r") as f:
            return json.load(f)
    return {}


def _save_registry(registry: dict[str, str]) -> None:
    """Persist the repo registry to disk."""
    with open(REGISTRY_FILE, "w") as f:
        json.dump(registry, f, indent=2)


def _sync_registry() -> dict[str, str]:
    """Merge legacy repos/ subdirectories into the registry."""
    registry = _load_registry()
    for name in os.listdir(REPOS_DIR):
        full = os.path.join(REPOS_DIR, name)
        if os.path.isdir(os.path.join(full, ".minigit")) and name not in registry:
            registry[name] = os.path.abspath(full)
    _save_registry(registry)
    return registry


def get_ops_by_path(repo_path: str) -> Operations:
    """Create an Operations instance from an absolute repo path."""
    db_path = os.path.join(repo_path, ".minigit", "minigit.db")
    return Operations(repo_path, db_path)


def get_ops(repo_name: str) -> Operations:
    """Look up a repo by name in the registry and return Operations."""
    registry = _load_registry()
    if repo_name in registry:
        return get_ops_by_path(registry[repo_name])
    repo_path = os.path.join(REPOS_DIR, repo_name)
    db_path = os.path.join(repo_path, ".minigit", "minigit.db")
    return Operations(repo_path, db_path)


@app.route("/")
def index() -> str:
    """Render the homepage listing all registered repositories."""
    registry = _sync_registry()
    repos: list[dict[str, Any]] = []
    for name, path in sorted(registry.items()):
        if not os.path.isdir(os.path.join(path, ".minigit")):
            continue
        ops = get_ops_by_path(path)
        branches = ops.get_all_branches()
        history = ops.get_commit_history()
        repos.append({
            "name": name,
            "path": path,
            "branches": len(branches),
            "commits": len(history),
            "last_commit": history[0] if history else None,
        })
    return render_template("index.html", repos=repos)


@app.route("/api/suggest-dirs")
def suggest_dirs() -> Any:
    """Return JSON array of directory suggestions for autocomplete."""
    q = request.args.get("q", "").strip()
    if not q:
        q = os.path.expanduser("~")
    q = os.path.expanduser(q)

    if os.path.isdir(q):
        parent = q
        prefix = ""
    else:
        parent = os.path.dirname(q)
        prefix = os.path.basename(q).lower()

    if not os.path.isdir(parent):
        return jsonify([])

    results: list[str] = []
    try:
        for name in sorted(os.listdir(parent)):
            full = os.path.join(parent, name)
            if not os.path.isdir(full):
                continue
            if name.startswith("."):
                continue
            if prefix and not name.lower().startswith(prefix):
                continue
            results.append(full)
            if len(results) >= 15:
                break
    except PermissionError:
        pass
    return jsonify(results)


@app.route("/new-repo", methods=["POST"])
def new_repo() -> Any:
    """Handle new repository creation or registration."""
    dir_path = request.form.get("path", "").strip()
    custom_name = request.form.get("name", "").strip()

    if dir_path:
        dir_path = os.path.expanduser(dir_path)
        dir_path = os.path.abspath(dir_path)

        if not os.path.isdir(dir_path):
            flash(f"Directory does not exist: {dir_path}", "error")
            return redirect(url_for("index"))

        name = custom_name or os.path.basename(dir_path)
        registry = _load_registry()
        if name in registry:
            flash(f"Repository '{name}' already registered", "error")
            return redirect(url_for("index"))

        ops = get_ops_by_path(dir_path)
        if not os.path.isdir(os.path.join(dir_path, ".minigit")):
            ops.init_repo(message="Initial commit")

        registry[name] = dir_path
        _save_registry(registry)
        logger.info("repo_registered", name=name, path=dir_path)
        flash(f"Repository '{name}' added from {dir_path}", "success")
        return redirect(url_for("repo_detail", repo_name=name))

    if not custom_name:
        flash("Enter a directory path or a new repository name", "error")
        return redirect(url_for("index"))

    name = custom_name
    repo_path = os.path.join(REPOS_DIR, name)
    if os.path.exists(repo_path):
        flash(f"Repository '{name}' already exists", "error")
        return redirect(url_for("index"))

    os.makedirs(repo_path, exist_ok=True)
    readme_path = os.path.join(repo_path, "README.md")
    with open(readme_path, "w") as f:
        f.write(f"# {name}\n")

    ops = get_ops_by_path(repo_path)
    ops.init_repo(message="Initial commit")
    registry = _load_registry()
    registry[name] = os.path.abspath(repo_path)
    _save_registry(registry)
    logger.info("repo_created", name=name)
    flash(f"Repository '{name}' created", "success")
    return redirect(url_for("repo_detail", repo_name=name))


@app.route("/repo/<repo_name>")
def repo_detail(repo_name: str) -> str:
    """Render the repository detail page with branch info and latest tree."""
    ops = get_ops(repo_name)
    branch = request.args.get("branch", "main")
    branches = ops.get_all_branches()
    history = ops.get_commit_history(branch)
    latest = history[0] if history else None

    tree_entries: list[dict[str, str]] = []
    if latest:
        tree_entries = ops.browse_tree(latest["tree_hash"])

    return render_template(
        "repo_detail.html",
        repo_name=repo_name,
        branch=branch,
        branches=branches,
        latest_commit=latest,
        tree_entries=tree_entries,
    )


@app.route("/repo/<repo_name>/tree/<tree_hash>")
def browse_tree(repo_name: str, tree_hash: str) -> str:
    """Render the tree browser showing entries at a given tree hash."""
    ops = get_ops(repo_name)
    entries = ops.browse_tree(tree_hash)
    parent = request.args.get("parent", "")
    return render_template(
        "browse_tree.html",
        repo_name=repo_name,
        tree_hash=tree_hash,
        entries=entries,
        parent_path=parent,
    )


@app.route("/repo/<repo_name>/blob/<blob_hash>")
def view_blob(repo_name: str, blob_hash: str) -> str:
    """Render the blob viewer showing file content."""
    ops = get_ops(repo_name)
    content = ops.get_blob_content(blob_hash)
    filename = request.args.get("name", "file")
    return render_template(
        "view_blob.html",
        repo_name=repo_name,
        blob_hash=blob_hash,
        content=content,
        filename=filename,
    )


@app.route("/repo/<repo_name>/history")
def commit_history(repo_name: str) -> str:
    """Render the commit history timeline for a branch."""
    ops = get_ops(repo_name)
    branch = request.args.get("branch", "main")
    branches = ops.get_all_branches()
    history = ops.get_commit_history(branch)
    return render_template(
        "commit_history.html",
        repo_name=repo_name,
        branch=branch,
        branches=branches,
        history=history,
    )


@app.route("/repo/<repo_name>/commit/<commit_hash>")
def commit_detail(repo_name: str, commit_hash: str) -> str | Any:
    """Render commit detail page with metadata and file diffs."""
    ops = get_ops(repo_name)
    commit_data = ops.get_commit(commit_hash)
    if not commit_data:
        flash("Commit not found", "error")
        return redirect(url_for("repo_detail", repo_name=repo_name))

    diffs: list[dict[str, Any]] = []
    if commit_data["parent_hash"]:
        diffs = ops.get_diffs(commit_data["parent_hash"], commit_hash)
        for d in diffs:
            d["diff_lines"] = list(difflib.unified_diff(
                d["old_content"].splitlines(keepends=True),
                d["new_content"].splitlines(keepends=True),
                fromfile=f"a/{d['path']}",
                tofile=f"b/{d['path']}",
                lineterm="",
            ))
    else:
        tree_files = ops._flatten_tree(commit_data["tree_hash"])
        for path, blob_hash in sorted(tree_files.items()):
            content = ops.get_blob_content(blob_hash) or ""
            diff_lines = [f"+{line}" for line in content.splitlines()]
            diffs.append({
                "path": path,
                "status": "added",
                "diff_lines": ["--- /dev/null", f"+++ b/{path}"] + diff_lines,
            })

    return render_template(
        "commit_detail.html",
        repo_name=repo_name,
        commit=commit_data,
        diffs=diffs,
    )


@app.route("/repo/<repo_name>/new-branch", methods=["POST"])
def new_branch(repo_name: str) -> Any:
    """Handle branch creation form submission."""
    ops = get_ops(repo_name)
    branch_name = request.form.get("name", "").strip()
    try:
        ops.create_branch(branch_name)
        flash(f"Branch '{branch_name}' created", "success")
    except ValueError as e:
        flash(str(e), "error")
    return redirect(url_for("repo_detail", repo_name=repo_name))


@app.route("/repo/<repo_name>/working-dir")
def working_dir(repo_name: str) -> str:
    """Render the working directory browser with staging status."""
    ops = get_ops(repo_name)
    subdir = request.args.get("path", "")
    items = ops.get_working_dir_files(subdir)
    staged = ops.get_staged()
    staged_paths = {s["path"] for s in staged}
    return render_template(
        "working_dir.html",
        repo_name=repo_name,
        subdir=subdir,
        items=items,
        staged=staged,
        staged_paths=staged_paths,
    )


@app.route("/repo/<repo_name>/stage", methods=["POST"])
def stage_file(repo_name: str) -> Any:
    """Handle file staging form submission."""
    ops = get_ops(repo_name)
    file_path = request.form.get("path", "").strip()
    subdir = request.form.get("subdir", "")
    try:
        ops.add(file_path)
        flash(f"Staged: {file_path}", "success")
    except (FileNotFoundError, ValueError) as e:
        flash(str(e), "error")
    return redirect(url_for("working_dir", repo_name=repo_name, path=subdir))


@app.route("/repo/<repo_name>/unstage", methods=["POST"])
def unstage_file(repo_name: str) -> Any:
    """Handle file unstaging form submission."""
    ops = get_ops(repo_name)
    file_path = request.form.get("path", "").strip()
    ops.db.cursor.execute("DELETE FROM staging WHERE path = ?", (file_path,))
    ops.db.conn.commit()
    flash(f"Unstaged: {file_path}", "success")
    return redirect(url_for("working_dir", repo_name=repo_name))


@app.route("/repo/<repo_name>/stage-delete", methods=["POST"])
def stage_delete(repo_name: str) -> Any:
    """Handle file deletion staging form submission."""
    ops = get_ops(repo_name)
    file_path = request.form.get("path", "").strip()
    try:
        ops.delete_file(file_path)
        flash(f"Staged for deletion: {file_path}", "success")
    except (FileNotFoundError, ValueError) as e:
        flash(str(e), "error")
    return redirect(url_for("working_dir", repo_name=repo_name))


@app.route("/repo/<repo_name>/commit", methods=["POST"])
def create_commit(repo_name: str) -> Any:
    """Handle commit creation form submission."""
    ops = get_ops(repo_name)
    message = request.form.get("message", "").strip()
    if not message:
        flash("Commit message is required", "error")
        return redirect(url_for("working_dir", repo_name=repo_name))
    try:
        commit_hash = ops.create_new_commit(message)
        flash(f"Committed: {commit_hash[:8]}", "success")
    except ValueError as e:
        flash(str(e), "error")
    return redirect(url_for("repo_detail", repo_name=repo_name))


@app.route("/repo/<repo_name>/stash-save", methods=["POST"])
def stash_save(repo_name: str) -> Any:
    """Save staged changes to the stash stack."""
    ops = get_ops(repo_name)
    message = request.form.get("message", "").strip() or None
    try:
        index = ops.stash_save(message)
        flash(f"Stashed changes at index {index}", "success")
    except ValueError as e:
        flash(str(e), "error")
    return redirect(url_for("working_dir", repo_name=repo_name))


@app.route("/repo/<repo_name>/stashes")
def stash_list(repo_name: str) -> str:
    """Render the stash list page."""
    ops = get_ops(repo_name)
    stashes = ops.stash_list()
    return render_template(
        "stashes.html",
        repo_name=repo_name,
        stashes=stashes,
    )


@app.route("/repo/<repo_name>/stashes/<int:index>")
def stash_detail(repo_name: str, index: int) -> str | Any:
    """Render stash detail with diff preview."""
    ops = get_ops(repo_name)
    try:
        snapshot = ops.get_stash_snapshot(index)
    except ValueError:
        flash("Stash not found", "error")
        return redirect(url_for("stash_list", repo_name=repo_name))

    stashes = ops.stash_list()
    stash_meta = next((s for s in stashes if s["index"] == index), None)
    if stash_meta is None:
        flash("Stash not found", "error")
        return redirect(url_for("stash_list", repo_name=repo_name))

    preview: list[dict[str, Any]] = []
    for entry in snapshot:
        content = ""
        if entry["action"] == "add" and entry.get("blob_hash"):
            content = ops.get_blob_content(entry["blob_hash"]) or ""
        preview.append({
            "path": entry["path"],
            "action": entry["action"],
            "content": content,
        })

    return render_template(
        "stash_detail.html",
        repo_name=repo_name,
        stash=stash_meta,
        preview=preview,
    )


@app.route("/repo/<repo_name>/stashes/<int:index>/apply", methods=["POST"])
def stash_apply(repo_name: str, index: int) -> Any:
    """Apply a stash to the staging area."""
    ops = get_ops(repo_name)
    try:
        ops.stash_apply(index)
        flash(f"Applied stash@{index}", "success")
    except ValueError as e:
        flash(str(e), "error")
    return redirect(url_for("stash_list", repo_name=repo_name))


@app.route("/repo/<repo_name>/stashes/<int:index>/drop", methods=["POST"])
def stash_drop(repo_name: str, index: int) -> Any:
    """Delete a stash without applying."""
    ops = get_ops(repo_name)
    try:
        ops.stash_drop(index)
        flash(f"Dropped stash@{index}", "success")
    except ValueError as e:
        flash(str(e), "error")
    return redirect(url_for("stash_list", repo_name=repo_name))


if __name__ == "__main__":
    app.run(debug=True, port=5000)
