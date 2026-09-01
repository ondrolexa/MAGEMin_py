"""Tests for sb/gh database family support (magemin_ext's MAGEMin_InitEx)."""

import pytest

from magemin import MAGEMin, bulk_rocks
from magemin.errors import MAGEMinInitError


def test_sb11_database_computes(require_library: None) -> None:
    """The 'sb' (Stixrude & Lithgow-Bertelloni) database family is reachable."""
    with MAGEMin("sb11") as mg:
        result = mg.compute(P=10, T=800, bulk=bulk_rocks.KLB1_SB)
        assert result.status == 0


def test_gh_database_computes(require_library: None) -> None:
    """The 'gh' (MELTS) database family is reachable."""
    with MAGEMin("xMELTS") as mg:
        result = mg.compute(P=10, T=800, bulk=bulk_rocks.BASALT_GH)
        assert result.status == 0


def test_unknown_database_acronym_raises(require_library: None) -> None:
    """An unrecognized database acronym is rejected before reaching the C library."""
    with pytest.raises(MAGEMinInitError):
        MAGEMin("bogus")
