repo_dir := $(abspath $(dir $(lastword $(MAKEFILE_LIST)))/..)
spec ?= $(repo_dir)/freetype.spec
outdir ?= $(repo_dir)/srpm

.PHONY: srpm
srpm:
	@# COPR's make_srpm root has rpm-build/make, but no Python interpreter.
	@# Spec BuildRequires are installed only later, for the binary RPM builds.
	@if ! command -v python3 >/dev/null 2>&1; then \
		dnf -y install python3; \
	fi
	python3 "$(repo_dir)/scripts/build-srpm.py" --spec "$(spec)" --outdir "$(outdir)" $(if $(cachedir),--cache-dir "$(cachedir)")
