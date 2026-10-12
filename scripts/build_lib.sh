#!/usr/bin/env bash
# Build libMAGEMin from a MAGEMin source tree, for developing against unreleased
# source (users get prebuilt binaries via `magemin-install`). Runs MAGEMin's own
# `make lib` -- requires liblapacke-dev, libnlopt-dev and a C compiler.
#
# MAGEMIN_SRC_DIR (default: ./MAGEMin) selects the source tree; nothing in it is
# touched beyond `make`'s own build output.
#
# SANITIZE=1 builds with AddressSanitizer + UndefinedBehaviorSanitizer instead
# (-O1, no LTO) -- a debugging build for catching heap bugs (out-of-bounds or
# uninitialized reads). Python itself isn't instrumented, so the ASan
# runtime has to be preloaded; the exact command is printed at the end.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
magemin_src="${MAGEMIN_SRC_DIR:-$repo_root/MAGEMin}"
cc="${CC:-gcc}"

# Keep in sync with _MIN_SOURCE_VERSION in src/magemin/_download.py.
min_version="2.0.8"
version="$(grep -oE 'strcpy\(gv\.version,"[0-9]+\.[0-9]+\.[0-9]+' "$magemin_src/src/initialize.c" | grep -oE '[0-9]+\.[0-9]+\.[0-9]+$' || true)"
if [[ -z "$version" ]]; then
    echo "warning: could not determine the MAGEMin version; versions older than $min_version are unsupported" >&2
elif [[ "$(printf '%s\n%s\n' "$min_version" "$version" | sort -V | head -n1)" != "$min_version" ]]; then
    echo "error: MAGEMin $version is not supported; this package requires MAGEMin >= $min_version" >&2
    exit 1
fi

make_args=(USE_MPI=0 CC="$cc")
san=""
if [[ "${SANITIZE:-0}" == "1" ]]; then
    san="-fsanitize=address,undefined -fno-omit-frame-pointer"
    make_args+=(CCFLAGS="-Wall -O1 -g -fPIC -Wno-unused-variable -Wno-unused-but-set-variable $san")
    if [[ "$(uname -s)" == "Darwin" ]]; then
        make_args+=(LIBS="-lm -framework Accelerate /opt/homebrew/lib/libnlopt.dylib $san")
    else
        make_args+=(LIBS="-lm -llapacke -lnlopt -L/usr/lib $san")
    fi
fi

cd "$magemin_src"
make clean
make lib "${make_args[@]}"

# `make lib` always names its output libMAGEMin.dylib, even on Linux.
if [[ "$(uname -s)" == "Linux" ]]; then
    out="$magemin_src/libMAGEMin.so"
    mv libMAGEMin.dylib "$out"
else
    out="$magemin_src/libMAGEMin.dylib"
fi
find "$magemin_src/src" -name '*.o' -delete

echo "Built: $out"
if [[ -n "$san" ]]; then
    echo "Run the tests with the ASan runtime preloaded (plotting tests excluded: matplotlib's"
    echo "own extensions don't run under a preloaded ASan):"
    echo "  LD_PRELOAD=$("$cc" -print-file-name=libasan.so) PYTHONMALLOC=malloc \\"
    echo "  ASAN_OPTIONS=detect_leaks=0:halt_on_error=1:malloc_fill_byte=190 \\"
    echo "  UBSAN_OPTIONS=print_stacktrace=1:halt_on_error=1 \\"
    echo "  .venv/bin/python -m pytest --deselect tests/test_download_live.py \\"
    echo "      --ignore=tests/test_diagrams_plot.py --ignore=tests/test_pseudosection_plot.py"
fi
