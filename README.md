# freetype-qdoled-copr

FreeType RPMs for Fedora 44 and 45, with experimental Harmony subpixel geometry
for an Alienware AW2725D in its normal landscape orientation. Package names and
the shared-library ABI match Fedora's packages.

## What the rendering patch does

This build deliberately removes Fedora's ClearType-enabling patch.
[FreeType's documentation](https://freetype.org/freetype2/docs/reference/ft2-lcd_rendering.html)
confirms that Harmony requires `FT_CONFIG_OPTION_SUBPIXEL_RENDERING` to be
undefined and supports arbitrary RGB subpixel positions. The defaults here are
in RGB channel order, in 1/64-pixel units, with positive y pointing upwards:

```text
R = (-17, -18)
G = (  0,  16)
B = ( 17, -17)
```

These are experimental tuning values, not published Dell calibration data.
[Dell's AW2725D documentation](https://www.dell.com/support/product-details/en-sg/product/aw2725d-monitor/resources/manuals)
does not establish these precise subpixel centers. The runtime check verifies
that the library uses these values; visual improvement still needs comparison
on the actual monitor at native resolution and scale.

Applications must load this system library and request LCD subpixel rendering.
For applications that honor KDE/fontconfig settings, select **RGB** subpixel
antialiasing; BGR swaps the red and blue channels. Grayscale rendering is
unchanged. GTK 4's standard renderers use grayscale rather than component-alpha
subpixel rendering ([GTK explanation](https://blogs.gnome.org/gtk/2024/03/07/on-fractional-scales-fonts-and-hinting/)).
Flatpaks, containers, bundled renderers, and applications overriding LCD geometry
may not use this patch. This is a library-wide default, so it also affects text
on other monitors and does not automatically adapt to rotation. Restart
applications after installing it.

## Packaging and efficient builds

The shared SRPM now follows Fedora's **f45** FreeType packaging, built for both
Fedora 44 and 45. It includes Fedora 45's demo fixes and release bump; the old
`1.qdoled.1` release was lower than Fedora 45's stock release `2`.
This uses one upstream packaging baseline, not separate per-release source
branches: [COPR generates one SRPM per build](https://docs.copr.fedorainfracloud.org/user_documentation.html#scm).

The daily GitHub Action is only an **update check**. It clones the small Fedora
packaging repository, imports only the spec's required files, and commits only
changed bytes. Changelog dates come from Fedora's changelog and the versioned
`qdoled-release.json`, never the runner's current date. Unchanged polls produce
no commits. The previous script changed the changelog date every day, causing
the same RPM version to be rebuilt repeatedly.

The action publishes only committed build inputs to **`copr-build`**, and only
when their Git tree changes. COPR must track that branch. Documentation, tests,
sync implementation changes, and polling cannot independently trigger RPM builds.
The workflow serializes publishers and never force-pushes. No COPR credentials
are needed in GitHub Actions: the existing GitHub-to-COPR push webhook handles
the build-branch push.

`scripts/build-srpm.py` checks every downloaded archive against Fedora's SHA512
`sources` manifest before invoking `rpmbuild`. An optional content-addressed
cache avoids downloading the same archives for repeated local SRPM builds.
The Makefile installs Python only when it is missing: COPR's minimal SRPM
buildroot does not provide it, and the spec's `BuildRequires` are installed
later for binary builds. The source-build CI check starts without Python and
exercises this same Makefile entry point.

## Migrate an existing COPR project

First push/merge these changes into `main` and let **Sync Fedora freetype**
publish `copr-build` (or run the workflow manually). Then, with `copr-cli`
installed and your COPR API credentials in `~/.config/copr`, run:

```bash
./scripts/configure-copr.sh syndrizzle/freetype-qdoled-gen3
copr-cli build-package syndrizzle/freetype-qdoled-gen3 --name freetype \
  --chroot fedora-44-x86_64 --chroot fedora-44-i386 \
  --chroot fedora-45-x86_64 --chroot fedora-45-i386
```

The setup script enables all four targets, enables multilib, clears package
chroot exclusions, and switches the SCM package from `main` to `copr-build`.
It does not submit a build itself; the command above seeds the new targets once.
Future changed inputs build through the webhook. Keep the existing GitHub push
webhook enabled. Until this migration, COPR still tracks `main` and will build
on main-branch pushes, including documentation changes.

For a new project, create it with the four chroots above and `--multilib on`,
then add the SCM package after `copr-build` exists:

```bash
copr-cli add-package-scm <owner>/freetype-qdoled-gen3 \
  --name freetype \
  --clone-url https://github.com/<owner>/freetype-qdoled-copr.git \
  --commit copr-build --spec freetype.spec --method make_srpm \
  --webhook-rebuild on
```

Configure the project's GitHub push webhook as described in
[COPR's webhook guide](https://docs.copr.fedorainfracloud.org/user_documentation.html#webhooks),
then submit one initial build. GitHub Actions needs permission to push repository
contents, including the `copr-build` branch.

## Local validation and maintenance

```bash
python3 -m unittest discover -s tests -v
./scripts/sync-fedora.sh
rpmspec -q freetype.spec
make -f .copr/Makefile srpm outdir=/tmp/freetype-srpm cachedir=/tmp/freetype-cache
# In clean Fedora build environments, e.g. with mock installed:
mock -r fedora-44-x86_64 --rebuild /tmp/freetype-srpm/*.src.rpm
mock -r fedora-45-x86_64 --rebuild /tmp/freetype-srpm/*.src.rpm
```

To check the compiled renderer without installing the replacement system-wide,
extract the built runtime RPM into a temporary directory and run:

```bash
cc -Wall -Wextra -Werror $(pkg-config --cflags freetype2) tests/check-harmony.c \
  -o /tmp/check-harmony $(pkg-config --libs freetype2)
LD_LIBRARY_PATH=/path/to/extracted-rpm/usr/lib64 /tmp/check-harmony \
  "$(fc-match -f '%{file}' sans-serif)"
```

This compares the compiled defaults to explicitly requested QD-OLED geometry
across 32 glyph/size cases, verifies they differ from RGB stripes, and checks
that grayscale output is unchanged. Fedora's stock ClearType build should fail
the geometry API check, making it a useful negative control.

When changing downstream rendering or RPM content, increment `release` and set
the change date in `qdoled-release.json`, then run the sync. Commit those inputs
together with the generated spec. The suffix must increase so installed systems
receive the change. When moving to another Fedora baseline, update the sync's
default branch and verify every supported chroot before publishing. A changed
Fedora patch layout intentionally fails the sync for review.

## Install / rollback

After a successful build for your Fedora release:

```bash
sudo dnf copr enable syndrizzle/freetype-qdoled-gen3
sudo dnf distro-sync freetype freetype-devel freetype-demos
rpm -q freetype
```

To return to Fedora's packages:

```bash
sudo dnf copr remove syndrizzle/freetype-qdoled-gen3
sudo dnf distro-sync freetype freetype-devel freetype-demos
```

On systems with 32-bit applications, keep the installed x86_64 and i686
FreeType packages at matching versions. The COPR project's multilib setting
makes the i686 packages available alongside the x86_64 repository.
