"""Tests for oxygen-buffer/fixed-activity constraints (magemin_ext's MAGEMin_SetBuffer)."""

import pytest

from magemin import MAGEMin, bulk_rocks
from magemin.errors import MAGEMinComputeError


def test_redox_buffer_cco(ig: MAGEMin) -> None:
    """A redox buffer (cco, offset -1.0) reproduces a captured reference run."""
    result = ig.compute(P=8, T=800, bulk=bulk_rocks.KLB1_IG, buffer="cco", buffer_value=-1.0)

    assert result.status == 0
    assert result.buffer == "cco"
    assert result.buffer_n == pytest.approx(-1.0)
    assert result.g == pytest.approx(-797.7943373560247, abs=1e-3)


def test_activity_buffer_ah2o(ig: MAGEMin) -> None:
    """A fixed-activity buffer (aH2O, activity 0.5) is echoed back correctly."""
    result = ig.compute(P=8, T=800, bulk=bulk_rocks.KLB1_IG, buffer="aH2O", buffer_value=0.5)

    assert result.status == 0
    assert result.buffer == "aH2O"
    assert result.buffer_n == pytest.approx(0.5)


def test_buffer_does_not_leak_across_calls(ig: MAGEMin) -> None:
    """A buffer set on one call does not silently carry over to the next."""
    ig.compute(P=8, T=800, bulk=bulk_rocks.KLB1_IG, buffer="cco", buffer_value=-1.0)
    result = ig.compute(P=8, T=800, bulk=bulk_rocks.KLB1_IG)

    assert result.buffer == "none"
    assert result.buffer_n == 0.0
    assert result.g == pytest.approx(-797.7873866318645, abs=1e-3)


def test_unrecognized_buffer_name_raises(ig: MAGEMin) -> None:
    """An unknown buffer name is rejected before reaching the C library."""
    with pytest.raises(MAGEMinComputeError):
        ig.compute(P=8, T=800, bulk=bulk_rocks.KLB1_IG, buffer="bogus", buffer_value=0.0)


def test_buffer_value_required_with_buffer_raises(ig: MAGEMin) -> None:
    """buffer without buffer_value raises."""
    with pytest.raises(MAGEMinComputeError):
        ig.compute(P=8, T=800, bulk=bulk_rocks.KLB1_IG, buffer="cco")


def test_buffer_value_without_buffer_raises(ig: MAGEMin) -> None:
    """buffer_value without buffer raises."""
    with pytest.raises(MAGEMinComputeError):
        ig.compute(P=8, T=800, bulk=bulk_rocks.KLB1_IG, buffer_value=-1.0)


def test_activity_buffer_out_of_range_raises(ig: MAGEMin) -> None:
    """An activity value outside (0, 1) is rejected before reaching the C library."""
    with pytest.raises(MAGEMinComputeError):
        ig.compute(P=8, T=800, bulk=bulk_rocks.KLB1_IG, buffer="aH2O", buffer_value=1.5)
