"""Tests for MAGEMin(..., solver=...) (magemin_ext's MAGEMin_InitEx solver override).

Added while looking into a user report that suppressing "ilm" doesn't let "ilmm"
(the mp database's other ilmenite-group model) take its place. That turned out to
be a separate bug, unrelated to solver choice -- see tests/test_suppress_phases.py
and magemin_ext.c's MAGEMin_ComputeEquilibriumEx for the actual fix (gv.mbCpx/
mbIlm/mpSp/mpIlm gate whether a near-degenerate pair's pseudocompounds are even
generated, independent of ss_flags). Through MAGEMin 2.0.2, solver=0 also resolved a
near-degenerate feldspar solvus point (afs+pl) that solver=2 missed; since 2.0.6 the
solvers agree there and across a full mp P-T grid, so the test below only checks that
both solvers run and converge to the same equilibrium.
"""

import pytest

from magemin import MAGEMin, bulk_rocks
from magemin.errors import MAGEMinInitError


def test_invalid_solver_raises(require_library: None) -> None:
    """A solver value outside 0-3 is rejected before reaching the C library."""
    with pytest.raises(MAGEMinInitError):
        MAGEMin("ig", solver=4)


def test_default_solver_is_two(ig: MAGEMin) -> None:
    """Omitting solver matches MAGEMin's own library default (2)."""
    assert ig.solver == 2


def test_solver_property_reflects_requested_value(require_library: None) -> None:
    with MAGEMin("ig", solver=0) as mg:
        assert mg.solver == 0


def test_sb_database_accepts_any_solver_request(require_library: None) -> None:
    """sb/gh databases silently force solver=0 upstream; requesting otherwise still works."""
    with MAGEMin("sb11", solver=2) as mg:
        result = mg.compute(P=10, T=800, bulk=bulk_rocks.KLB1_SB)
        assert result.status == 0


def test_legacy_and_default_solvers_agree(require_library: None) -> None:
    """solver=0 (legacy) and solver=2 (default) both converge to the same equilibrium.

    P=10 kbar, T=790 C for the pseudosection tutorial's metapelite bulk was, through
    MAGEMin 2.0.2, a point where solver=0 found afs+pl but solver=2 only pl.
    """
    bulk = [
        61.5428,
        10.7347,
        1.2660,
        3.2294,
        5.3527,
        2.1983,
        1.5273,
        0.6297,
        0.1500,
        0.1001,
        13.2691,
    ]

    with MAGEMin("mp", solver=2) as mg:
        default_result = mg.compute(P=10, T=790, bulk=bulk, sys_in="mol", name_solvus=True)
    with MAGEMin("mp", solver=0) as mg:
        legacy_result = mg.compute(P=10, T=790, bulk=bulk, sys_in="mol", name_solvus=True)

    assert default_result.status == 0
    assert legacy_result.status == 0
    assert set(default_result.ph) == set(legacy_result.ph)
    assert default_result.g == pytest.approx(legacy_result.g, abs=1e-4)
