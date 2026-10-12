"""Tests for MAGEMin(..., optimizer=..., final_newton_step=...).

MAGEMin_api.h's MAGEMin_SetSSSolver (exposed as `optimizer`, after MAGEMin_C.jl's own
keyword) and MAGEMin_SetFinalNewtonStep.
"""

import pytest

from magemin import MAGEMin, PhaseDiagram, Point, bulk_rocks, multi_point_minimization
from magemin.errors import MAGEMinInitError

# The MAGEMin README's own nullspace-optimizer example: a CMAS + SiO2 system, below FMAS.
_CMAS = {"SiO2": 45.0, "Al2O3": 10.0, "CaO": 8.0, "MgO": 35.0}


def test_defaults(ig: MAGEMin) -> None:
    assert ig.optimizer == 0
    assert ig.final_newton_step is True


@pytest.mark.parametrize("optimizer", [-1, 3])
def test_invalid_optimizer_raises(require_library: None, optimizer: int) -> None:
    with pytest.raises(MAGEMinInitError, match="optimizer"):
        MAGEMin("ig", optimizer=optimizer)


def test_c_api_return_codes(require_library: None) -> None:
    """MAGEMin_SetSSSolver/SetFinalNewtonStep: 0 applied, -1 invalid."""
    with MAGEMin("ig") as mg:
        assert [mg._lib.MAGEMin_SetSSSolver(mg._handle, v) for v in (0, 1, 2, 3)] == [0, 0, 0, -1]
        assert [mg._lib.MAGEMin_SetFinalNewtonStep(mg._handle, v) for v in (1, 0, 2)] == [0, 0, -1]


@pytest.mark.parametrize("optimizer", [1, 2])
def test_optimizer_agrees_with_nlopt(require_library: None, optimizer: int) -> None:
    """On an ordinary bulk, the nullspace optimizer reaches NLopt's equilibrium."""
    with MAGEMin("ig", solver=0) as mg:
        reference = mg.compute(P=10, T=1200, bulk=bulk_rocks.KLB1_IG)
    with MAGEMin("ig", solver=0, optimizer=optimizer) as mg:
        assert mg.optimizer == optimizer
        result = mg.compute(P=10, T=1200, bulk=bulk_rocks.KLB1_IG)
    assert result.status == 0
    assert sorted(result.ph) == sorted(reference.ph)
    assert result.g == pytest.approx(reference.g, abs=1e-3)


def test_optimizer_handles_sub_fmas_system(require_library: None) -> None:
    """With the nullspace optimizer, exact-zero oxides (even FeO) are dropped from the system."""
    with MAGEMin("ig", solver=0, optimizer=1) as mg:
        bulk = [_CMAS.get(ox, 0.0) for ox in mg.oxide_names]
        result = mg.compute(P=10, T=1200, bulk=bulk, sys_in="mol")
    assert result.status == 0
    assert result.ph


def test_final_newton_step_off_still_converges(require_library: None) -> None:
    with MAGEMin("ig", final_newton_step=False) as mg:
        assert mg.final_newton_step is False
        result = mg.compute(P=10, T=1200, bulk=bulk_rocks.KLB1_IG)
    with MAGEMin("ig") as mg:
        reference = mg.compute(P=10, T=1200, bulk=bulk_rocks.KLB1_IG)
    assert result.status == 0
    assert sorted(result.ph) == sorted(reference.ph)
    assert result.g == pytest.approx(reference.g, abs=1e-3)


def test_multi_point_minimization_threads_options(require_library: None) -> None:
    with MAGEMin("ig", solver=0, optimizer=1) as mg:
        bulk = [_CMAS.get(ox, 0.0) for ox in mg.oxide_names]
        expected = mg.compute(P=10, T=1200, bulk=bulk, sys_in="mol")
    (result,) = multi_point_minimization(
        "ig", [Point(10, 1200, bulk, "mol")], solver=0, optimizer=1, max_workers=1
    )
    assert result.ph == expected.ph
    assert result.g == expected.g


def test_phase_diagram_keeps_options_across_refine(require_library: None) -> None:
    diagram = PhaseDiagram.pt(
        "ig",
        P=(10.0, 20.0),
        T=(1100.0, 1300.0),
        bulk=bulk_rocks.KLB1_IG,
        initial_resolution=1,
        solver=0,
        optimizer=1,
        final_newton_step=False,
    )
    refined = diagram.refine()
    for d in (diagram, refined):
        assert (d.optimizer, d.final_newton_step) == (1, False)
