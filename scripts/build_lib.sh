#!/usr/bin/env bash
# Build MAGEMin + the magemin_ext/ companion extension into one shared library
# usable by the Python ctypes wrapper. Requires liblapacke-dev and libnlopt-dev
# (and a C compiler) to be installed on the system.
#
# MAGEMIN_SRC_DIR (default: ./MAGEMin) selects where the vendored MAGEMin
# source lives. This script never modifies anything under it -- it only
# builds MAGEMin's own `make lib` output, then compiles magemin_ext/ against
# the same headers and links everything into one library. Keeping the source
# location configurable makes it easy to later point this script at a
# separately-downloaded/updated copy of MAGEMin without changing this file.
#
# SANITIZE=1 builds with AddressSanitizer + UndefinedBehaviorSanitizer instead
# (-O1, no LTO) -- a debugging build for catching heap bugs (out-of-bounds or
# uninitialized reads). Python itself isn't instrumented, so the ASan
# runtime has to be preloaded; the exact command is printed at the end.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
magemin_src="${MAGEMIN_SRC_DIR:-$repo_root/MAGEMin}"
cc="${CC:-gcc}"

# Keep in sync with MIN_MAGEMIN_VERSION in src/magemin/_download.py.
min_version="2.0.7"
version="$(grep -oE 'strcpy\(gv\.version,"[0-9]+\.[0-9]+\.[0-9]+' "$magemin_src/src/initialize.c" | grep -oE '[0-9]+\.[0-9]+\.[0-9]+$' || true)"
if [[ -z "$version" ]]; then
    echo "warning: could not determine the MAGEMin version; versions older than $min_version are unsupported" >&2
elif [[ "$(printf '%s\n%s\n' "$min_version" "$version" | sort -V | head -n1)" != "$min_version" ]]; then
    echo "error: MAGEMin $version is not supported; this package requires MAGEMin >= $min_version" >&2
    exit 1
fi

ccflags="-Wall -O3 -g -fPIC -Wno-unused-variable -Wno-unused-but-set-variable -march=native -funroll-loops"
san=""
lto="-flto"
if [[ "${SANITIZE:-0}" == "1" ]]; then
    san="-fsanitize=address,undefined -fno-omit-frame-pointer"
    ccflags="-Wall -O1 -g -fPIC -Wno-unused-variable -Wno-unused-but-set-variable $san"
    lto=""
fi

cd "$magemin_src"
make clean
make lib USE_MPI=0 CC="$cc" CCFLAGS="$ccflags"
# `make lib`'s own link output is superseded by our relink below (we only
# needed its side effect: the vendored .o files, which `lib:` -- unlike
# `all:` -- does not clean up afterward).
rm -f libMAGEMin.dylib

inc=""
if [[ "$(uname -s)" == "Darwin" ]]; then
    inc="-I/opt/homebrew/include"
fi

"$cc" $ccflags -c "$repo_root/src/magemin/magemin_ext/magemin_ext.c" \
    -I"$magemin_src/src" -I"$repo_root/src/magemin/magemin_ext" \
    -o "$repo_root/src/magemin/magemin_ext/magemin_ext.o" $inc

vendored_objects=$(find "$magemin_src/src" -name '*.o')

if [[ "$(uname -s)" == "Linux" ]]; then
    out="$magemin_src/libMAGEMin.so"
    libs="-lm -llapacke -lnlopt -L/usr/lib"
else
    out="$magemin_src/libMAGEMin.dylib"
    libs="-lm -framework Accelerate /opt/homebrew/lib/libnlopt.dylib"
fi

"$cc" -shared -fPIC -o "$out" \
    $vendored_objects "$repo_root/src/magemin/magemin_ext/magemin_ext.o" \
    $inc $libs $san $lto

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
