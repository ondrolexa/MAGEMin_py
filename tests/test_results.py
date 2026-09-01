"""Tests for magemin.results -- the copied-out output dataclasses."""

from magemin import MAGEMin, bulk_rocks


def test_equilibrium_result_phase_arrays_are_consistent(ig: MAGEMin) -> None:
    """Per-phase array lengths agree with the phase counts, and phases are copied."""
    result = ig.compute(P=8, T=800, bulk=bulk_rocks.KLB1_IG)

    assert len(result.ph) == result.n_ph
    assert len(result.ph_frac) == result.n_ph
    assert len(result.solution_phases) == result.n_ss
    assert len(result.pure_phases) == result.n_pp
    assert len(result.metastable_phases) == result.n_mss

    for phase in result.solution_phases:
        assert len(phase.comp) == phase.n_ox
        assert len(phase.em_names) == phase.n_em
        assert len(phase.em_frac) == phase.n_em


def test_result_survives_handle_reuse(ig: MAGEMin) -> None:
    """A previously returned result is unaffected by a later compute() call."""
    first = ig.compute(P=8, T=800, bulk=bulk_rocks.KLB1_IG)
    first_ph = first.ph
    first_g = first.g

    ig.compute(P=20, T=1300, bulk=bulk_rocks.KLB1_IG)

    assert first.ph == first_ph
    assert first.g == first_g


def test_str_summary_contains_key_fields(ig: MAGEMin) -> None:
    """The human-readable summary reports Celsius temperature and phase table."""
    result = ig.compute(P=8, T=800, bulk=bulk_rocks.KLB1_IG)
    summary = str(result)
    assert "800" in summary
    assert "opx" in summary
