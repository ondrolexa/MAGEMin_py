"""Tests for magemin.core -- the MAGEMin handle class."""

import math

import pytest

from magemin import MAGEMin, bulk_rocks
from magemin.errors import BulkCompositionError, MAGEMinClosedHandleError, MAGEMinComputeError

KLB1_IG_OXIDE_NAMES = (
    "SiO2",
    "Al2O3",
    "CaO",
    "MgO",
    "FeO",
    "K2O",
    "Na2O",
    "TiO2",
    "O",
    "Cr2O3",
    "H2O",
)


def test_oxide_names_and_count(ig: MAGEMin) -> None:
    """The 'ig' database's oxide set matches the known fixed order."""
    assert ig.n_oxides == 11
    assert ig.oxide_names == KLB1_IG_OXIDE_NAMES


def test_klb1_p8_t800(ig: MAGEMin) -> None:
    """KLB1 peridotite at P=8 kbar, T=800 C reproduces a captured reference run."""
    result = ig.compute(P=8, T=800, bulk=bulk_rocks.KLB1_IG)

    assert result.status == 0
    assert set(result.ph) == {"opx", "ol", "cpx", "spl"}
    assert result.g == pytest.approx(-797.787387, abs=1e-3)
    # rho is derived from a second Gibbs-energy derivative, which is more sensitive than g or
    # ph_frac to the floating-point rounding path -- and MAGEMin's Makefile builds with
    # -march=native, so that path (and thus rho, at the ~1e-5 relative level) varies by CPU.
    assert result.rho == pytest.approx(3282.556, rel=1e-4)

    fractions = dict(zip(result.ph, result.ph_frac, strict=True))
    assert fractions["opx"] == pytest.approx(0.22805, abs=1e-4)
    assert fractions["ol"] == pytest.approx(0.61182, abs=1e-4)
    assert fractions["cpx"] == pytest.approx(0.13759, abs=1e-4)
    assert fractions["spl"] == pytest.approx(0.02254, abs=1e-4)


def test_custom_wt_composition_p10_t1100(ig: MAGEMin) -> None:
    """A custom wt%-basis composition reproduces a captured reference run."""
    bulk = [50.0, 15.0, 10.0, 8.0, 9.0, 0.5, 3.0, 1.5, 0.0, 0.0, 2.0]
    result = ig.compute(P=10, T=1100, bulk=bulk, sys_in="wt", name_solvus=False)

    assert result.status == 0
    assert set(result.ph) == {"cpx", "liq", "fsp"}
    assert result.g == pytest.approx(-942.671498, abs=1e-3)


def test_bad_sys_in_raises(ig: MAGEMin) -> None:
    """An invalid sys_in value is rejected before reaching the C library."""
    with pytest.raises(MAGEMinComputeError):
        ig.compute(P=8, T=800, bulk=bulk_rocks.KLB1_IG.values, sys_in="bogus")


def test_missing_sys_in_for_plain_sequence_raises(ig: MAGEMin) -> None:
    """A plain-sequence bulk composition requires an explicit sys_in."""
    with pytest.raises(MAGEMinComputeError):
        ig.compute(P=8, T=800, bulk=bulk_rocks.KLB1_IG.values)


def test_bulk_length_mismatch_raises(ig: MAGEMin) -> None:
    """A bulk sequence of the wrong length raises BulkCompositionError."""
    with pytest.raises(BulkCompositionError):
        ig.compute(P=8, T=800, bulk=[1.0, 2.0, 3.0], sys_in="mol")


def test_bulk_rock_wrong_database_raises(ig: MAGEMin) -> None:
    """A BulkRock defined for a different database is rejected."""
    with pytest.raises(BulkCompositionError):
        ig.compute(P=8, T=800, bulk=bulk_rocks.KLB1_MTL)


def test_handle_reuse_across_calls(ig: MAGEMin) -> None:
    """Repeated compute() calls on the same handle give independent results."""
    first = ig.compute(P=8, T=800, bulk=bulk_rocks.KLB1_IG)
    second = ig.compute(P=20, T=1300, bulk=bulk_rocks.KLB1_IG)

    assert first.p == 8
    assert second.p == 20
    assert not math.isclose(first.g, second.g)


def test_context_manager_closes_handle(require_library: None) -> None:
    """Using MAGEMin as a context manager closes the handle on exit."""
    with MAGEMin("ig") as mg:
        pass
    with pytest.raises(MAGEMinClosedHandleError):
        mg.compute(P=8, T=800, bulk=bulk_rocks.KLB1_IG)


def test_close_is_idempotent(require_library: None) -> None:
    """Calling close() more than once does not raise."""
    mg = MAGEMin("ig")
    mg.close()
    mg.close()


def test_predefined_bulk_rocks_smoke(require_library: None) -> None:
    """Every predefined BulkRock computes successfully against its own database."""
    for rocks in bulk_rocks.BULK_ROCKS_BY_DATABASE.values():
        for rock in rocks:
            with MAGEMin(rock.database) as mg:
                result = mg.compute(P=10, T=800, bulk=rock)
                assert result.status == 0
