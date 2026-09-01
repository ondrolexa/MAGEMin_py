"""Real, network-touching end-to-end tests for magemin._download.

Deliberately excluded from the default `pytest` collection (see the
module-level skip below) -- these download and build MAGEMin for real
against github.com/ComputationalThermodynamics/MAGEMin, which is slow
(minutes) and depends on network access and a working C toolchain
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

pytestmark = pytest.mark.skip(
    reason="hits the real network and runs a full C build; run manually, see module docstring"
)

_EXPECTED_SYMBOLS = (
    "MAGEMin_Init",
    "MAGEMin_NOxides",
    "MAGEMin_OxideNames",
    "MAGEMin_ComputeEquilibrium",
    "MAGEMin_Free",
    "MAGEMin_InitEx",
    "MAGEMin_SetBuffer",
    "MAGEMin_ComputeEquilibriumEx",
    "MAGEMin_NSolutionPhases",
    "MAGEMin_SolutionPhaseNames",
    "MAGEMin_NPurePhases",
    "MAGEMin_PurePhaseNames",
)


def _assert_loadable_with_all_symbols(lib_path):  # noqa: ANN001, ANN202
    lib = ctypes.CDLL(str(lib_path))
    for name in _EXPECTED_SYMBOLS:
        assert hasattr(lib, name)


def test_download_and_build_tag_v2_0_0(tmp_path):  # noqa: ANN001, ANN201
    """A real download+build of the v2.0.0 release tag."""
    lib_path = _download.install(version="2.0.0", dest=tmp_path / "MAGEMin-2.0.0")
    assert lib_path.exists()
    _assert_loadable_with_all_symbols(lib_path)


def test_download_and_build_latest(tmp_path):  # noqa: ANN001, ANN201
    """A real download+build of the main branch (HEAD), via version="latest"."""
    lib_path = _download.install(version="latest", dest=tmp_path / "MAGEMin-latest")
    assert lib_path.exists()
    _assert_loadable_with_all_symbols(lib_path)


def test_download_and_build_latest_release(tmp_path):  # noqa: ANN001, ANN201
    """A real download+build of the latest published release -- the version=None default."""
    lib_path = _download.install(version=None, dest=tmp_path / "MAGEMin-latest")
    assert lib_path.exists()
    _assert_loadable_with_all_symbols(lib_path)


def test_get_library_picks_up_cache_install(monkeypatch, tmp_path):  # noqa: ANN001, ANN201
    """A real install() into the default-cache flow is auto-discovered by get_library()."""
    cache_dir = tmp_path / "cache"
    monkeypatch.setattr(_download, "default_cache_dir", lambda: cache_dir)
    monkeypatch.setattr(_lib, "_library", None)
    monkeypatch.delenv("MAGEMIN_LIB_PATH", raising=False)
    # Force fall-through past the (already-built, on this dev machine) vendored
    # tree, so this actually exercises the cache-dir discovery tier.
    monkeypatch.setattr(_lib, "_candidate_paths", lambda: [])

    _download.install(version="2.0.0")  # default dest -> writes the marker

    lib = _lib.get_library()
    assert isinstance(lib, ctypes.CDLL)
