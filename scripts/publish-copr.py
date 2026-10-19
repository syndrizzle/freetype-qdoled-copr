#!/usr/bin/env python3
"""Publish a build-input snapshot; documentation and polling never cause builds."""

import argparse
import os
from pathlib import Path
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parent.parent


def publish(repo, remote="origin", branch="copr-build"):
    def git(*args, **kwargs):
        return subprocess.check_output(["git", "-C", str(repo), *args], text=True, **kwargs).strip()

    ref = f"refs/heads/{branch}"
    git("check-ref-format", ref)
    # Read committed inputs so a developer's uncommitted files cannot be published.
    managed = git("show", "HEAD:.fedora-files").splitlines()
    names = sorted(set(managed + ["freetype-qdoled-gen3-harmony.patch",
                                 ".copr/Makefile", "scripts/build-srpm.py"]))
    if any(Path(name).is_absolute() or ".." in Path(name).parts for name in names):
        raise ValueError("Unsafe build input path")
    with tempfile.TemporaryDirectory(prefix="copr-index-") as tmp:
        env = dict(os.environ, GIT_INDEX_FILE=str(Path(tmp) / "index"))
        git("read-tree", "--empty", env=env)
        for name in names:
            entry = git("ls-tree", "HEAD", "--", name)
            metadata, actual_name = entry.split("\t", 1)
            mode, kind, oid = metadata.split()
            if actual_name != name or kind != "blob" or mode not in {"100644", "100755"}:
                raise ValueError(f"Expected a regular committed build input: {name}")
            git("update-index", "--add", "--cacheinfo", mode, oid, name, env=env)
        tree = git("write-tree", env=env)
    remote_ref = git("ls-remote", "--heads", remote, ref)
    parent = []
    if remote_ref:
        previous = remote_ref.split()[0]
        git("fetch", "--quiet", "--no-tags", remote, ref)
        if git("rev-parse", f"{previous}^{{tree}}") == tree:
            print("COPR build inputs unchanged; no push or build needed.")
            return False
        parent = ["-p", previous]
    source = git("rev-parse", "HEAD")
    commit = git("commit-tree", tree, *parent, "-m", f"Update COPR build inputs from {source}")
    # A normal fast-forward push rejects concurrent changes rather than overwriting them.
    git("push", remote, f"{commit}:{ref}")
    print(f"Published changed build inputs to {branch}.")
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=ROOT)
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--branch", default="copr-build")
    args = parser.parse_args()
    publish(args.repo.resolve(), args.remote, args.branch)
