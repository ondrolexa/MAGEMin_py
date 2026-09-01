"""Tests for phase suppression (magemin_ext's MAGEMin_ComputeEquilibriumEx)."""

import pytest

from magemin import MAGEMin, bulk_rocks
from magemin.errors import MAGEMinComputeError

_MP_BULK = [
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


def test_suppress_stable_phase_removes_it(ig: MAGEMin) -> None:
    """Suppressing a phase from the KLB1 P=8,T=800 assemblage removes it."""
    result = ig.compute(P=8, T=800, bulk=bulk_rocks.KLB1_IG, suppress_phases=["spl"])

    assert result.status == 0
    assert "spl" not in result.ph
    assert sum(result.ph_frac) == pytest.approx(1.0, abs=1e-6)


def test_suppressing_ilm_lets_ilmm_take_its_place(require_library: None) -> None:
    """Regression test: mp's near-degenerate ilm/ilmm pair.

    Some vendored databases hard-code a single default variant for a near-
    degenerate phase-model pair (MAGEMin.h's gv.mbCpx/mbIlm/mpSp/mpIlm,
    defaulted to 0 in initialize.c) -- left alone, only that one variant
    ("mp"'s "ilm") ever gets pseudocompounds generated at all, so suppressing
    it via suppress_phases previously left the other variant ("ilmm")
    unreachable even though it was never actually excluded, just never
    generated. MAGEMin_ComputeEquilibriumEx now sets these to 2 ("activate
    both variants") whenever any phase is suppressed, matching
    MAGEMin_C.jl's own point_wise_minimization.
    """
    with MAGEMin("mp") as mg:
        without_suppression = mg.compute(P=6, T=660, bulk=_MP_BULK, sys_in="mol")
        assert "ilm" in without_suppression.ph
        assert "ilmm" not in without_suppression.ph

        suppressing_ilm = mg.compute(
            P=6, T=660, bulk=_MP_BULK, sys_in="mol", suppress_phases=["ilm"]
        )
        assert "ilm" not in suppressing_ilm.ph
        assert "ilmm" in suppressing_ilm.ph


def test_mbcpx_style_flags_do_not_leak_across_calls_on_a_reused_handle(
    require_library: None,
) -> None:
    """The mbCpx/mbIlm/mpSp/mpIlm 'activate both variants' override is per-call only.

    Neither MAGEMin.h's gv.mbCpx/mbIlm/mpSp/mpIlm fields nor reset_gv ever
    clear these back to their defaults -- so a later compute() call that
    doesn't suppress anything must not silently inherit "activate both
    variants" mode left over from an earlier suppressing call on the same
    reused handle (same rationale as buffer being re-applied/cleared every
    call, not just at Init).
    """
    with MAGEMin("mp") as mg:
        mg.compute(P=6, T=660, bulk=_MP_BULK, sys_in="mol", suppress_phases=["ilm"])
        after_suppressing_call = mg.compute(P=6, T=660, bulk=_MP_BULK, sys_in="mol")

    with MAGEMin("mp") as mg:
        fresh_handle = mg.compute(P=6, T=660, bulk=_MP_BULK, sys_in="mol")

    assert after_suppressing_call.ph == fresh_handle.ph


def test_suppress_unknown_name_raises(ig: MAGEMin) -> None:
    """An unrecognized phase name to suppress raises."""
    with pytest.raises(MAGEMinComputeError):
        ig.compute(P=8, T=800, bulk=bulk_rocks.KLB1_IG, suppress_phases=["not_a_phase"])


def test_solution_phase_names_and_pure_phase_names(ig: MAGEMin) -> None:
    """Discoverability properties list known phase names for 'ig'."""
    assert "liq" in ig.solution_phase_names
    assert "opx" in ig.solution_phase_names
    assert len(ig.pure_phase_names) > 0
