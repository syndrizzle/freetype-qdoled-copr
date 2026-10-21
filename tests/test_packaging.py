import hashlib
import importlib.util
import json
import os
from datetime import datetime
from pathlib import Path
import subprocess
import shutil
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parent.parent


def load_module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sync = load_module("sync-fedora")
srpm = load_module("build-srpm")
publisher = load_module("publish-copr")

FEDORA_SPEC = """Name: freetype
Version: 2.14.3
Release: 2%{?dist}
Source: http://download.savannah.gnu.org/releases/freetype/freetype-%{version}.tar.xz
Source3: ftconfig.h
# Enable subpixel rendering (ClearType)
Patch0: freetype-2.3.0-enable-spr.patch
Patch5: freetype-2.10.0-internal-outline.patch
BuildRequires: gcc
BuildRequires: make
%prep
%setup -q
%patch 0 -p1 -b .enable-spr
%patch 5 -p1
%build
make
%changelog
* Wed Jul 15 2026 Fedora Release Engineering <releng@fedoraproject.org> - 2.14.3-2
- Mass rebuild
"""


def git(directory, *args):
    return subprocess.check_output(["git", "-C", str(directory), *args], stderr=subprocess.DEVNULL)


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.upstream = self.root / "upstream"
        self.upstream.mkdir()
        git(self.upstream, "init", "--initial-branch=f45")
        git(self.upstream, "config", "user.name", "Test")
        git(self.upstream, "config", "user.email", "test@example.invalid")
        for name, data in {"freetype.spec": FEDORA_SPEC, "sources": "manifest\n",
                           "ftconfig.h": "config\n", "freetype-2.10.0-internal-outline.patch": "patch\n",
                           "freetype-2.3.0-enable-spr.patch": "ClearType\n"}.items():
            (self.upstream / name).write_text(data)
        self.commit()
        self.repo = self.root / "repo"
        self.repo.mkdir()
        (self.repo / "qdoled-release.json").write_text(json.dumps({"release": 2, "date": "2026-10-19"}))
        (self.repo / ".fedora-files").write_text("obsolete.patch\n")
        (self.repo / "obsolete.patch").write_text("old patch")
        (self.repo / sync.PATCH).write_text("custom geometry")
        (self.repo / "README.md").write_text("local docs")
        (self.repo / ".github").mkdir()
        (self.repo / ".github" / "workflow").write_text("workflow")

    def commit(self):
        git(self.upstream, "add", "-A")
        git(self.upstream, "commit", "-m", "Update")

    def run_sync(self):
        sync.sync(self.repo, self.upstream.as_uri(), "f45")

    def snapshot(self):
        return {str(p.relative_to(self.repo)): (p.read_bytes(), p.stat().st_mtime_ns)
                for p in self.repo.rglob("*") if p.is_file()}

    def test_repeated_polls_and_unrelated_upstream_commits_are_noops(self):
        self.run_sync()
        first = self.snapshot()
        self.run_sync()
        self.assertEqual(first, self.snapshot())
        with patch.object(sync, "datetime") as clock:
            clock.strptime.side_effect = datetime.strptime
            clock.now.return_value = datetime(2030, 1, 1)
            clock.today.return_value = datetime(2030, 1, 1)
            clock.utcnow.return_value = datetime(2030, 1, 1)
            self.run_sync()
        self.assertEqual(first, self.snapshot())
        (self.upstream / "README.md").write_text("Fedora-only documentation")
        self.commit()
        self.run_sync()
        self.assertEqual(first, self.snapshot())
        self.assertFalse((self.repo / "obsolete.patch").exists())
        self.assertFalse((self.repo / "freetype-2.3.0-enable-spr.patch").exists())
        self.assertEqual((self.repo / sync.PATCH).read_text(), "custom geometry")
        self.assertEqual((self.repo / "README.md").read_text(), "local docs")
        self.assertEqual((self.repo / ".github" / "workflow").read_text(), "workflow")

    def test_real_upstream_release_updates_once(self):
        self.run_sync()
        spec = FEDORA_SPEC.replace("Release: 2%", "Release: 3%")
        (self.upstream / "freetype.spec").write_text(spec)
        self.commit()
        self.run_sync()
        generated = (self.repo / "freetype.spec").read_text()
        self.assertIn("Release: 3.qdoled.2%{?dist}", generated)
        self.assertEqual(generated.count("Patch100:"), 1)
        self.assertEqual(generated.count("%patch 100"), 1)
        self.assertNotIn("%patch 0 ", generated)
        self.assertNotIn("http://download", generated)
        current = self.snapshot()
        self.run_sync()
        self.assertEqual(current, self.snapshot())

    def test_patch_and_source_updates_are_not_missed(self):
        self.run_sync()
        (self.upstream / "sources").write_text("updated manifest\n")
        (self.upstream / "freetype-2.10.0-internal-outline.patch").write_text("updated patch\n")
        self.commit()
        self.run_sync()
        self.assertEqual((self.repo / "sources").read_text(), "updated manifest\n")
        self.assertEqual((self.repo / "freetype-2.10.0-internal-outline.patch").read_text(), "updated patch\n")

    def test_changed_spec_layout_fails_before_any_writes(self):
        before = self.snapshot()
        (self.upstream / "freetype.spec").write_text(FEDORA_SPEC.replace("%patch 0 ", "%patch -P 0 "))
        self.commit()
        with self.assertRaisesRegex(ValueError, "Fedora spec changed"):
            self.run_sync()
        self.assertEqual(before, self.snapshot())

    def test_local_revision_bumps_release_and_date(self):
        text = sync.transform_spec(FEDORA_SPEC, {"release": 3, "date": "2026-10-20"})
        self.assertIn("2.14.3-2.qdoled.3", text)
        self.assertIn("* Tue Oct 20 2026", text)


