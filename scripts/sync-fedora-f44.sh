#!/usr/bin/env bash
set -euo pipefail

upstream_url="${FEDORA_FREETYPE_DISTGIT:-https://src.fedoraproject.org/rpms/freetype.git}"
upstream_branch="${FEDORA_FREETYPE_BRANCH:-f44}"
repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
tmpdir="$(mktemp -d)"

cleanup() {
  rm -rf "$tmpdir"
}
trap cleanup EXIT

git clone --depth=1 --branch "$upstream_branch" "$upstream_url" "$tmpdir/upstream"

rsync -a --delete \
  --exclude '.git/' \
  --exclude '.copr/' \
  --exclude '.github/' \
  --exclude 'scripts/' \
  --exclude 'README.md' \
  --exclude 'freetype-qdoled-gen3-harmony.patch' \
  "$tmpdir/upstream/" "$repo_dir/"

spec="$repo_dir/freetype.spec"
version="$(awk '/^Version:[[:space:]]*/ { print $2; exit }' "$spec")"
base_release="$(awk '/^Release:[[:space:]]*/ { rel=$2; sub(/%\{\?dist\}$/, "", rel); print rel; exit }' "$spec")"
qdoled_release="${base_release}.qdoled.1"
changelog_date="$(date -u '+%a %b %d %Y')"

awk \
  -v version="$version" \
  -v qdoled_release="$qdoled_release" \
  -v changelog_date="$changelog_date" '
  /^Release:[[:space:]]*/ {
    print "Release: " qdoled_release "%{?dist}"
    next
  }

  /^Source:[[:space:]]+http:\/\/download\.savannah\.gnu\.org\/releases\/freetype\// {
    sub("http://download.savannah.gnu.org/releases/freetype/",
        "https://download-mirror.savannah.gnu.org/releases/freetype/")
    print
    next
  }

  /^Source[12]:[[:space:]]+http:\/\/download\.savannah\.gnu\.org\/releases\/freetype\// {
    sub("http://download.savannah.gnu.org/releases/freetype/",
        "https://download-mirror.savannah.gnu.org/releases/freetype/")
    print
    next
  }

  /^# Enable subpixel rendering \(ClearType\)$/ {
    print "# Fedora ClearType-style subpixel rendering patch is intentionally not"
    print "# applied in this build. QD-OLED Gen 3 geometry uses FreeType Harmony,"
    print "# which is compiled only when FT_CONFIG_OPTION_SUBPIXEL_RENDERING is undefined."
    next
  }

  /^Patch0:[[:space:]]*freetype-2\.3\.0-enable-spr\.patch/ {
    next
  }

  /^Patch100:[[:space:]]*freetype-qdoled-gen3-harmony\.patch/ {
    next
  }

  /^Patch5:[[:space:]]*/ {
    print
    print ""
    print "# Set FreeType Harmony LCD geometry for 27-inch Gen 3 QD-OLED panels."
    print "Patch100:  freetype-qdoled-gen3-harmony.patch"
    next
  }

  /^%patch[[:space:]]+0[[:space:]]/ {
    next
  }

  /^%patch[[:space:]]+100[[:space:]]/ {
    next
  }

  /^%patch[[:space:]]+5[[:space:]]/ {
    print
    print "%patch 100 -p1 -b .qdoled-gen3-harmony"
    next
  }

  /^%changelog$/ {
    print
    print "* " changelog_date " Syn <syn@localhost> - " version "-" qdoled_release
    print "- Disable ClearType-style subpixel rendering patch for Harmony LCD geometry"
    print "- Add Gen 3 QD-OLED Harmony geometry for AW2725D-class panels"
    print ""
    next
  }

  { print }
' "$spec" > "$spec.tmp"

mv "$spec.tmp" "$spec"
