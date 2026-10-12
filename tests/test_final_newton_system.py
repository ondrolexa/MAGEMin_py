"""Tests for compute(..., store_kkt=True) (MAGEMin_api.h's MAGEMin_SetStoreKKT/
MAGEMin_GetFinalNewtonSystem)."""

import pytest

from magemin import FinalNewtonSystem, MAGEMin, Point, bulk_rocks, multi_point_minimization


def test_not_stored_by_default(ig: MAGEMin) -> None:
    result = ig.compute(P=10, T=1200, bulk=bulk_rocks.KLB1_IG)
    assert result.final_newton_system is None


@pytest.mark.parametrize(
    ("database", "bulk", "T"),
    [("ig", bulk_rocks.KLB1_IG, 1200), ("sb11", bulk_rocks.KLB1_SB, 800)],
)
def test_stored_system_is_consistent(require_library: None, database, bulk, T) -> None:
    with MAGEMin(database) as mg:
        result = mg.compute(P=10, T=T, bulk=bulk, store_kkt=True, name_solvus=False)
    kkt = result.final_newton_system
    assert isinstance(kkt, FinalNewtonSystem)
    assert kkt.nz == kkt.m + kkt.n_y + kkt.n_cc + kkt.n_ph + kkt.n_pp
    assert len(kkt.jacobian) == kkt.nz
    assert all(len(row) == kkt.nz for row in kkt.jacobian)
    assert len(kkt.residual) == kkt.nz
    assert len(kkt.ox_id) == kkt.m
    assert len(kkt.off_y) == kkt.n_ph + 1
    assert kkt.off_y[-1] == kkt.n_y
    assert kkt.off_c[-1] == kkt.n_cc
    assert len(kkt.n) == len(kkt.drop) == kkt.n_ph + kkt.n_pp
    assert kkt.n_ph + kkt.n_pp == result.n_ph
    assert kkt.gamma == pytest.approx(result.gamma)
    assert kkt.g == pytest.approx(result.g)
    names = [mg.solution_phase_names[i] for i in kkt.ss_id]
    names += [mg.pure_phase_names[i] for i in kkt.pp_id]
    assert sorted(names) == sorted(result.ph)


def test_setting_does_not_leak_between_calls(ig: MAGEMin) -> None:
    """Like buffer/suppress_phases, store_kkt is re-applied on every call of a reused handle."""
    assert ig.compute(10, 1200, bulk_rocks.KLB1_IG, store_kkt=True).final_newton_system
    assert ig.compute(10, 1200, bulk_rocks.KLB1_IG).final_newton_system is None


def test_none_without_final_newton_step(require_library: None) -> None:
    with MAGEMin("ig", final_newton_step=False) as mg:
        result = mg.compute(P=10, T=1200, bulk=bulk_rocks.KLB1_IG, store_kkt=True)
    assert result.status == 0
    assert result.final_newton_system is None


def test_point_store_kkt(require_library: None) -> None:
    with_kkt, without = multi_point_minimization(
        "ig",
        [Point(10, 1200, bulk_rocks.KLB1_IG, store_kkt=True), Point(10, 1200, bulk_rocks.KLB1_IG)],
        max_workers=1,
    )
    assert with_kkt.final_newton_system is not None
    assert without.final_newton_system is None


def test_jacobian_orientation(ig: MAGEMin) -> None:
    """`jacobian[row][col]` is equation `row`, unknown `col` (C stores it column-major).

    Per `fn_system` in MAGEMin's PGE_function.c, phase q's driving-force equation depends on
    oxide j's chemical potential by -c_qj, and oxide j's mass balance on phase q's amount by
    +c_qj -- so those two entries are exact negatives, which a transposed copy would break.
    """
    kkt = ig.compute(10, 1200, bulk_rocks.KLB1_IG, store_kkt=True).final_newton_system
    assert kkt is not None
    driving_force_row = kkt.n_y + kkt.n_cc  # first phase's driving-force equation
    mass_balance_row = driving_force_row + kkt.n_ph + kkt.n_pp
    amount_col = kkt.m + kkt.n_y + kkt.n_cc  # first phase's amount
    compositions = [kkt.jacobian[mass_balance_row + j][amount_col] for j in range(kkt.m)]
    assert any(compositions)
    for j, c in enumerate(compositions):
        assert kkt.jacobian[driving_force_row][j] == pytest.approx(-c)
