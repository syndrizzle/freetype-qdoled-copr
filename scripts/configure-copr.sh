#!/usr/bin/env bash
# Run after pushing these changes and publishing the copr-build branch.
set -euo pipefail
project="${1:-syndrizzle/freetype-qdoled-gen3}"
command -v copr-cli >/dev/null || { echo 'Install copr-cli and configure ~/.config/copr first.' >&2; exit 1; }
repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
git -C "$repo_dir" ls-remote --exit-code --heads origin refs/heads/copr-build >/dev/null || {
  echo 'Publish the copr-build branch before switching COPR to it.' >&2
  exit 1
}
copr-cli modify "$project" \
  --chroot fedora-44-x86_64 --chroot fedora-44-i386 \
  --chroot fedora-45-x86_64 --chroot fedora-45-i386 \
  --multilib on --follow-fedora-branching on
copr-cli edit-package-scm "$project" --name freetype \
  --commit copr-build --spec freetype.spec --method make_srpm \
  --chroot-denylist '' --webhook-rebuild on
echo 'COPR now tracks copr-build for Fedora 44/45, including multilib.'
echo 'If these inputs were already published before this configuration, trigger one initial build:'
echo "copr-cli build-package $project --name freetype --chroot fedora-44-x86_64 --chroot fedora-44-i386 --chroot fedora-45-x86_64 --chroot fedora-45-i386"
