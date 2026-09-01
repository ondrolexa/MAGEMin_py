"""Tests for MAGEMin(..., solver=...) (magemin_ext's MAGEMin_InitEx solver override).

Added while looking into a user report that suppressing "ilm" doesn't let "ilmm"
(the mp database's other ilmenite-group model) take its place. That turned out to
be a separate bug, unrelated to solver choice -- see tests/test_suppress_phases.py
and magemin_ext.c's MAGEMin_ComputeEquilibriumEx for the actual fix (gv.mbCpx/
mbIlm/mpSp/mpIlm gate whether a near-degenerate pair's pseudocompounds are even
generated, independent of ss_flags). What solver choice IS independently verified
to affect: other near-degenerate phase pairs where both variants are already
reachable -- see test_solver_changes_result_for_near_degenerate_feldspar_case below.
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


def test_solver_changes_result_for_near_degenerate_feldspar_case(require_library: None) -> None:
    """solver has a real, verified effect: a two-feldspar-solvus point flips with solver=0.

    P=10 kbar, T=790 C for this bulk composition (the pseudosection tutorial's
    metapelite bulk) is a near-degenerate point where the feldspar solvus (alkali
    feldspar `afs` vs plagioclase `pl`) resolves differently depending on solver:
    the default (solver=2, hybrid PGE/LP) finds only `pl` stable, while the legacy
    solver (0) finds both `afs` and `pl` stable together.
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

    assert "afs" not in default_result.ph
    assert "afs" in legacy_result.ph
