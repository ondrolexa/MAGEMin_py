"""Tests for solvus disambiguation (magemin._solvus / compute(..., name_solvus=True))."""

from magemin import MAGEMin, base_phase_name, bulk_rocks, solvus_name

_WT_BULK = [50.0, 15.0, 10.0, 8.0, 9.0, 0.5, 3.0, 1.5, 0.0, 0.0, 2.0]


def test_name_solvus_false_leaves_names_unchanged(ig: MAGEMin) -> None:
    """With name_solvus=False, solution-phase names are the raw model names."""
    result = ig.compute(P=8, T=800, bulk=bulk_rocks.KLB1_IG, name_solvus=False)
    assert "spl" in result.ph


def test_name_solvus_true_disambiguates_fsp(ig: MAGEMin) -> None:
    """name_solvus=True (the default) renames fsp to its disambiguated mineral name (pl here)."""
    plain = ig.compute(P=10, T=1100, bulk=_WT_BULK, sys_in="wt", name_solvus=False)
    disambiguated = ig.compute(P=10, T=1100, bulk=_WT_BULK, sys_in="wt", name_solvus=True)

    assert plain.ph == ("cpx", "liq", "fsp")
    assert disambiguated.ph == ("cpx", "liq", "pl")
    # Only the ph_type[i] == 1 (solution phase) entries can move; pure-phase
    # entries (none here) and everything else about the result is untouched.
    assert disambiguated.g == plain.g
    assert disambiguated.ph_frac == plain.ph_frac


def test_name_solvus_independent_of_light(ig: MAGEMin) -> None:
    """name_solvus works even when light=True skips building solution_phases."""
    result = ig.compute(P=10, T=1100, bulk=_WT_BULK, sys_in="wt", light=True, name_solvus=True)

    assert result.solution_phases == ()
    assert result.ph == ("cpx", "liq", "pl")


def test_base_phase_name_round_trips_solvus_name() -> None:
    """base_phase_name inverts solvus_name for the default mb_cpx=0 case."""
    assert base_phase_name("ig", "pl") == "fsp"
    assert base_phase_name("ig", "afs") == "fsp"
    assert base_phase_name("ig", "mgt") == "spl"


def test_solvus_name_synthetic_fsp_threshold() -> None:
    """solvus_name disambiguates fsp using comp_variables[1] against the 0.5 threshold."""
    assert solvus_name("ig", "fsp", [0.0, 0.9]) == "afs"
    assert solvus_name("ig", "fsp", [0.0, 0.1]) == "pl"


def test_solvus_name_unrecognized_database_returns_unchanged() -> None:
    """A database with no disambiguation rules returns the name unchanged."""
    assert solvus_name("mtl", "spl", [0.9]) == "spl"
    assert solvus_name("sb11", "spl", [0.9]) == "spl"


def test_solvus_suppress_phases_interop(ig: MAGEMin) -> None:
    """base_phase_name converts a disambiguated name back for use in suppress_phases."""
    disambiguated = ig.compute(P=10, T=1100, bulk=_WT_BULK, sys_in="wt", name_solvus=True)
    assert "pl" in disambiguated.ph

    raw_name = base_phase_name(disambiguated.database, "pl")
    assert raw_name == "fsp"

    suppressed = ig.compute(P=10, T=1100, bulk=_WT_BULK, sys_in="wt", suppress_phases=[raw_name])
    assert "fsp" not in suppressed.ph
    assert suppressed.status == 0
