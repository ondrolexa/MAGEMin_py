"""Tests for compute(..., light=True) (reduced-output mode)."""

import pytest

from magemin import MAGEMin, bulk_rocks


def test_light_mode_omits_nested_phases(ig: MAGEMin) -> None:
    """light=True leaves nested phase tuples empty but keeps summary fields."""
    full = ig.compute(P=8, T=800, bulk=bulk_rocks.KLB1_IG)
    light = ig.compute(P=8, T=800, bulk=bulk_rocks.KLB1_IG, light=True)

    assert light.solution_phases == ()
    assert light.metastable_phases == ()
    assert light.pure_phases == ()
    assert full.solution_phases != ()

    assert light.ph == full.ph
    assert light.ph_frac == full.ph_frac
    assert light.g == pytest.approx(full.g)
    assert light.n_ss == full.n_ss
