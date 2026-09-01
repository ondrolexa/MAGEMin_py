"""Download and build the MAGEMin C library from GitHub.

Private module: public functions (`install`, `default_cache_dir`) are re-exported at the
top-level ``magemin`` package. Provides an alternative to ``scripts/build_lib.sh`` for
obtaining a buildable ``MAGEMin/`` source tree without git-vendoring it into this repo --
useful for a future non-monorepo install. Stdlib-only (``urllib.request``, ``tarfile``,
``subprocess``, ``platform``), no runtime dependency added.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

from magemin.errors import MAGEMinDownloadError, MAGEMinError

_GITHUB_OWNER = "ComputationalThermodynamics"
_GITHUB_REPO = "MAGEMin"
_ARCHIVE_URL = "https://github.com/{owner}/{repo}/archive/{ref}.tar.gz"
_RELEASES_LATEST_URL = "https://api.github.com/repos/{owner}/{repo}/releases/latest"

_SEMVER_RE = re.compile(r"\d+\.\d+\.\d+")
_UNSAFE_DIRNAME_CHARS_RE = re.compile(r"[^A-Za-z0-9._-]")

# Platform defaults, mirroring scripts/build_lib.sh's Linux/Darwin values exactly, plus a
# best-effort Windows/MSYS2 row (see build()'s docstring -- not build-tested on this dev
# machine, which has no Windows/MSYS2 environment).
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

_CCFLAGS = [
    "-Wall",
    "-O3",
    "-g",
    "-fPIC",
    "-pthread",
    "-Wno-unused-variable",
    "-Wno-unused-but-set-variable",
    "-march=native",
    "-funroll-loops",
]


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
            lookup fails (see `_latest_release_ref`).
    """
    if version is None:
        return _latest_release_ref()
    if version == "latest":
        return "main"
    if _SEMVER_RE.fullmatch(version):
        return f"v{version}"
    return version


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

    Raises:
        MAGEMinDownloadError: On an HTTP error (including 404) or a
            connectivity failure.
    """
    try:
        urllib.request.urlretrieve(
            url, dest_file, reporthook=_download_progress_hook if verbose else None
        )
    except (urllib.error.HTTPError, urllib.error.URLError) as exc:
        raise MAGEMinDownloadError(f"failed to download {url}: {exc}") from exc
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
        `dest`, containing the extracted MAGEMin source tree (same layout as
        the vendored `MAGEMin/`: `Makefile`, `src/`, etc. directly inside it).

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
    """Build libMAGEMin from a MAGEMin source tree via `make` + a C compiler.

    Works identically whether `src_dir` is the vendored `MAGEMin/` tree or a
    tree returned by `download()` -- no special-casing which one it is.
    Reimplements `scripts/build_lib.sh`'s logic in pure Python/`subprocess`
    (no bash), so it also runs on Windows.

    Args:
        src_dir: Directory containing MAGEMin's `Makefile` and `src/`.
        cc: C compiler. Defaults to the `CC` environment variable, or `gcc`
            (matching `scripts/build_lib.sh`'s override of the vendored
            Makefile's own `clang` default).
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
        MAGEMinDownloadError: `make`/`cc` is not on `PATH`, or any build step
            (`make clean`, `make lib`, compiling `magemin_ext.c`, or the
            final link) exits non-zero.

    Note:
        The Windows/MSYS2 defaults (`inc`/`libs`/`.dll` output) are designed
        from documented MSYS2 mingw64 packaging conventions and this
        project's verified Makefile command-line-override mechanics -- they
        are not build-tested end-to-end (no Windows/MSYS2 environment is
        available in this project's own development/test environment). Pass
        `cc`/`inc`/`libs` explicitly if your MSYS2 layout differs.
    """
    src_dir = Path(src_dir)
    system = platform.system()
    cc = cc or os.environ.get("CC") or "gcc"
    inc = inc if inc is not None else _INC_DEFAULTS.get(system, "")
    libs = libs if libs is not None else _LIBS_DEFAULTS.get(system, "")
    ext = _LIB_EXT_BY_SYSTEM.get(system, "so")

    repo_root = Path(__file__).resolve().parents[2]
    magemin_ext_dir = repo_root / "magemin_ext"
    ext_c = magemin_ext_dir / "magemin_ext.c"
    ext_o = magemin_ext_dir / "magemin_ext.o"

    _log(f"Building with CC={cc} (system: {system})", verbose=verbose)

    _log("Cleaning previous build artifacts (make clean)...", verbose=verbose)
    _run(["make", "clean"], cwd=src_dir, verbose=verbose)

    _log("Building MAGEMin library (make lib) -- this can take a few minutes...", verbose=verbose)
    _run(
        ["make", "lib", "USE_MPI=0", f"CC={cc}", f"INC={inc}", f"LIBS={libs}"],
        cwd=src_dir,
        verbose=verbose,
    )
    # The Makefile's own `lib:` target always names its output libMAGEMin.dylib,
    # even on Linux/Windows -- only its .o byproducts (which `lib:`, unlike
    # `all:`, leaves behind) are wanted.
    (src_dir / "libMAGEMin.dylib").unlink(missing_ok=True)

    compile_cmd = [
        cc,
        *_CCFLAGS,
        "-c",
        str(ext_c),
        "-I",
        str(src_dir / "src"),
        "-I",
        str(magemin_ext_dir),
        "-o",
        str(ext_o),
    ]
    if inc:
        compile_cmd += shlex.split(inc)
    _log("Compiling magemin_ext.c...", verbose=verbose)
    _run(compile_cmd, cwd=repo_root, verbose=verbose)

    objects = sorted(str(p) for p in (src_dir / "src").rglob("*.o"))
    out = src_dir / f"libMAGEMin.{ext}"
    link_cmd = [cc, "-shared", "-fPIC", "-pthread", "-o", str(out), *objects, str(ext_o)]
    if inc:
        link_cmd += shlex.split(inc)
    if libs:
        link_cmd += shlex.split(libs)
    link_cmd += ["-flto"]
    _log(f"Linking {out.name} from {len(objects)} object files...", verbose=verbose)
    _run(link_cmd, cwd=repo_root, verbose=verbose)

    _log(f"Built library at {out}", verbose=verbose)
    return out


def install(
    version: str | None = None,
    dest: Path | str | None = None,
    *,
    force: bool = False,
    cc: str | None = None,
    inc: str | None = None,
    libs: str | None = None,
    verbose: bool = False,
) -> Path:
    """Download and build MAGEMin, returning the path to the built library.

    Equivalent to `build(download(version, dest, force=force), cc=cc, inc=inc,
    libs=libs)`. The main entry point for most callers and for the
    `magemin-install` console script.

    Args:
        version: See `resolve_ref`. Defaults to the latest published release
            (pass `version="latest"` for the `main` branch).
        dest: See `download`. Defaults to a per-user cache directory.
        force: See `download`.
        cc: See `build`.
        inc: See `build`.
        libs: See `build`.
        verbose: Print download/build progress to stderr.

    Returns:
        Path to the built `libMAGEMin.{so,dylib,dll}`.
    """
    src_dir = download(version, dest, force=force, verbose=verbose)
    return build(src_dir, cc=cc, inc=inc, libs=libs, verbose=verbose)


def main(argv: list[str] | None = None) -> int:
    """Entry point for the `magemin-install` console script."""
    parser = argparse.ArgumentParser(
        prog="magemin-install",
        description="Download and build the MAGEMin C library from GitHub.",
    )
    parser.add_argument(
        "version",
        nargs="?",
        default=None,
        help='MAGEMin version to install: "latest" for the tip of the main branch '
        "(bleeding edge, not necessarily a tagged release), X.Y.Z for release tag "
        "vX.Y.Z, or any other git ref (branch/tag/SHA). Defaults to the latest "
        "published release.",
    )
    parser.add_argument(
        "--dest",
        default=None,
        help="Destination directory for the source tree. Defaults to a per-user cache directory.",
    )
    parser.add_argument("--cc", default=None, help="C compiler (default: $CC or gcc).")
    parser.add_argument("--inc", default=None, help="Extra compiler include flags.")
    parser.add_argument("--libs", default=None, help="Linker flags.")
    parser.add_argument(
        "--force", action="store_true", help="Re-download even if --dest already exists."
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--download-only",
        action="store_true",
        help="Only download the source tree, skip building.",
    )
    group.add_argument(
        "--build-only",
        action="store_true",
        help="Only build; --dest (or the default cache path for the version argument) must "
        "already contain a downloaded/vendored source tree. Skips the network fetch.",
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
