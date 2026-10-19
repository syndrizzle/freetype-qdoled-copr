#!/usr/bin/env python3
"""Import Fedora packaging without timestamps or deleting project-owned files."""

import argparse
from datetime import datetime
import json
import locale
import os
from pathlib import Path
import re
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parent.parent
PATCH = "freetype-qdoled-gen3-harmony.patch"
PROJECT_FILES = {PATCH, "README.md", "qdoled-release.json", ".fedora-files", ".gitignore"}


def replace_once(pattern, replacement, text):
    text, count = re.subn(pattern, replacement, text, flags=re.MULTILINE)
    if count != 1:
        raise ValueError(f"Fedora spec changed: expected one match for {pattern!r}, got {count}")
    return text


def transform_spec(text, revision):
    locale.setlocale(locale.LC_TIME, "C")
    version = re.search(r"^Version:\s+(\S+)$", text, re.MULTILINE).group(1)
    release = re.search(r"^Release:\s+(\d+)%\{\?dist\}$", text, re.MULTILINE)
    if not release:
        raise ValueError("Unsupported Fedora Release tag; review the downstream release suffix")
    release = f"{release.group(1)}.qdoled.{revision['release']}"
    text = replace_once(r"^Release:.*$", f"Release: {release}%{{?dist}}", text)
    text = text.replace("http://download.savannah.gnu.org/releases/freetype/",
                        "https://download-mirror.savannah.gnu.org/releases/freetype/")
    text = replace_once(r"^# Enable subpixel rendering \(ClearType\)\n", "", text)
    text = replace_once(r"^Patch0:\s+freetype-2\.3\.0-enable-spr\.patch\n", "", text)
    text = replace_once(r"^%patch\s+0\s+[^\n]*\n", "", text)
    if "FT_CONFIG_OPTION_SUBPIXEL_RENDERING" in text or re.search(r"^Patch100:", text, re.MULTILINE):
        raise ValueError("Fedora renderer configuration changed; review Harmony enablement")
    if not re.search(r"^BuildRequires:", text, re.MULTILINE):
        raise ValueError("Expected Fedora BuildRequires tags")
    text = re.sub(r"^BuildRequires:",
                  "# Use Harmony; do not enable FT_CONFIG_OPTION_SUBPIXEL_RENDERING.\n"
                  f"Patch100: {PATCH}\n\nBuildRequires:", text, count=1, flags=re.MULTILINE)
    text = replace_once(r"^%build$", "%patch 100 -p1 -b .qdoled-gen3-harmony\n\n%build", text)
    # Dates come from versioned inputs, never the clock on the polling runner.
    if "%changelog\n* " not in text:
        raise ValueError("Expected a conventional Fedora changelog")
    # The first 15 characters are e.g. 'Mon Apr 13 2026'.
    upstream_date = datetime.strptime(text.split("%changelog\n* ", 1)[1][:15], "%a %b %d %Y")
    local_date = datetime.strptime(revision["date"], "%Y-%m-%d")
    date = max(upstream_date, local_date).strftime("%a %b %d %Y")
    text = replace_once(r"^%changelog$", "%changelog\n"
                        f"* {date} Syn <syn@localhost> - {version}-{release}\n"
                        "- Use Harmony with experimental Gen 3 QD-OLED geometry\n", text)
    return text


def sync(repo, url, branch):
    revision = json.loads((repo / "qdoled-release.json").read_text())
    if not isinstance(revision["release"], int) or revision["release"] < 1:
        raise ValueError("qdoled-release.json release must be a positive integer")
    with tempfile.TemporaryDirectory(prefix="freetype-fedora-") as tmp:
        upstream = Path(tmp) / "upstream"
        subprocess.run(["git", "clone", "--quiet", "--depth=1", "--single-branch",
                        "--branch", branch, "--", url, str(upstream)], check=True)
        spec = transform_spec((upstream / "freetype.spec").read_text(), revision)
        # Import only files the spec actually uses. Never mirror/delete the repository root.
        names = {"freetype.spec", "sources"}
        for name in re.findall(r"^(?:Source\d*|Patch\d*):\s+(\S+)", spec, re.MULTILINE):
            if "://" not in name and name != PATCH:
                if Path(name).name != name or name in PROJECT_FILES:
                    raise ValueError(f"Unsupported source path: {name}")
                names.add(name)
        content = {name: (upstream / name).read_bytes() for name in names - {"freetype.spec"}}
        content["freetype.spec"] = spec.encode()
        managed = repo / ".fedora-files"
        old_names = set(managed.read_text().splitlines())
        if any(Path(name).name != name or name in PROJECT_FILES for name in old_names):
            raise ValueError("Unsafe .fedora-files entry")
        # All inputs are validated before changing the working tree.
        changed = []
        for name, data in sorted(content.items()):
            path = repo / name
            if not path.exists() or path.read_bytes() != data:
                path.write_bytes(data)
                changed.append(name)
        for name in sorted(old_names - names):
            path = repo / name
            if path.exists():
                path.unlink()
                changed.append(name)
        data = "\n".join(sorted(names)) + "\n"
        if managed.read_text() != data:
            managed.write_text(data)
            changed.append(managed.name)
        print("Updated: " + ", ".join(changed) if changed else "No Fedora packaging changes.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=ROOT)
    parser.add_argument("--upstream", default=os.environ.get("FEDORA_FREETYPE_DISTGIT",
                        "https://src.fedoraproject.org/rpms/freetype.git"))
    parser.add_argument("--branch", default=os.environ.get("FEDORA_FREETYPE_BRANCH", "f45"))
    args = parser.parse_args()
    sync(args.repo.resolve(), args.upstream, args.branch)


if __name__ == "__main__":
    main()
