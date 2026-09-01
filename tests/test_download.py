"""Tests for magemin._download -- offline only, no real network access.

See tests/test_download_live.py for real end-to-end download+build tests
against the live GitHub repo (not part of the default pytest collection).
"""

import io
import json
import platform
import subprocess
import tarfile
import urllib.error
from pathlib import Path

import pytest

from magemin import _download
from magemin.errors import MAGEMinDownloadError

# --- resolve_ref -------------------------------------------------------


def test_resolve_ref_none_looks_up_latest_release(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_download, "_latest_release_ref", lambda: "v2.1.0")
    assert _download.resolve_ref(None) == "v2.1.0"


def test_resolve_ref_latest_is_main() -> None:
    assert _download.resolve_ref("latest") == "main"


def test_resolve_ref_semver_gets_v_prefix() -> None:
    assert _download.resolve_ref("2.0.0") == "v2.0.0"


def test_resolve_ref_passthrough_for_non_semver() -> None:
    assert _download.resolve_ref("main") == "main"
    assert _download.resolve_ref("abc1234") == "abc1234"
    assert _download.resolve_ref("some-branch") == "some-branch"


# --- _safe_dirname -------------------------------------------------------


def test_safe_dirname_sanitizes_slashes() -> None:
    assert _download._safe_dirname("feature/foo") == "feature_foo"


def test_safe_dirname_passthrough_for_plain_ref() -> None:
    assert _download._safe_dirname("v2.0.0") == "v2.0.0"
    assert _download._safe_dirname("main") == "main"


# --- default_cache_dir -------------------------------------------------------


def test_default_cache_dir_windows_with_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_download.sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", "C:\\Users\\test\\AppData\\Local")
    assert _download.default_cache_dir() == Path("C:\\Users\\test\\AppData\\Local") / "magemin"


def test_default_cache_dir_windows_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_download.sys, "platform", "win32")
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    result = _download.default_cache_dir()
    assert result == Path.home() / "AppData" / "Local" / "magemin"


def test_default_cache_dir_darwin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_download.sys, "platform", "darwin")
    result = _download.default_cache_dir()
    assert result == Path.home() / "Library" / "Caches" / "magemin"


def test_default_cache_dir_linux_with_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_download.sys, "platform", "linux")
    monkeypatch.setenv("XDG_CACHE_HOME", "/custom/cache")
    assert _download.default_cache_dir() == Path("/custom/cache") / "magemin"


def test_default_cache_dir_linux_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_download.sys, "platform", "linux")
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    assert _download.default_cache_dir() == Path.home() / ".cache" / "magemin"


# --- download ------------------------------------------------------------


def _make_fixture_tarball(dest: Path) -> None:
    """Build a small synthetic archive mimicking GitHub's layout."""
    with tarfile.open(dest, "w:gz") as tf:
        makefile = b"lib:\n\techo fake\n"
        src_c = b"int main(void) { return 0; }\n"
        entries = (
            ("FakeRepo-main/Makefile", makefile),
            ("FakeRepo-main/src/foo.c", src_c),
        )
        for name, content in entries:
            info = tarfile.TarInfo(name=name)
            info.size = len(content)
            tf.addfile(info, io.BytesIO(content))


def test_download_extracts_and_strips_top_level_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def fake_fetch(url: str, dest_file: Path, **kwargs: object) -> None:
        _make_fixture_tarball(dest_file)

    monkeypatch.setattr(_download, "_fetch", fake_fetch)
    monkeypatch.setattr(_download, "default_cache_dir", lambda: tmp_path / "cache")

    dest = tmp_path / "out"
    result = _download.download(version="main", dest=dest)

    assert result == dest
    assert (dest / "Makefile").exists()
    assert (dest / "src" / "foo.c").exists()
    # explicit dest -> marker must NOT be written
    assert not (tmp_path / "cache" / "current.txt").exists()


