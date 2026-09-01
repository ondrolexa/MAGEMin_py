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
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
magemin_src="${MAGEMIN_SRC_DIR:-$repo_root/MAGEMin}"
cc="${CC:-gcc}"

cd "$magemin_src"
make clean
make lib USE_MPI=0 CC="$cc"
# `make lib`'s own link output is superseded by our relink below (we only
# needed its side effect: the vendored .o files, which `lib:` -- unlike
# `all:` -- does not clean up afterward).
rm -f libMAGEMin.dylib

ccflags="-Wall -O3 -g -fPIC -pthread -Wno-unused-variable -Wno-unused-but-set-variable -march=native -funroll-loops"
inc=""
if [[ "$(uname -s)" == "Darwin" ]]; then
    inc="-I/opt/homebrew/include"
fi

"$cc" $ccflags -c "$repo_root/magemin_ext/magemin_ext.c" \
    -I"$magemin_src/src" -I"$repo_root/magemin_ext" \
    -o "$repo_root/magemin_ext/magemin_ext.o" $inc

vendored_objects=$(find "$magemin_src/src" -name '*.o')

if [[ "$(uname -s)" == "Linux" ]]; then
    out="$magemin_src/libMAGEMin.so"
    libs="-lm -llapacke -lnlopt -L/usr/lib"
else
    out="$magemin_src/libMAGEMin.dylib"
    libs="-lm -framework Accelerate /opt/homebrew/lib/libnlopt.dylib"
fi

"$cc" -shared -fPIC -pthread -o "$out" \
    $vendored_objects "$repo_root/magemin_ext/magemin_ext.o" \
    $inc $libs -flto

echo "Built: $out"
