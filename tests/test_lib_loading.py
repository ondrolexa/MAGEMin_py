"""Tests for library discovery in magemin._lib."""

import ctypes
from pathlib import Path

import pytest

from magemin import _download, _lib
from magemin.errors import MAGEMinLibraryNotFoundError


def test_library_not_found_raises_actionable_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """A MAGEMIN_LIB_PATH pointing nowhere raises with a helpful message."""
    monkeypatch.setattr(_lib, "_library", None)
    monkeypatch.setenv("MAGEMIN_LIB_PATH", "/nonexistent/libMAGEMin.so")
    with pytest.raises(MAGEMinLibraryNotFoundError) as exc_info:
        _lib.get_library()
    message = str(exc_info.value)
    assert "MAGEMIN_LIB_PATH" in message


def test_get_library_returns_cdll(require_library: None) -> None:
    """A successfully loaded library is a ctypes.CDLL with the 5+7 API functions."""
    lib = _lib.get_library()
    assert isinstance(lib, ctypes.CDLL)
    for name in (
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
    ):
        assert hasattr(lib, name)


def test_cache_candidate_paths_reads_marker(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """_cache_candidate_paths() derives library paths from the cache's current.txt marker."""
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    src_dir = tmp_path / "MAGEMin-main"
    (cache_dir / "current.txt").write_text(str(src_dir) + "\n")
    monkeypatch.setattr(_download, "default_cache_dir", lambda: cache_dir)

    candidates = _lib._cache_candidate_paths()

    assert candidates == [
        src_dir / "libMAGEMin.so",
        src_dir / "libMAGEMin.dylib",
        src_dir / "libMAGEMin.dll",
    ]


def test_cache_candidate_paths_empty_without_marker(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """_cache_candidate_paths() returns nothing when no install has happened yet."""
    monkeypatch.setattr(_download, "default_cache_dir", lambda: tmp_path / "no-such-cache")

    assert _lib._cache_candidate_paths() == []
