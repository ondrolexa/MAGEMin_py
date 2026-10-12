"""Install the MAGEMin C library: prebuilt binaries, or a source build.

Private module: public functions (`install`, `default_cache_dir`) are re-exported at the
top-level ``magemin`` package. By default `install` fetches the official prebuilt
``MAGEMin_jll`` binaries (built by Julia's Yggdrasil for every major platform) plus the
runtime libraries they link against, so no compiler is needed. Building from a source
tree (`download` + `build`) remains available for unreleased refs. Stdlib-only
(``urllib.request``, ``tarfile``, ``tomllib``, ``subprocess``, ``platform``).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import tomllib
import urllib.error
import urllib.request
import warnings
from pathlib import Path

from magemin.errors import MAGEMinDownloadError, MAGEMinError

_GITHUB_OWNER = "ComputationalThermodynamics"
_GITHUB_REPO = "MAGEMin"
_ARCHIVE_URL = "https://github.com/{owner}/{repo}/archive/{ref}.tar.gz"
_RELEASES_LATEST_URL = "https://api.github.com/repos/{owner}/{repo}/releases/latest"

_SEMVER_RE = re.compile(r"\d+\.\d+\.\d+")
# First release with the solver/buffer/phase-suppression C API (`_lib._REQUIRED_API`).
MIN_MAGEMIN_VERSION = (2, 0, 8)
# Floor for a source tree's own `gv.version`. Kept separate from MIN_MAGEMIN_VERSION because
# `main` can lag behind (between releases it may still report the previous one). Whether a
# built tree actually has the C API is checked by symbol when the library is loaded
# (`_lib._load`).
# Keep in sync with min_version in scripts/build_lib.sh.
_MIN_SOURCE_VERSION = (2, 0, 8)
_SOURCE_VERSION_RE = re.compile(r'strcpy\(\s*gv\.version\s*,\s*"(\d+)\.(\d+)\.(\d+)')
_UNSAFE_DIRNAME_CHARS_RE = re.compile(r"[^A-Za-z0-9._-]")
# `_fetch` retries transient download failures, waiting _FETCH_RETRY_DELAY * attempt seconds.
_FETCH_ATTEMPTS = 4
_FETCH_RETRY_DELAY = 5.0

# Source-build platform defaults (best-effort Windows/MSYS2 row -- see build()'s docstring).
_INC_DEFAULTS = {
    "Linux": "",
    "Darwin": "-I/opt/homebrew/include",
    "Windows": "",
}
_LIBS_DEFAULTS = {
    "Linux": "-lm -llapacke -lnlopt -L/usr/lib",
    "Darwin": "-lm -framework Accelerate /opt/homebrew/lib/libnlopt.dylib",
    "Windows": "-lm -llapacke -lnlopt",
}
_LIB_EXT_BY_SYSTEM = {
    "Linux": "so",
    "Darwin": "dylib",
    "Windows": "dll",
}

# Prebuilt binaries: MAGEMin_jll and the jll packages its library links against. Every
# library is installed into one flat directory, where each binary finds its dependencies
# by itself (RUNPATH $ORIGIN on Linux, @loader_path on macOS, the DLL's own directory on
# Windows), so loading libMAGEMin needs no preloading.
_JLL_OWNER = "JuliaBinaryWrappers"
_JLL_RAW_URL = "https://raw.githubusercontent.com/{owner}/{repo}.jl/{ref}/{file}"
_JLL_RELEASES_URL = (
    "https://api.github.com/repos/{owner}/{repo}.jl/releases?per_page=100&page={page}"
)
_MAGEMIN_JLL = "MAGEMin_jll"
_JLL_DEPENDENCIES = ("CompilerSupportLibraries_jll", "OpenBLAS32_jll", "NLopt_jll")
# Runtime libraries libMAGEMin needs from those packages (file-name prefixes); everything
# else they ship (sanitizer runtimes, headers, ...) is left out.
_RUNTIME_LIBRARY_PREFIXES = (
    "libnlopt",
    "libopenblas",
    "libgfortran",
    "libquadmath",
    "libgcc_s",
    "libstdc++",
    "libwinpthread",
)
_ARCH_ALIASES = {
    "x86_64": "x86_64",
    "amd64": "x86_64",
    "aarch64": "aarch64",
    "arm64": "aarch64",
    "i686": "i686",
    "i386": "i686",
    "x86": "i686",
    "armv7l": "armv7l",
    "armv6l": "armv6l",
    "ppc64le": "powerpc64le",
}
_JLL_OS = {"Linux": "linux", "Darwin": "macos", "Windows": "windows", "FreeBSD": "freebsd"}
# Platform keys an Artifacts.toml entry may carry that are matched (or are bookkeeping).
_PLATFORM_KEYS = {"arch", "os", "libc", "libgfortran_version", "cxxstring_abi", "call_abi"}
_ENTRY_KEYS = _PLATFORM_KEYS | {"git-tree-sha1", "download", "lazy"}


def resolve_ref(version: str | None) -> str:
    """Resolve a user-facing version string to a git ref for the archive URL.

    Args:
        version: `None` (the default) looks up and returns the latest
            published GitHub release's tag (a network call -- see
            `_latest_release_ref`). `"latest"` resolves to the `main` branch
            (the bleeding-edge tip, not necessarily a tagged release). A bare
            `X.Y.Z` string is normalized to the release tag `vX.Y.Z`. Any
            other string (a branch name, tag, or commit SHA) is used as-is.

    Returns:
        The git ref to substitute into GitHub's `/archive/{ref}.tar.gz` URL.

    Raises:
        MAGEMinDownloadError: `version` is `None` and the latest-release
            lookup fails (see `_latest_release_ref`), or `version` is an
            `X.Y.Z` release older than `MIN_MAGEMIN_VERSION`.
    """
    if version is None:
        return _latest_release_ref()
    if version == "latest":
        return "main"
    if _SEMVER_RE.fullmatch(version):
        _check_min_version(tuple(int(part) for part in version.split(".")), version)
        return f"v{version}"
    return version


def _check_min_version(
    found: tuple[int, ...], label: str, minimum: tuple[int, ...] = MIN_MAGEMIN_VERSION
) -> None:
    """Raise `MAGEMinDownloadError` if `found` is older than `minimum`."""
    if found < minimum:
        required = ".".join(str(part) for part in minimum)
        raise MAGEMinDownloadError(
            f"MAGEMin {label} is not supported: this package requires MAGEMin >= {required}. "
            "Install the newest release instead: magemin-install"
        )


def _check_source_version(src_dir: Path) -> None:
    """Check the version string in a MAGEMin source tree's `src/initialize.c`.

    Warns (rather than failing) if the version can't be determined, so unusual
    branches/forks still build.

    Raises:
        MAGEMinDownloadError: The tree's version is older than `_MIN_SOURCE_VERSION`.
    """
    init_c = src_dir / "src" / "initialize.c"
    try:
        match = _SOURCE_VERSION_RE.search(init_c.read_text(errors="replace"))
    except OSError:
        match = None
    if match is None:
        warnings.warn(
            f"Could not determine the MAGEMin version from {init_c}; "
            "building anyway, but versions older than "
            f"{'.'.join(str(part) for part in _MIN_SOURCE_VERSION)} are unsupported.",
            stacklevel=3,
        )
        return
    found = tuple(int(part) for part in match.groups())
    _check_min_version(found, ".".join(match.groups()), _MIN_SOURCE_VERSION)


def _latest_release_ref() -> str:
    """Query GitHub for MAGEMin's latest published release tag. Network seam, mockable.

    Raises:
        MAGEMinDownloadError: The API request fails, or the repo has no
            published releases.
    """
    url = _RELEASES_LATEST_URL.format(owner=_GITHUB_OWNER, repo=_GITHUB_REPO)
    request = urllib.request.Request(url, headers={"User-Agent": "magemin-install"})
    try:
        with urllib.request.urlopen(request) as response:
            data = json.load(response)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise MAGEMinDownloadError(
                f"no published releases found for {_GITHUB_OWNER}/{_GITHUB_REPO} -- "
                'pass version="latest" (or the "latest" positional argument) to use the '
                "main branch instead"
            ) from exc
        raise MAGEMinDownloadError(f"failed to look up the latest release: {exc}") from exc
    except urllib.error.URLError as exc:
        raise MAGEMinDownloadError(f"failed to look up the latest release: {exc}") from exc
    return data["tag_name"]


def _safe_dirname(ref: str) -> str:
    """Sanitize a git ref for use as a filesystem directory-name component.

    Replaces any character outside `[A-Za-z0-9._-]` with `_` -- covers branch
    names containing `/` (e.g. `"feature/foo"` -> `"feature_foo"`) and any
    character invalid in a Windows path component.
    """
    return _UNSAFE_DIRNAME_CHARS_RE.sub("_", ref)


def default_cache_dir() -> Path:
    """Return this platform's conventional per-user cache directory for magemin.

    A pure query: does not create the directory. Callers that need it to
    exist create it themselves (`.mkdir(parents=True, exist_ok=True)`).

    Returns:
        `%LOCALAPPDATA%/magemin` on Windows (falling back to
        `~/AppData/Local/magemin` if unset); `~/Library/Caches/magemin` on
        macOS; `$XDG_CACHE_HOME/magemin` (falling back to `~/.cache/magemin`)
        elsewhere.
    """
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        base = str(Path.home() / "Library" / "Caches")
    else:
        base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "magemin"


def _log(message: str, *, verbose: bool) -> None:
    """Print a progress message to stderr, if `verbose`."""
    if verbose:
        print(message, file=sys.stderr, flush=True)


def _download_progress_hook(block_num: int, block_size: int, total_size: int) -> None:
    """`urlretrieve` reporthook: prints a single self-overwriting progress line."""
    downloaded = block_num * block_size
    if total_size > 0:
        pct = min(100, downloaded * 100 // total_size)
        mb = downloaded / 1_048_576
        total_mb = total_size / 1_048_576
        print(f"\r  {pct:3d}%  ({mb:.1f} / {total_mb:.1f} MB)", end="", file=sys.stderr, flush=True)
    else:
        mb = downloaded / 1_048_576
        print(f"\r  {mb:.1f} MB", end="", file=sys.stderr, flush=True)


def _fetch(url: str, dest_file: Path, *, verbose: bool = False) -> None:
    """Download `url` to `dest_file`. Thin network seam, monkeypatched in tests.

    Transient failures (HTTP 5xx, connectivity errors) are retried up to
    `_FETCH_ATTEMPTS` times with a growing delay -- GitHub's release-asset downloads
    occasionally return 504 for a single asset.

    Raises:
        MAGEMinDownloadError: On an HTTP error (including 404), or a 5xx/connectivity
            failure that persists across every attempt.
    """
    for attempt in range(1, _FETCH_ATTEMPTS + 1):
        try:
            urllib.request.urlretrieve(
                url, dest_file, reporthook=_download_progress_hook if verbose else None
            )
            return
        except (urllib.error.HTTPError, urllib.error.URLError) as exc:
            transient = not isinstance(exc, urllib.error.HTTPError) or exc.code >= 500
            if not transient or attempt == _FETCH_ATTEMPTS:
                raise MAGEMinDownloadError(f"failed to download {url}: {exc}") from exc
            _log(f"\n{exc}; retrying ({attempt}/{_FETCH_ATTEMPTS - 1})", verbose=verbose)
            time.sleep(_FETCH_RETRY_DELAY * attempt)
        finally:
            if verbose:
                print(file=sys.stderr)


def _write_marker(src_dir: Path) -> None:
    """Record `src_dir` as the "current" cache-installed MAGEMin source tree."""
    cache_dir = default_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / "current.txt").write_text(str(src_dir.resolve()) + "\n")


def download(
    version: str | None = None,
    dest: Path | str | None = None,
    *,
    force: bool = False,
    verbose: bool = False,
) -> Path:
    """Download a MAGEMin source tree from GitHub into `dest`.

    Args:
        version: See `resolve_ref`. Defaults to the latest published release
            (pass `version="latest"` for the `main` branch).
        dest: Directory the extracted source tree is moved to. Defaults to
            `default_cache_dir() / f"MAGEMin-{ref}"`. When left as the
            default, a successful download also updates the cache's
            "current" marker (see `magemin._lib`'s discovery) -- an
            explicitly given `dest` never does, so a one-off download to a
            scratch location can't silently change what `MAGEMin()` picks
            up elsewhere.
        force: If `dest` already exists and is non-empty: `False` (default)
            treats it as a cache hit and returns `dest` unchanged without
            re-downloading; `True` deletes and re-downloads.
        verbose: Print progress (ref resolution, download percentage,
            extraction, cache hits) to stderr.

    Returns:
        `dest`, containing the extracted MAGEMin source tree (`Makefile`,
        `src/`, etc. directly inside it).

    Raises:
        MAGEMinDownloadError: The ref doesn't exist upstream (404), a
            connectivity failure, or the downloaded archive has an
            unexpected internal layout.
    """
    if verbose and version is None:
        _log("Looking up the latest MAGEMin release...", verbose=verbose)
    ref = resolve_ref(version)
    _log(f"Resolved version to ref {ref!r}", verbose=verbose)
    explicit_dest = dest is not None
    dest = Path(dest) if dest is not None else default_cache_dir() / f"MAGEMin-{_safe_dirname(ref)}"

    if dest.exists() and any(dest.iterdir()) and not force:
        _log(f"Using cached source tree at {dest} (pass --force to re-download)", verbose=verbose)
        return dest

    url = _ARCHIVE_URL.format(owner=_GITHUB_OWNER, repo=_GITHUB_REPO, ref=ref)
    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        archive = tmp / "magemin.tar.gz"
        _log(f"Downloading {url}", verbose=verbose)
        try:
            _fetch(url, archive, verbose=verbose)
        except MAGEMinDownloadError as exc:
            if "HTTP Error 404" in str(exc):
                raise MAGEMinDownloadError(
                    f"MAGEMin ref {ref!r} not found on GitHub ({url})"
                ) from exc
            raise

        _log("Extracting archive...", verbose=verbose)
        extract_root = tmp / "extracted"
        with tarfile.open(archive, "r:gz") as tf:
            tf.extractall(extract_root, filter="data")

        try:
            (top_dir,) = [p for p in extract_root.iterdir() if p.is_dir()]
        except ValueError as exc:
            raise MAGEMinDownloadError(f"unexpected archive layout for ref {ref!r}") from exc

        if dest.exists():
            shutil.rmtree(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(top_dir), str(dest))

    _log(f"Source tree ready at {dest}", verbose=verbose)
    if not explicit_dest:
        _write_marker(dest)
    return dest


def _run(cmd: list[str], *, cwd: Path, verbose: bool = False) -> None:
    """Run a build command, raising MAGEMinDownloadError with captured output on failure."""
    _log(f"$ {' '.join(cmd)}", verbose=verbose)
    try:
        result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise MAGEMinDownloadError(
            f"{cmd[0]!r} not found on PATH -- install a C compiler and `make` "
            "(build-essential / Xcode Command Line Tools / MSYS2's make+gcc)"
        ) from exc
    if result.returncode != 0:
        raise MAGEMinDownloadError(
            f"command failed ({result.returncode}): {' '.join(cmd)}\n"
            f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
        )


def build(
    src_dir: Path | str,
    *,
    cc: str | None = None,
    inc: str | None = None,
    libs: str | None = None,
    verbose: bool = False,
) -> Path:
    """Build libMAGEMin from a MAGEMin source tree with its own `make lib`.

    Works on any MAGEMin source tree, e.g. one returned by `download()`. Pure
    Python/`subprocess` (no bash), so it also runs on Windows. Needs `make`, a
    C compiler, LAPACKE and NLopt.

    Args:
        src_dir: Directory containing MAGEMin's `Makefile` and `src/`.
        cc: C compiler. Defaults to the `CC` environment variable, or `gcc`
            (overriding the Makefile's own `clang` default).
        inc: Extra include flags, e.g. `-I/opt/homebrew/include` on macOS.
            Platform default if not given.
        libs: Link flags, e.g. `-lm -llapacke -lnlopt -L/usr/lib` on Linux.
            Platform default if not given.
        verbose: Print progress (each build step, the exact commands run) to
            stderr.

    Returns:
        Path to the built `libMAGEMin.{so,dylib,dll}`, written at
        `src_dir / "libMAGEMin.<ext>"`.

    Raises:
        MAGEMinDownloadError: The source tree's version (read from
            `src/initialize.c`) is older than `_MIN_SOURCE_VERSION`,
            `make`/`cc` is not on `PATH`, or `make clean`/`make lib` exits
            non-zero.

    Note:
        The Windows/MSYS2 defaults (`inc`/`libs`/`.dll` output) are not
        build-tested end-to-end. Pass `cc`/`inc`/`libs` explicitly if your
        MSYS2 layout differs -- or use the prebuilt binaries (`install()`).
    """
    src_dir = Path(src_dir)
    _check_source_version(src_dir)
    system = platform.system()
    cc = cc or os.environ.get("CC") or "gcc"
    inc = inc if inc is not None else _INC_DEFAULTS.get(system, "")
    libs = libs if libs is not None else _LIBS_DEFAULTS.get(system, "")
    ext = _LIB_EXT_BY_SYSTEM.get(system, "so")

    _log(f"Building with CC={cc} (system: {system})", verbose=verbose)
    _log("Cleaning previous build artifacts (make clean)...", verbose=verbose)
    _run(["make", "clean"], cwd=src_dir, verbose=verbose)

    _log("Building MAGEMin library (make lib) -- this can take a few minutes...", verbose=verbose)
    _run(
        ["make", "lib", "USE_MPI=0", f"CC={cc}", f"INC={inc}", f"LIBS={libs}"],
        cwd=src_dir,
        verbose=verbose,
    )
    # The Makefile's `lib:` target always names its output libMAGEMin.dylib.
    out = src_dir / f"libMAGEMin.{ext}"
    built = src_dir / "libMAGEMin.dylib"
    if built != out:
        built.replace(out)
    for obj in (src_dir / "src").rglob("*.o"):
        obj.unlink()

    _log(f"Built library at {out}", verbose=verbose)
    return out


def _github_api_json(url: str) -> object:
    """GET a GitHub API URL as JSON. Network seam, mockable.

    Sends `GITHUB_TOKEN` when set, lifting the unauthenticated rate limit (e.g. in CI).

    Raises:
        MAGEMinDownloadError: The request fails.
    """
    headers = {"User-Agent": "magemin-install", "Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers)) as response:
            return json.load(response)
    except (urllib.error.HTTPError, urllib.error.URLError) as exc:
        raise MAGEMinDownloadError(f"GitHub API request failed ({url}): {exc}") from exc


def _fetch_text(url: str) -> str:
    """Download a small text file. Network seam, mockable.

    Raises:
        MAGEMinDownloadError: On an HTTP error (including 404) or a connectivity failure.
    """
    request = urllib.request.Request(url, headers={"User-Agent": "magemin-install"})
    try:
        with urllib.request.urlopen(request) as response:
            return response.read().decode()
    except (urllib.error.HTTPError, urllib.error.URLError) as exc:
        raise MAGEMinDownloadError(f"failed to download {url}: {exc}") from exc


def _jll_file(repo: str, ref: str, file: str) -> str:
    return _fetch_text(_JLL_RAW_URL.format(owner=_JLL_OWNER, repo=repo, ref=ref, file=file))


def _jll_release_tag(repo: str, version: str) -> str:
    """Return the newest `<Name>-v{version}+N` release tag of a jll package.

    Raises:
        MAGEMinDownloadError: No release of that version exists.
    """
    name = repo.removesuffix("_jll")
    pattern = re.compile(rf"{re.escape(name)}-v{re.escape(version)}\+(\d+)")
    builds: list[tuple[int, str]] = []
    page = 1
    while True:
        releases = _github_api_json(
            _JLL_RELEASES_URL.format(owner=_JLL_OWNER, repo=repo, page=page)
        )
        if not isinstance(releases, list) or not releases:
            break
        for release in releases:
            match = pattern.fullmatch(release["tag_name"])
            if match:
                builds.append((int(match.group(1)), release["tag_name"]))
        page += 1
    if not builds:
        raise MAGEMinDownloadError(f"no prebuilt {repo} release for version {version}")
    return max(builds)[1]


def _host_platform() -> dict[str, str]:
    """Describe this machine in Artifacts.toml's platform terms."""
    system = platform.system()
    machine = platform.machine().lower()
    if system not in _JLL_OS or machine not in _ARCH_ALIASES:
        raise MAGEMinDownloadError(
            f"no prebuilt MAGEMin binaries for {system}/{platform.machine()}; "
            "build from source instead (magemin-install --from-source)"
        )
    host = {
        "arch": _ARCH_ALIASES[machine],
        "os": _JLL_OS[system],
        "libgfortran_version": "5.0.0",
        "cxxstring_abi": "cxx11",
    }
    if system == "Linux":
        host["libc"] = "glibc" if platform.libc_ver()[0] == "glibc" else "musl"
    if host["arch"].startswith("armv"):
        host["call_abi"] = "eabihf"
    return host


def _select_artifact(entries: list[dict], host: dict[str, str]) -> dict:
    """Pick the Artifacts.toml entry for `host`.

    An entry matches when every platform key it carries equals the host's value
    (keys it omits, like `libgfortran_version` on a package with no Fortran, match
    anything). Entries with unrecognized keys (sanitizer or microarchitecture
    variants) are skipped.

    Raises:
        MAGEMinDownloadError: No entry matches.
    """
    for entry in entries:
        if set(entry) - _ENTRY_KEYS:
            continue
        if all(entry[key] == host.get(key) for key in _PLATFORM_KEYS & set(entry)):
            return entry
    raise MAGEMinDownloadError(f"no prebuilt binary for platform {host}")


def _jll_artifact(repo: str, ref: str, host: dict[str, str]) -> dict:
    """Return the download entry ({"url", "sha256"}) of `repo` at `ref` for `host`."""
    artifacts = tomllib.loads(_jll_file(repo, ref, "Artifacts.toml"))
    (entries,) = artifacts.values()
    return _select_artifact(entries, host)["download"][0]


def _jll_dependency_ref(repo: str, compat: dict[str, str]) -> str:
    """The ref to fetch a dependency at: its exact `=X.Y.Z` compat pin, else its newest build."""
    pin = compat.get(repo, "")
    if pin.startswith("="):
        return _jll_release_tag(repo, pin.removeprefix("=").strip())
    return "main"


def _install_artifact(download: dict, dest: Path, *, main: bool, verbose: bool) -> None:
    """Download, verify and unpack one jll tarball, copying its runtime libraries into `dest`."""
    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        archive = tmp / "artifact.tar.gz"
        _log(f"Downloading {download['url']}", verbose=verbose)
        _fetch(download["url"], archive, verbose=verbose)
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        if digest != download["sha256"]:
            raise MAGEMinDownloadError(
                f"checksum mismatch for {download['url']}: expected {download['sha256']}, "
                f"got {digest}"
            )
        with tarfile.open(archive, "r:gz") as tf:
            tf.extractall(tmp / "x", filter="data")
        lib_dir = tmp / "x" / ("bin" if sys.platform == "win32" else "lib")
        prefixes = ("libMAGEMin.",) if main else _RUNTIME_LIBRARY_PREFIXES
        for path in sorted(lib_dir.glob("*")) if lib_dir.is_dir() else []:
            if path.name.startswith(prefixes) and not path.is_dir():
                target = dest / path.name
                target.unlink(missing_ok=True)
                if path.is_symlink():
                    target.symlink_to(os.readlink(path))
                else:
                    shutil.copy2(path, target)


def _resolve_binary_version(version: str | None) -> tuple[str, str]:
    """Map `version` to (MAGEMin version, MAGEMin_jll ref)."""
    if version is None:
        project = tomllib.loads(_jll_file(_MAGEMIN_JLL, "main", "Project.toml"))
        resolved = project["version"].split("+")[0]
        _check_min_version(tuple(int(part) for part in resolved.split(".")), resolved)
        return resolved, "main"
    if not _SEMVER_RE.fullmatch(version):
        raise MAGEMinDownloadError(
            f"prebuilt binaries exist only for released X.Y.Z versions, not {version!r}; "
            "build from source instead (magemin-install --from-source)"
        )
    _check_min_version(tuple(int(part) for part in version.split(".")), version)
    return version, _jll_release_tag(_MAGEMIN_JLL, version)


def install_binary(
    version: str | None = None,
    dest: Path | str | None = None,
    *,
    force: bool = False,
    verbose: bool = False,
) -> Path:
    """Install the prebuilt MAGEMin library (MAGEMin_jll) and its runtime libraries.

    Args:
        version: An `X.Y.Z` MAGEMin release, or `None` (default) for the newest
            prebuilt one.
        dest: Directory to install into. Defaults to
            `default_cache_dir() / f"MAGEMin-{version}-bin"`; only the default
            updates the cache's "current" marker (see `download`).
        force: Re-install even if `dest` already holds a library.
        verbose: Print progress to stderr.

    Returns:
        Path to the installed `libMAGEMin.{so,dylib,dll}`.

    Raises:
        MAGEMinDownloadError: No prebuilt binary for this platform or version, a
            download or checksum failure, or the release predates the C API this
            package needs.
    """
    host = _host_platform()
    resolved, ref = _resolve_binary_version(version)
    _log(f"Installing prebuilt MAGEMin {resolved} for {host['arch']}-{host['os']}", verbose=verbose)
    explicit_dest = dest is not None
    dest = Path(dest) if dest is not None else default_cache_dir() / f"MAGEMin-{resolved}-bin"
    ext = _LIB_EXT_BY_SYSTEM.get(platform.system(), "so")
    lib_path = dest / f"libMAGEMin.{ext}"

    if lib_path.exists() and not force:
        _log(f"Using installed library at {lib_path} (pass --force to reinstall)", verbose=verbose)
    else:
        project = tomllib.loads(_jll_file(_MAGEMIN_JLL, ref, "Project.toml"))
        compat = project.get("compat", {})
        if dest.exists():
            shutil.rmtree(dest)
        dest.mkdir(parents=True)
        for repo in _JLL_DEPENDENCIES:
            if repo not in project.get("deps", {}):
                continue
            download = _jll_artifact(repo, _jll_dependency_ref(repo, compat), host)
            _install_artifact(download, dest, main=False, verbose=verbose)
        download = _jll_artifact(_MAGEMIN_JLL, ref, host)
        _install_artifact(download, dest, main=True, verbose=verbose)

    _check_loadable(lib_path, resolved)
    if not explicit_dest:
        _write_marker(dest)
    _log(f"Installed library at {lib_path}", verbose=verbose)
    return lib_path


def _check_loadable(lib_path: Path, version: str) -> None:
    """Load the installed library once, so a broken or too-old install fails here.

    Raises:
        MAGEMinDownloadError: The library can't be loaded, or lacks the needed C API.
    """
    from magemin import _lib
    from magemin.errors import MAGEMinLibraryNotFoundError

    try:
        _lib._load(lib_path)
    except MAGEMinLibraryNotFoundError as exc:
        raise MAGEMinDownloadError(
            f"the prebuilt MAGEMin {version} predates the C API this package needs; install the "
            "newest release (magemin-install) or build a newer source tree (magemin-install latest)"
        ) from exc
    except OSError as exc:
        raise MAGEMinDownloadError(f"installed {lib_path} could not be loaded: {exc}") from exc


def install(
    version: str | None = None,
    dest: Path | str | None = None,
    *,
    from_source: bool = False,
    force: bool = False,
    cc: str | None = None,
    inc: str | None = None,
    libs: str | None = None,
    verbose: bool = False,
) -> Path:
    """Install the MAGEMin C library, returning the path to it.

    The main entry point for most callers and for the `magemin-install` console
    script. Released versions install the prebuilt binaries (`install_binary`) --
    no compiler needed. `version="latest"` (the `main` branch), any other git ref,
    or `from_source=True` downloads and builds the source instead
    (`build(download(...))`).

    Args:
        version: `None` (default) for the newest release, `X.Y.Z`, `"latest"`, or
            a git ref -- see `resolve_ref`.
        dest: Install directory (binaries) or source-tree directory (source
            build). Defaults to a per-user cache directory.
        from_source: Build from source even for a released version.
        force: Re-download even if `dest` is already populated.
        cc: Source builds only, see `build`.
        inc: Source builds only, see `build`.
        libs: Source builds only, see `build`.
        verbose: Print progress to stderr.

    Returns:
        Path to the installed `libMAGEMin.{so,dylib,dll}`.
    """
    is_release = version is None or _SEMVER_RE.fullmatch(version) is not None
    if is_release and not from_source:
        return install_binary(version, dest, force=force, verbose=verbose)
    src_dir = download(version, dest, force=force, verbose=verbose)
    return build(src_dir, cc=cc, inc=inc, libs=libs, verbose=verbose)


def main(argv: list[str] | None = None) -> int:
    """Entry point for the `magemin-install` console script."""
    parser = argparse.ArgumentParser(
        prog="magemin-install",
        description="Install the MAGEMin C library: prebuilt binaries for released versions, "
        "or a source build.",
    )
    parser.add_argument(
        "version",
        nargs="?",
        default=None,
        help="MAGEMin version to install: X.Y.Z for a release (prebuilt binaries), "
        '"latest" for the tip of the main branch, or any other git ref (branch/tag/SHA) -- '
        "both built from source. Defaults to the newest prebuilt release.",
    )
    parser.add_argument(
        "--dest",
        default=None,
        help="Install directory (or source-tree directory for a source build). "
        "Defaults to a per-user cache directory.",
    )
    parser.add_argument(
        "--from-source",
        action="store_true",
        help="Build from source even for a released version (needs make, a C compiler, "
        "LAPACKE and NLopt).",
    )
    parser.add_argument(
        "--cc", default=None, help="Source builds: C compiler (default: $CC or gcc)."
    )
    parser.add_argument("--inc", default=None, help="Source builds: extra include flags.")
    parser.add_argument("--libs", default=None, help="Source builds: linker flags.")
    parser.add_argument(
        "--force", action="store_true", help="Re-download even if --dest already exists."
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--download-only",
        action="store_true",
        help="Source builds: only download the source tree, skip building.",
    )
    group.add_argument(
        "--build-only",
        action="store_true",
        help="Source builds: only build; --dest (or the default cache path for the version "
        "argument) must already contain a downloaded source tree.",
    )
    parser.add_argument(
        "--quiet", action="store_true", help="Suppress progress output (only errors/result path)."
    )
    args = parser.parse_args(argv)
    verbose = not args.quiet

    try:
        if args.build_only:
            if args.dest is None and args.version is None:
                raise MAGEMinDownloadError(
                    "--build-only needs --dest or an explicit version argument when "
                    "defaulting to the latest release, since finding the latest release "
                    "requires a network lookup --build-only is meant to avoid"
                )
            src_dir = (
                Path(args.dest)
                if args.dest
                else default_cache_dir() / f"MAGEMin-{_safe_dirname(resolve_ref(args.version))}"
            )
            _log(f"Using source tree at {src_dir}", verbose=verbose)
            result = build(src_dir, cc=args.cc, inc=args.inc, libs=args.libs, verbose=verbose)
        elif args.download_only:
            result = download(args.version, args.dest, force=args.force, verbose=verbose)
        else:
            result = install(
                args.version,
                args.dest,
                from_source=args.from_source,
                force=args.force,
                cc=args.cc,
                inc=args.inc,
                libs=args.libs,
                verbose=verbose,
            )
    except MAGEMinError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    _log("Done.", verbose=verbose)
    print(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
