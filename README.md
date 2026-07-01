# freetype-qdoled-copr

Fedora 44 `freetype` packaging with FreeType Harmony LCD geometry tuned for
27-inch Gen 3 Samsung QD-OLED panels such as the Alienware AW2725D.

This is a drop-in replacement for Fedora's `freetype` RPMs. It keeps the Fedora
package names and ABI, but it does not apply Fedora's ClearType-style
`FT_CONFIG_OPTION_SUBPIXEL_RENDERING` patch. That is intentional: FreeType's
custom LCD geometry path is compiled only for the Harmony renderer.

## Geometry

The patch changes FreeType's default Harmony subpixel centers to:

```text
R = (-17, -18)
G = (  0,  16)
B = ( 17, -17)
```

## Copr Setup

Create the project with Fedora 44 multilib chroots:

```bash
copr-cli create freetype-qdoled-gen3 \
  --chroot fedora-44-x86_64 \
  --chroot fedora-44-i386 \
  --multilib on \
  --description "Fedora freetype rebuilt with Gen 3 QD-OLED Harmony LCD geometry" \
  --instructions "Enable with: sudo dnf copr enable <owner>/freetype-qdoled-gen3 && sudo dnf distro-sync freetype freetype-devel freetype-demos"
```

Add the package as an SCM package:

```bash
copr-cli add-package-scm freetype-qdoled-gen3 \
  --name freetype \
  --clone-url https://github.com/<owner>/freetype-qdoled-copr.git \
  --commit main \
  --spec freetype.spec \
  --method make_srpm \
  --webhook-rebuild on
```

Trigger the first build:

```bash
copr-cli build-package freetype-qdoled-gen3 --name freetype
```

## Local Checks

```bash
rpmspec -q freetype.spec
make -f .copr/Makefile srpm outdir=/tmp/freetype-qdoled-srpm spec=freetype.spec
```

## Install

```bash
sudo dnf copr enable <owner>/freetype-qdoled-gen3
sudo dnf distro-sync freetype freetype-devel freetype-demos
rpm -q freetype
```

## Rollback

```bash
sudo dnf copr remove <owner>/freetype-qdoled-gen3
sudo dnf distro-sync freetype freetype-devel freetype-demos
```
