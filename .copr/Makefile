srpm:
	mkdir -p "$(outdir)"
	tmpdir="$$(mktemp -d)"; \
	trap 'rm -rf "$$tmpdir"' EXIT; \
	find . -maxdepth 1 -type f -exec cp -p {} "$$tmpdir"/ \; ; \
	rpmbuild -bs \
		--define "_sourcedir $$tmpdir" \
		--define "_srcrpmdir $(outdir)" \
		--define "_disable_source_fetch 0" \
		"$(spec)"
