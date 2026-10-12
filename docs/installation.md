# Installation

## Python package

```sh
pip install magemin
# or: uv add magemin
```

## Installing the MAGEMin library

The recommended way is to install the official prebuilt binaries of the latest MAGEMin release:

```sh
magemin-install
```

This downloads the official prebuilt MAGEMin binaries -- `MAGEMin_jll`, built by Julia's
[Yggdrasil](https://github.com/JuliaPackaging/Yggdrasil) for Linux (glibc and musl), macOS and
Windows on x86_64 and ARM -- together with the runtime libraries they link against (NLopt,
OpenBLAS, the GCC runtime), verifies their checksums, and installs them side by side into a
per-user cache directory (e.g. `~/.cache/magemin` on Linux). No compiler or system packages are
needed, and `magemin` finds the library automatically on the next import. Options:

```sh
magemin-install X.Y.Z               # a specific release
magemin-install --dest /path/to/dir # install somewhere else (see MAGEMIN_LIB_PATH below)
magemin-install --force             # reinstall over an existing install
```

MAGEMin **2.0.8 or newer** is required: it is the first release with the C API this package uses
(`MAGEMin_api.h`). `magemin-install` refuses older releases, and `import`-time loading rejects an
older library with a clear error.

## Building from source (developers)

To use unreleased MAGEMin changes -- the tip of its `main` branch or any other git ref -- or on a
platform without prebuilt binaries, download and build the source instead. This needs `make`, a C
compiler, LAPACKE and NLopt (`sudo apt install liblapacke-dev libnlopt-dev` on Debian/Ubuntu):

```sh
magemin-install latest              # the main branch (HEAD)
magemin-install some-ref            # any other branch/tag/commit SHA
magemin-install X.Y.Z --from-source # a release, built locally
magemin-install latest --cc clang --libs "-lm -llapacke -lnlopt"
```

This runs MAGEMin's own `make lib` (with `USE_MPI=0`, since neither the API nor this package's
parallelism needs MPI). On Windows it needs a MinGW-w64 toolchain such as
[MSYS2](https://www.msys2.org/) with its `mingw-w64-x86_64-gcc`, `-lapack` and `-nlopt` packages,
run from a "mingw64" shell; this path is best-effort and not tested by this project -- prefer the
prebuilt binaries there.

### From an existing MAGEMin source tree

To build a MAGEMin checkout you already have, use the dev repo's script:

```sh
MAGEMIN_SRC_DIR=/path/to/MAGEMin ./scripts/build_lib.sh
```

Nothing under the source tree is modified beyond `make`'s own build output. The script is only
part of the dev repo, not the published package.

## Pointing at a different library location

If your compiled library lives elsewhere, point `magemin` at it with an environment variable:

```sh
export MAGEMIN_LIB_PATH=/path/to/libMAGEMin.so
```

Creating a [`MAGEMin`][magemin.core.MAGEMin] instance (and therefore every other entry point) will
raise a [`MAGEMinLibraryNotFoundError`][magemin.errors.MAGEMinLibraryNotFoundError] with actionable
instructions if the library can't be located at all. Library discovery also checks the per-user
cache directory `magemin-install` writes into, before falling back to a system-wide search.

## Verifying the install

```sh
python -c "from magemin import MAGEMin, bulk_rocks; print(MAGEMin('ig').compute(P=8, T=800, bulk=bulk_rocks.KLB1_IG))"
```

## Development

Clone this repo, then:

```sh
uv sync --group dev
uv run pytest
uv run ruff check .
uv run ruff format .
```

Most tests require the compiled library and are skipped gracefully if it isn't built.

### Building this documentation site

```sh
uv sync --group docs
uv run mkdocs serve   # live-reloading local preview
uv run mkdocs build   # static site in site/
```
