repo_dir := $(abspath $(dir $(lastword $(MAKEFILE_LIST)))/..)
spec ?= $(repo_dir)/freetype.spec
outdir ?= $(repo_dir)/srpm

.PHONY: srpm
srpm:
	python3 "$(repo_dir)/scripts/build-srpm.py" --spec "$(spec)" --outdir "$(outdir)" $(if $(cachedir),--cache-dir "$(cachedir)")
