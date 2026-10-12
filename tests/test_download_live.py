"""Real, network-touching end-to-end tests for magemin._download.

Deliberately excluded from the default `pytest` collection (see the
module-level skip below) -- these download prebuilt MAGEMin_jll binaries from
github.com/JuliaBinaryWrappers, and build MAGEMin's main branch from
github.com/ComputationalThermodynamics/MAGEMin. Slow (minutes), and depends on
network access; the source-build test also needs a working C toolchain
(liblapacke-dev/libnlopt-dev + gcc/clang, same prerequisites as
scripts/build_lib.sh).

Run manually by temporarily commenting out the `pytestmark = pytest.mark.skip(...)`
line below, then:

    uv run pytest tests/test_download_live.py -v

and restore the `pytestmark` line afterward.
"""

import ctypes

import pytest

from magemin import _download, _lib
from magemin.errors import MAGEMinDownloadError

pytestmark = pytest.mark.skip(
    reason="hits the real network and runs a full C build; run manually, see module docstring"
)


def test_install_prebuilt_latest_release(tmp_path):  # noqa: ANN001, ANN201
    """The newest prebuilt release installs, loads, and passes the C-API check."""
    lib_path = _download.install(dest=tmp_path / "bin")
    assert isinstance(_lib._load(lib_path), ctypes.CDLL)


def test_prebuilt_release_without_c_api_is_rejected(tmp_path):  # noqa: ANN001, ANN201
    """2.0.7 predates the C API, so it is refused before anything is downloaded."""
    with pytest.raises(MAGEMinDownloadError, match=">= 2.0.8"):
        _download.install("2.0.7", dest=tmp_path / "bin")


def test_install_from_source_main_branch(tmp_path):  # noqa: ANN001, ANN201
    """A real download+build of the main branch (HEAD), via version="latest"."""
    lib_path = _download.install(version="latest", dest=tmp_path / "MAGEMin-latest")
    assert isinstance(_lib._load(lib_path), ctypes.CDLL)


def test_get_library_picks_up_cache_install(monkeypatch, tmp_path):  # noqa: ANN001, ANN201
    """A real install() into the default-cache flow is auto-discovered by get_library()."""
    cache_dir = tmp_path / "cache"
    monkeypatch.setattr(_download, "default_cache_dir", lambda: cache_dir)
    monkeypatch.setattr(_lib, "_library", None)
    monkeypatch.delenv("MAGEMIN_LIB_PATH", raising=False)
    # Force fall-through past the (already-built, on this dev machine) vendored
    # tree, so this actually exercises the cache-dir discovery tier.
    monkeypatch.setattr(_lib, "_candidate_paths", lambda: [])

    _download.install()  # default dest -> writes the marker

    lib = _lib.get_library()
    assert isinstance(lib, ctypes.CDLL)