class SourceTests(unittest.TestCase):
    def test_corrupt_source_never_reaches_rpmbuild(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            spec = repo / "freetype.spec"
            spec.write_text("unused")
            (repo / "source.tar.xz").write_bytes(b"corrupt archive")
            (repo / "sources").write_text(f"SHA512 (source.tar.xz) = {hashlib.sha512(b'expected').hexdigest()}\n")
            with patch.object(srpm.subprocess, "check_output", return_value="Source0: https://example.invalid/source.tar.xz\n"), \
                 patch.object(srpm.subprocess, "run") as build, patch.object(srpm, "urlopen") as download:
                with self.assertRaisesRegex(ValueError, "SHA512 mismatch"):
                    srpm.build(spec, repo / "out", None)
                build.assert_not_called()
                download.assert_not_called()

    def test_manifest_must_cover_every_download(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "sources").write_text(f"SHA512 (other.tar.xz) = {'0' * 128}\n")
            with patch.object(srpm.subprocess, "check_output", return_value="Source: https://example.invalid/source.tar.xz\n"), \
                 patch.object(srpm.subprocess, "run") as build:
                with self.assertRaisesRegex(ValueError, "do not match"):
                    srpm.build(repo / "freetype.spec", repo / "out", None)
                build.assert_not_called()

    def test_manifest_rejects_ambiguous_or_unsafe_entries(self):
        for text in ["", "SHA256 (archive) = 123", f"SHA512 (../archive) = {'0' * 128}",
                     f"SHA512 (archive) = {'0' * 128}\n" * 2]:
            with self.subTest(text=text), self.assertRaises(ValueError):
                srpm.manifest_checksums(text)


class SrpmBootstrapTests(unittest.TestCase):
    def test_minimal_copr_root_installs_python_before_running_helper(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            (repo / ".copr").mkdir(parents=True)
            (repo / "scripts").mkdir()
            shutil.copyfile(ROOT / ".copr/Makefile", repo / ".copr/Makefile")
            (repo / "scripts/build-srpm.py").write_text(
                '#!/bin/sh\nprintf "%s\\n" "$@" >> "$BUILD_LOG"\n')
            stub_bin = root / "bin"
            stub_bin.mkdir()
            python_stub = root / "python-stub"
            python_stub.write_text('#!/bin/sh\nexec /bin/sh "$@"\n')
            python_stub.chmod(0o755)
            dnf = stub_bin / "dnf"
            dnf.write_text('#!/bin/sh\n'
                           'printf "%s\\n" "$*" >> "$INSTALL_LOG"\n'
                           'if [ "${INSTALL_FAIL:-0}" = 1 ]; then exit 1; fi\n'
                           '/usr/bin/cp "$PYTHON_STUB" "$STUB_BIN/python3"\n')
            dnf.chmod(0o755)
            env = dict(os.environ, PATH=str(stub_bin), PYTHON_STUB=str(python_stub),
                       STUB_BIN=str(stub_bin), INSTALL_LOG=str(root / "install.log"),
                       BUILD_LOG=str(root / "build.log"))
            command = [shutil.which("make"), "-f", str(repo / ".copr/Makefile"),
                       "srpm", f"spec={repo}/freetype.spec", f"outdir={root}/out"]
            # PATH intentionally contains no Python, matching the supplied COPR log.
            subprocess.run(command, env=env, check=True, capture_output=True)
            self.assertEqual((root / "install.log").read_text(), "-y install python3\n")
            self.assertIn(str(repo / "freetype.spec"), (root / "build.log").read_text())
            subprocess.run(command, env=env, check=True, capture_output=True)
            self.assertEqual((root / "install.log").read_text(), "-y install python3\n")
            (stub_bin / "python3").unlink()
            (root / "build.log").unlink()
            result = subprocess.run(command, env=dict(env, INSTALL_FAIL="1"), capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((root / "build.log").exists())


class PublishTests(unittest.TestCase):
    def test_only_changed_committed_build_inputs_produce_a_push(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            git(repo, "init", "--initial-branch=main")
            git(repo, "config", "user.name", "Test")
            git(repo, "config", "user.email", "test@example.invalid")
            remote = Path(tmp) / "remote.git"
            git(repo, "init", "--bare", str(remote))
            git(repo, "remote", "add", "origin", str(remote))
            for name in [".fedora-files", "freetype.spec", sync.PATCH, ".copr/Makefile", "scripts/build-srpm.py"]:
                path = repo / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("freetype.spec\n" if name == ".fedora-files" else "input\n")
            git(repo, "add", "-A")
            git(repo, "commit", "-m", "Initial inputs")
            self.assertTrue(publisher.publish(repo))
            first = git(remote, "rev-parse", "copr-build")
            self.assertFalse(publisher.publish(repo))
            (repo / "README.md").write_text("new documentation")
            git(repo, "add", "README.md")
            git(repo, "commit", "-m", "Documentation only")
            self.assertFalse(publisher.publish(repo))
            self.assertEqual(first, git(remote, "rev-parse", "copr-build"))
            # Uncommitted changes are not published; the developer's index stays intact.
            (repo / sync.PATCH).write_text("changed geometry")
            git(repo, "add", sync.PATCH)
            staged = git(repo, "write-tree")
            self.assertFalse(publisher.publish(repo))
            self.assertEqual(staged, git(repo, "write-tree"))
            git(repo, "commit", "-m", "Change geometry")
            self.assertTrue(publisher.publish(repo))
            second = git(remote, "rev-parse", "copr-build")
            self.assertNotEqual(first, second)
            self.assertEqual(first, git(remote, "rev-parse", "copr-build^"))
            self.assertNotIn(b"README.md", git(remote, "ls-tree", "--name-only", "copr-build"))


if __name__ == "__main__":
    unittest.main()
