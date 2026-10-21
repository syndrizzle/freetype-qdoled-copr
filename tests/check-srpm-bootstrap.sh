#!/usr/bin/env bash
# Run inside a fresh Fedora container as root, with no Python preinstalled.
set -euo pipefail
repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"

assert_no_python() {
  if command -v python3 >/dev/null 2>&1; then
    echo 'Test fixture must start without Python to cover the COPR bootstrap failure.' >&2
    exit 1
  fi
}

assert_no_python
# These tools are already supplied by COPR's make_srpm buildroot.
dnf -y --setopt=install_weak_deps=False install make rpm-build redhat-rpm-config ca-certificates
assert_no_python
make -f "$repo_dir/.copr/Makefile" srpm \
  spec="$repo_dir/freetype.spec" outdir=/tmp/srpm-bootstrap-result
command -v python3
shopt -s nullglob
srpms=(/tmp/srpm-bootstrap-result/*.src.rpm)
test "${#srpms[@]}" -eq 1
rpm -qp --qf 'PASS: COPR source entry point produced %{NAME}-%{VERSION}-%{RELEASE}.src.rpm\n' "${srpms[0]}"