def test_download_default_dest_writes_marker(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def fake_fetch(url: str, dest_file: Path, **kwargs: object) -> None:
        _make_fixture_tarball(dest_file)

    monkeypatch.setattr(_download, "_fetch", fake_fetch)
    cache_dir = tmp_path / "cache"
    monkeypatch.setattr(_download, "default_cache_dir", lambda: cache_dir)

    result = _download.download(version="main")

    marker = cache_dir / "current.txt"
    assert marker.exists()
    assert marker.read_text().strip() == str(result.resolve())


def test_download_cache_hit_skips_refetch(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    dest = tmp_path / "out"
    dest.mkdir()
    (dest / "Makefile").write_text("lib:\n")

    def fail_fetch(url: str, dest_file: Path, **kwargs: object) -> None:
        pytest.fail("fetch should not be called on a cache hit")

    monkeypatch.setattr(_download, "_fetch", fail_fetch)

    result = _download.download(version="main", dest=dest)
    assert result == dest


def test_download_force_refetches(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    dest = tmp_path / "out"
    dest.mkdir()
    (dest / "stale.txt").write_text("old")

    called = []

    def fake_fetch(url: str, dest_file: Path, **kwargs: object) -> None:
        called.append(url)
        _make_fixture_tarball(dest_file)

    monkeypatch.setattr(_download, "_fetch", fake_fetch)

    result = _download.download(version="main", dest=dest, force=True)
    assert called
    assert result == dest
    assert not (dest / "stale.txt").exists()
    assert (dest / "Makefile").exists()


def test_download_404_raises_with_ref_named(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def fake_fetch(url: str, dest_file: Path, **kwargs: object) -> None:
        raise MAGEMinDownloadError(f"failed to download {url}: HTTP Error 404: Not Found")

    monkeypatch.setattr(_download, "_fetch", fake_fetch)

    with pytest.raises(MAGEMinDownloadError, match="does-not-exist"):
        _download.download(version="does-not-exist", dest=tmp_path / "out")


def test_fetch_wraps_http_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def raise_http_error(url, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)

    monkeypatch.setattr(_download.urllib.request, "urlretrieve", raise_http_error)

    with pytest.raises(MAGEMinDownloadError, match="HTTP Error 404"):
        _download._fetch("http://example.invalid/x.tar.gz", tmp_path / "x.tar.gz")


# --- _latest_release_ref -------------------------------------------------------


class _FakeApiResponse:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def __enter__(self) -> _FakeApiResponse:
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None

    def read(self) -> bytes:
        return self._payload


def test_latest_release_ref_parses_tag_name(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = json.dumps({"tag_name": "v2.1.0"}).encode()

    def fake_urlopen(request, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        return _FakeApiResponse(payload)

    monkeypatch.setattr(_download.urllib.request, "urlopen", fake_urlopen)
    assert _download._latest_release_ref() == "v2.1.0"


def test_latest_release_ref_wraps_404_with_no_releases_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_404(request, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        raise urllib.error.HTTPError("url", 404, "Not Found", {}, None)

    monkeypatch.setattr(_download.urllib.request, "urlopen", raise_404)

    with pytest.raises(MAGEMinDownloadError, match="no published releases"):
        _download._latest_release_ref()


def test_latest_release_ref_wraps_other_http_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_403(request, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        raise urllib.error.HTTPError("url", 403, "Forbidden", {}, None)

    monkeypatch.setattr(_download.urllib.request, "urlopen", raise_403)

    with pytest.raises(MAGEMinDownloadError, match="failed to look up the latest release"):
        _download._latest_release_ref()


# --- build -----------------------------------------------------------------


class _Recorder:
    def __init__(self) -> None:
        self.calls: list[tuple[list[str], Path]] = []

    def __call__(self, cmd: list[str], *, cwd: Path, **kwargs: object) -> None:
        self.calls.append((cmd, cwd))


@pytest.mark.parametrize(
    ("system", "expected_inc", "expected_libs", "expected_ext"),
    [
        ("Linux", "", "-lm -llapacke -lnlopt -L/usr/lib", "so"),
        (
            "Darwin",
            "-I/opt/homebrew/include",
            "-lm -framework Accelerate /opt/homebrew/lib/libnlopt.dylib",
            "dylib",
        ),
        ("Windows", "", "-lm -llapacke -lnlopt", "dll"),
    ],
)
def test_build_command_sequence_and_platform_defaults(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    system: str,
    expected_inc: str,
    expected_libs: str,
    expected_ext: str,
) -> None:
    recorder = _Recorder()
    monkeypatch.setattr(_download, "_run", recorder)
    monkeypatch.setattr(platform, "system", lambda: system)
    monkeypatch.delenv("CC", raising=False)

    src_dir = tmp_path / "MAGEMin"
    (src_dir / "src").mkdir(parents=True)

    out = _download.build(src_dir)

    assert out == src_dir / f"libMAGEMin.{expected_ext}"
    assert len(recorder.calls) == 4
    clean_cmd, _ = recorder.calls[0]
    assert clean_cmd == ["make", "clean"]
    lib_cmd, _ = recorder.calls[1]
    assert lib_cmd == [
        "make",
        "lib",
        "USE_MPI=0",
        "CC=gcc",
        f"INC={expected_inc}",
        f"LIBS={expected_libs}",
    ]
    compile_cmd, _ = recorder.calls[2]
    assert compile_cmd[0] == "gcc"
    assert "-c" in compile_cmd
    link_cmd, _ = recorder.calls[3]
    assert link_cmd[0] == "gcc"
    assert "-shared" in link_cmd
    assert str(out) in link_cmd


def test_build_respects_explicit_cc_inc_libs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    recorder = _Recorder()
    monkeypatch.setattr(_download, "_run", recorder)

    src_dir = tmp_path / "MAGEMin"
    (src_dir / "src").mkdir(parents=True)

    _download.build(src_dir, cc="clang", inc="-I/custom", libs="-lcustom")

    lib_cmd, _ = recorder.calls[1]
    assert lib_cmd == ["make", "lib", "USE_MPI=0", "CC=clang", "INC=-I/custom", "LIBS=-lcustom"]


def test_run_missing_executable_raises_download_error(tmp_path: Path) -> None:
    with pytest.raises(MAGEMinDownloadError, match="not found on PATH"):
        _download._run(["definitely-not-a-real-command-xyz"], cwd=tmp_path)


def test_run_nonzero_exit_includes_captured_output(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def fake_run(cmd, cwd, capture_output, text):  # noqa: ANN001
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="compile error XYZ")

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(MAGEMinDownloadError, match="compile error XYZ"):
        _download._run(["cc", "-c", "foo.c"], cwd=tmp_path)


# --- main (CLI) -------------------------------------------------------


def test_build_only_without_dest_or_version_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """--build-only must never touch the network, even indirectly via version=None."""

    def fail_if_called(*args, **kwargs):  # noqa: ANN002, ANN003
        pytest.fail("must not be called: --build-only should never touch the network")

    monkeypatch.setattr(_download, "_fetch", fail_if_called)
    monkeypatch.setattr(_download, "_latest_release_ref", fail_if_called)
    monkeypatch.setattr(_download, "build", fail_if_called)

    exit_code = _download.main(["--build-only"])
    assert exit_code == 1
