#!/usr/bin/env python3
"""Build an SRPM using only sources verified against Fedora's sources manifest."""

import argparse
import hashlib
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from urllib.parse import urlparse
from urllib.request import urlopen


def manifest_checksums(text):
    checksums = {}
    for line in text.splitlines():
        match = re.fullmatch(r"SHA512 \(([^/()]+)\) = ([0-9a-f]{128})", line)
        if not match or match[1] in checksums:
            raise ValueError(f"Unsupported or duplicate Fedora sources entry: {line}")
        checksums[match[1]] = match[2]
    if not checksums:
        raise ValueError("Empty Fedora sources manifest")
    return checksums


def verify_source(path, checksum):
    with path.open("rb") as stream:
        actual = hashlib.file_digest(stream, "sha512").hexdigest()
    if actual != checksum:
        raise ValueError(f"SHA512 mismatch for {path.name}")


def build(spec, outdir, cachedir):
    spec = spec.resolve()
    source_dir = spec.parent
    checksums = manifest_checksums((source_dir / "sources").read_text())
    parsed = subprocess.check_output(["rpmspec", "--parse", str(spec)], text=True)
    entries = re.findall(r"^(?:Source\d*|Patch\d*):\s+(\S+)", parsed, re.MULTILINE)
    remote_names = {Path(urlparse(entry).path).name for entry in entries if "://" in entry}
    if remote_names != checksums.keys():
        raise ValueError("Spec downloads and Fedora sources manifest do not match")
    outdir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="freetype-srpm-") as tmp:
        staged = Path(tmp)
        for entry in entries:
            remote = "://" in entry
            name = Path(urlparse(entry).path).name
            dest = staged / name
            if not remote:
                if entry != name:
                    raise ValueError(f"Unsupported local source path: {entry}")
                shutil.copyfile(source_dir / name, dest)
                continue
            if urlparse(entry).scheme != "https":
                raise ValueError(f"Source must use HTTPS: {entry}")
            checksum = checksums[name]
            local = source_dir / name
            cached = cachedir / checksum / name if cachedir else None
            if local.is_file():
                verify_source(local, checksum)
                shutil.copyfile(local, dest)
            elif cached and cached.is_file():
                verify_source(cached, checksum)
                shutil.copyfile(cached, dest)
            else:
                print(f"Downloading {name}", flush=True)
                with urlopen(entry, timeout=120) as response, dest.open("wb") as target:
                    if urlparse(response.url).scheme != "https":
                        raise ValueError("Insecure source redirect")
                    shutil.copyfileobj(response, target)
                verify_source(dest, checksum)
                if cached:
                    cached.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(dest, cached)
        subprocess.run(["rpmbuild", "-bs", "--define", f"_sourcedir {staged}",
                        "--define", f"_srcrpmdir {outdir.resolve()}",
                        "--define", "_disable_source_fetch 1", str(spec)], check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, default=Path("freetype.spec"))
    parser.add_argument("--outdir", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path)
    args = parser.parse_args()
    build(args.spec, args.outdir, args.cache_dir)


if __name__ == "__main__":
    main()
