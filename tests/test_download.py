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
    assert _download.resolve_ref("2.0.8") == "v2.0.8"
    assert _download.resolve_ref("2.1.0") == "v2.1.0"


def test_resolve_ref_rejects_versions_below_minimum() -> None:
    with pytest.raises(MAGEMinDownloadError, match=">= 2.0.8"):
        _download.resolve_ref("2.0.7")


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


def test_fetch_retries_transient_errors(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls = []

    def flaky(url, dest_file, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        calls.append(url)
        if len(calls) == 1:
            raise urllib.error.HTTPError(url, 504, "Gateway Time-out", {}, None)
        if len(calls) == 2:
            raise urllib.error.URLError("connection reset")
        Path(dest_file).write_bytes(b"ok")

    monkeypatch.setattr(_download.urllib.request, "urlretrieve", flaky)
    monkeypatch.setattr(_download.time, "sleep", lambda seconds: None)

    _download._fetch("http://example.invalid/x.tar.gz", tmp_path / "x.tar.gz")
    assert len(calls) == 3
    assert (tmp_path / "x.tar.gz").read_bytes() == b"ok"


def test_fetch_gives_up_after_persistent_5xx(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls = []

    def always_504(url, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        calls.append(url)
        raise urllib.error.HTTPError(url, 504, "Gateway Time-out", {}, None)

    monkeypatch.setattr(_download.urllib.request, "urlretrieve", always_504)
    monkeypatch.setattr(_download.time, "sleep", lambda seconds: None)

    with pytest.raises(MAGEMinDownloadError, match="HTTP Error 504"):
        _download._fetch("http://example.invalid/x.tar.gz", tmp_path / "x.tar.gz")
    assert len(calls) == _download._FETCH_ATTEMPTS


def test_fetch_does_not_retry_client_errors(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls = []

    def not_found(url, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        calls.append(url)
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)

    monkeypatch.setattr(_download.urllib.request, "urlretrieve", not_found)

    with pytest.raises(MAGEMinDownloadError, match="HTTP Error 404"):
        _download._fetch("http://example.invalid/x.tar.gz", tmp_path / "x.tar.gz")
    assert len(calls) == 1


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
    """Stands in for `_run`; `make lib` leaves libMAGEMin.dylib behind, like the real Makefile."""

    def __init__(self) -> None:
        self.calls: list[tuple[list[str], Path]] = []

    def __call__(self, cmd: list[str], *, cwd: Path, **kwargs: object) -> None:
        self.calls.append((cmd, cwd))
        if cmd[:2] == ["make", "lib"]:
            (cwd / "libMAGEMin.dylib").write_bytes(b"lib")


def _fake_src_dir(tmp_path: Path, version: str = "2.0.8") -> Path:
    """A MAGEMin source tree stub whose src/initialize.c declares `version`."""
    src_dir = tmp_path / "MAGEMin"
    (src_dir / "src").mkdir(parents=True)
    (src_dir / "src" / "initialize.c").write_text(
        f'\tstrcpy(gv.version,"{version} [07/10/2026]");\n'
    )
    return src_dir


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

    src_dir = _fake_src_dir(tmp_path)

    out = _download.build(src_dir)

    assert out == src_dir / f"libMAGEMin.{expected_ext}"
    assert out.exists()
    assert len(recorder.calls) == 2
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


def test_build_respects_explicit_cc_inc_libs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    recorder = _Recorder()
    monkeypatch.setattr(_download, "_run", recorder)

    src_dir = _fake_src_dir(tmp_path)

    _download.build(src_dir, cc="clang", inc="-I/custom", libs="-lcustom")

    lib_cmd, _ = recorder.calls[1]
    assert lib_cmd == ["make", "lib", "USE_MPI=0", "CC=clang", "INC=-I/custom", "LIBS=-lcustom"]


def test_build_rejects_source_tree_below_minimum(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    recorder = _Recorder()
    monkeypatch.setattr(_download, "_run", recorder)
    src_dir = _fake_src_dir(tmp_path, version="2.0.7")

    with pytest.raises(MAGEMinDownloadError, match="MAGEMin 2.0.7 is not supported"):
        _download.build(src_dir)
    assert recorder.calls == []


def test_build_warns_but_proceeds_when_version_unknown(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    recorder = _Recorder()
    monkeypatch.setattr(_download, "_run", recorder)
    src_dir = tmp_path / "MAGEMin"
    (src_dir / "src").mkdir(parents=True)

    with pytest.warns(UserWarning, match="Could not determine the MAGEMin version"):
        _download.build(src_dir)
    assert len(recorder.calls) == 2


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


# --- prebuilt binaries (MAGEMin_jll) --------------------------------------

_LINUX_HOST = {
    "arch": "x86_64",
    "os": "linux",
    "libc": "glibc",
    "libgfortran_version": "5.0.0",
    "cxxstring_abi": "cxx11",
}


def _entry(name: str, **platform_keys: str) -> dict:
    return {"git-tree-sha1": "0" * 40, "download": [{"url": name, "sha256": ""}], **platform_keys}


def test_select_artifact_matches_libc_and_libgfortran() -> None:
    entries = [
        _entry("gf3", arch="x86_64", os="linux", libc="glibc", libgfortran_version="3.0.0"),
        _entry("musl", arch="x86_64", os="linux", libc="musl", libgfortran_version="5.0.0"),
        _entry("mac", arch="x86_64", os="macos", libgfortran_version="5.0.0"),
        _entry("gf5", arch="x86_64", os="linux", libc="glibc", libgfortran_version="5.0.0"),
    ]
    assert _download._select_artifact(entries, _LINUX_HOST)["download"][0]["url"] == "gf5"


def test_select_artifact_ignores_keys_the_entry_omits() -> None:
    """A package without Fortran/C++ (no libgfortran_version/cxxstring_abi) still matches."""
    entries = [_entry("plain", arch="x86_64", os="linux", libc="glibc")]
    assert _download._select_artifact(entries, _LINUX_HOST)["download"][0]["url"] == "plain"


def test_select_artifact_skips_unknown_variants() -> None:
    """Sanitizer/microarchitecture builds carry extra keys and are never picked."""
    entries = [
        _entry("asan", arch="x86_64", os="linux", libc="glibc", sanitize="address"),
        _entry("plain", arch="x86_64", os="linux", libc="glibc"),
    ]
    assert _download._select_artifact(entries, _LINUX_HOST)["download"][0]["url"] == "plain"


def test_select_artifact_no_match_raises() -> None:
    entries = [_entry("mac", arch="aarch64", os="macos")]
    with pytest.raises(MAGEMinDownloadError, match="no prebuilt binary"):
        _download._select_artifact(entries, _LINUX_HOST)


@pytest.mark.parametrize(
    ("system", "machine", "libc", "expected"),
    [
        ("Linux", "x86_64", "glibc", {"arch": "x86_64", "os": "linux", "libc": "glibc"}),
        ("Linux", "aarch64", "", {"arch": "aarch64", "os": "linux", "libc": "musl"}),
        ("Darwin", "arm64", "", {"arch": "aarch64", "os": "macos"}),
        ("Windows", "AMD64", "", {"arch": "x86_64", "os": "windows"}),
    ],
)
def test_host_platform(
    monkeypatch: pytest.MonkeyPatch, system: str, machine: str, libc: str, expected: dict
) -> None:
    monkeypatch.setattr(platform, "system", lambda: system)
    monkeypatch.setattr(platform, "machine", lambda: machine)
    monkeypatch.setattr(platform, "libc_ver", lambda: (libc, ""))
    host = _download._host_platform()
    assert {key: host[key] for key in expected} == expected
    assert ("libc" in host) == (system == "Linux")


def test_host_platform_unsupported_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    monkeypatch.setattr(platform, "machine", lambda: "s390x")
    with pytest.raises(MAGEMinDownloadError, match="--from-source"):
        _download._host_platform()


def test_jll_release_tag_picks_newest_build_across_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    pages = {
        1: [{"tag_name": "NLopt-v2.9.0+0"}, {"tag_name": "NLopt-v2.8.0+0"}],
        2: [{"tag_name": "NLopt-v2.8.0+2"}, {"tag_name": "NLopt-v2.8.01+5"}],
    }
    monkeypatch.setattr(
        _download,
        "_github_api_json",
        lambda url: pages.get(int(url.rsplit("=", 1)[1]), []),
    )
    assert _download._jll_release_tag("NLopt_jll", "2.8.0") == "NLopt-v2.8.0+2"


def test_jll_release_tag_missing_version_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_download, "_github_api_json", lambda url: [])
    with pytest.raises(MAGEMinDownloadError, match="no prebuilt MAGEMin_jll release"):
        _download._jll_release_tag("MAGEMin_jll", "9.9.9")


def test_jll_dependency_ref_follows_exact_pin_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_download, "_jll_release_tag", lambda repo, version: f"{repo}@{version}")
    compat = {"NLopt_jll": "=2.8.0", "JLLWrappers": "1.7.0"}
    assert _download._jll_dependency_ref("NLopt_jll", compat) == "NLopt_jll@2.8.0"
    assert _download._jll_dependency_ref("OpenBLAS32_jll", compat) == "main"


def _jll_tarball(path: Path, files: dict[str, bytes], prefix: str = "lib") -> bytes:
    """A jll-style tarball (`prefix`/..., ``bin`` on Windows) holding `files`; returns its bytes."""
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tf:
        for name, data in files.items():
            info = tarfile.TarInfo(f"{prefix}/{name}")
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    path.write_bytes(buffer.getvalue())
    return buffer.getvalue()


class _FakeJll:
    """Serves fake MAGEMin_jll + dependency metadata and tarballs to install_binary."""

    def __init__(self, tmp_path: Path) -> None:
        import hashlib

        self.tarballs: dict[str, bytes] = {
            "MAGEMin": _jll_tarball(tmp_path / "m.tgz", {"libMAGEMin.so": b"magemin"}),
            "NLopt": _jll_tarball(tmp_path / "n.tgz", {"libnlopt.so.0": b"nlopt"}),
            "OpenBLAS32": _jll_tarball(tmp_path / "o.tgz", {"libopenblas.so": b"blas"}),
            "CompilerSupportLibraries": _jll_tarball(
                tmp_path / "c.tgz",
                {"libgfortran.so.5": b"gf", "libasan.so.8": b"asan"},
            ),
        }
        self.sha = {name: hashlib.sha256(data).hexdigest() for name, data in self.tarballs.items()}
        self.fetched: list[str] = []

    def jll_file(self, repo: str, ref: str, file: str) -> str:
        name = repo.removesuffix("_jll")
        if file == "Project.toml":
            return (
                'name = "MAGEMin_jll"\nversion = "2.0.8+0"\n'
                '[deps]\nNLopt_jll = "x"\nOpenBLAS32_jll = "x"\n'
                'CompilerSupportLibraries_jll = "x"\n'
                '[compat]\nNLopt_jll = "=2.8.0"\n'
            )
        return (
            f'[[{name}]]\narch = "x86_64"\nos = "linux"\nlibc = "glibc"\n'
            f'git-tree-sha1 = "{"0" * 40}"\n'
            f'[[{name}.download]]\nurl = "{name}"\nsha256 = "{self.sha[name]}"\n'
        )

    def fetch(self, url: str, dest_file: Path, *, verbose: bool = False) -> None:
        self.fetched.append(url)
        dest_file.write_bytes(self.tarballs[url])


@pytest.fixture
def fake_jll(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> _FakeJll:
    fake = _FakeJll(tmp_path)
    monkeypatch.setattr(_download, "_jll_file", fake.jll_file)
    monkeypatch.setattr(_download, "_fetch", fake.fetch)
    monkeypatch.setattr(_download, "_jll_release_tag", lambda repo, version: f"{repo}-v{version}")
    monkeypatch.setattr(_download, "_host_platform", lambda: dict(_LINUX_HOST))
    monkeypatch.setattr(_download, "_check_loadable", lambda lib_path, version: None)
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    monkeypatch.setattr(_download, "default_cache_dir", lambda: tmp_path / "cache")
    return fake


def test_install_binary_flattens_runtime_libraries(fake_jll: _FakeJll, tmp_path: Path) -> None:
    lib_path = _download.install_binary(dest=tmp_path / "bin")

    assert lib_path == tmp_path / "bin" / "libMAGEMin.so"
    installed = sorted(p.name for p in (tmp_path / "bin").iterdir())
    assert installed == ["libMAGEMin.so", "libgfortran.so.5", "libnlopt.so.0", "libopenblas.so"]
    assert not (tmp_path / "cache" / "current.txt").exists()  # explicit dest: no marker


def test_install_binary_layout_follows_host_not_interpreter(
    fake_jll: _FakeJll, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # The artifacts' lib/ vs bin/ layout comes from the resolved host platform, not from
    # sys.platform -- a Linux host on a Windows interpreter (as faked here, and as on the
    # Windows CI runner) must still find the lib/ tarballs' libraries.
    monkeypatch.setattr(_download.sys, "platform", "win32")
    _download.install_binary(dest=tmp_path / "bin")
    assert (tmp_path / "bin" / "libMAGEMin.so").exists()


def test_install_artifact_windows_layout_uses_bin(tmp_path: Path) -> None:
    import hashlib

    data = _jll_tarball(tmp_path / "w.tgz", {"libMAGEMin.dll": b"dll"}, prefix="bin")
    download = {"url": "https://example.invalid/w.tgz", "sha256": hashlib.sha256(data).hexdigest()}
    dest = tmp_path / "dest"
    dest.mkdir()

    def fake_fetch(url: str, dest_file: Path, **kwargs: object) -> None:
        dest_file.write_bytes(data)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(_download, "_fetch", fake_fetch)
        _download._install_artifact(download, dest, {"os": "windows"}, main=True, verbose=False)
    assert [p.name for p in dest.iterdir()] == ["libMAGEMin.dll"]


def test_install_binary_default_dest_writes_marker(fake_jll: _FakeJll, tmp_path: Path) -> None:
    lib_path = _download.install_binary()

    assert lib_path == tmp_path / "cache" / "MAGEMin-2.0.8-bin" / "libMAGEMin.so"
    marker = (tmp_path / "cache" / "current.txt").read_text().strip()
    assert Path(marker) == lib_path.parent


def test_install_binary_cache_hit_skips_download(fake_jll: _FakeJll, tmp_path: Path) -> None:
    _download.install_binary(dest=tmp_path / "bin")
    fake_jll.fetched.clear()

    _download.install_binary(dest=tmp_path / "bin")
    assert fake_jll.fetched == []


def test_install_binary_checksum_mismatch_raises(fake_jll: _FakeJll, tmp_path: Path) -> None:
    fake_jll.sha["MAGEMin"] = "f" * 64
    with pytest.raises(MAGEMinDownloadError, match="checksum mismatch"):
        _download.install_binary(dest=tmp_path / "bin")


def test_install_binary_rejects_newest_release_below_minimum(
    fake_jll: _FakeJll, monkeypatch: pytest.MonkeyPatch
) -> None:
    def old_jll_file(repo: str, ref: str, file: str) -> str:
        return fake_jll.jll_file(repo, ref, file).replace('"2.0.8+0"', '"2.0.7+0"')

    monkeypatch.setattr(_download, "_jll_file", old_jll_file)
    with pytest.raises(MAGEMinDownloadError, match="newest release"):
        _download.install_binary()
    assert fake_jll.fetched == []


def test_install_binary_rejects_non_release_versions(fake_jll: _FakeJll) -> None:
    with pytest.raises(MAGEMinDownloadError, match="--from-source"):
        _download.install_binary("main")


@pytest.mark.parametrize(
    ("version", "from_source", "expected"),
    [
        (None, False, "binary"),
        ("2.0.8", False, "binary"),
        ("2.0.8", True, "source"),
        ("latest", False, "source"),
        ("some-branch", False, "source"),
    ],
)
def test_install_dispatches_binary_or_source(
    monkeypatch: pytest.MonkeyPatch, version: str | None, from_source: bool, expected: str
) -> None:
    monkeypatch.setattr(_download, "install_binary", lambda *a, **k: Path("binary"))
    monkeypatch.setattr(_download, "download", lambda *a, **k: Path("src"))
    monkeypatch.setattr(_download, "build", lambda *a, **k: Path("source"))

    assert _download.install(version, from_source=from_source) == Path(expected)
