# Installation

## Python package

```sh
uv sync
```

## Compiling the C library

Building the vendored C library additionally requires:

- A C compiler (e.g. `gcc` or `clang`)
- `liblapacke-dev`
- `libnlopt-dev`

On Debian/Ubuntu:

```sh
sudo apt install liblapacke-dev libnlopt-dev
```

Then build the library:

```sh
./scripts/build_lib.sh
```

This runs `make lib` inside `MAGEMin/` (with `USE_MPI=0`, since neither the API nor this package's
parallelism needs MPI), then compiles the `magemin_ext/` companion extension (which adds
buffer/activity fixing, phase suppression, sb/gh database support, and phase-name discovery on top
of MAGEMin's own internal functions -- see `magemin_ext/magemin_ext.h` for its C-level contract) and
links it together with MAGEMin's object files into one `MAGEMin/libMAGEMin.so`. If your system's
`cc`/`clang` isn't available, set `CC=gcc ./scripts/build_lib.sh` (or any other compiler).

The vendored source location defaults to `./MAGEMin` and can be overridden with `MAGEMIN_SRC_DIR`
(e.g. `MAGEMIN_SRC_DIR=/path/to/MAGEMin ./scripts/build_lib.sh`) -- nothing under it is ever modified
by this build, which keeps it safe to point at a separately managed/updated copy.

## Downloading and building automatically

If you don't have (or don't want to use) the vendored `MAGEMin/` tree, `magemin-install` downloads
a MAGEMin source release from GitHub and builds it, in one step:

```sh
uv run magemin-install
```

By default this fetches the latest **published release** into a per-user cache directory (e.g.
`~/.cache/magemin` on Linux) and builds it there; `magemin` finds it automatically on the next
import, no environment variable needed. Options:

```sh
uv run magemin-install latest              # the main branch (dev/HEAD) instead of a release
uv run magemin-install 2.0.0               # a specific tagged release (-> git ref v2.0.0)
uv run magemin-install some-sha            # any other branch/tag/commit SHA
uv run magemin-install --dest /path/to/dir --cc clang
```

Same prerequisites as "Compiling the C library" above (a C compiler, `liblapacke-dev`,
`libnlopt-dev`/equivalents, and `make` on `PATH`) -- this doesn't remove that requirement, it just
also fetches the source for you instead of relying on the git-vendored copy.

### Windows

`magemin-install` runs on Windows, but driving `make`/`gcc` there requires a MinGW-w64 toolchain you
provide yourself -- typically [MSYS2](https://www.msys2.org/) with its `mingw-w64-x86_64-gcc`,
`mingw-w64-x86_64-lapack`, and `mingw-w64-x86_64-nlopt` packages installed, run from an MSYS2
"mingw64" shell so `-llapacke -lnlopt` resolve via MSYS2's own `CPATH`/`LIBRARY_PATH` conventions
(or WSL, treated as Linux). This is the same category of prerequisite as `liblapacke-dev`/
`libnlopt-dev` on Linux, not a zero-setup feature. **The Windows/MSYS2 path is best-effort and
community-testable, not verified by this project's own test suite** (which runs on Linux); if your
MSYS2 layout differs from the defaults, pass `--cc`/`--inc`/`--libs` explicitly.

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
uv run python -c "from magemin import MAGEMin, bulk_rocks; print(MAGEMin('ig').compute(P=8, T=800, bulk=bulk_rocks.KLB1_IG))"
```

## Development

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
