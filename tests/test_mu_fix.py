"""Tests for MAGEMin(..., mu_fix=...) and compute(..., mu_fix_values=...).

MAGEMin_api.h's MAGEMin_InitMuFix/MAGEMin_NMuFix/MAGEMin_SetMuFix: the chemical potential of
the named oxides is fixed directly, via one fictive "m<oxide>" pure phase per oxide.
"""

import math
import warnings
from collections.abc import Iterator

import pytest

from magemin import MAGEMin, Point, bulk_rocks, multi_point_minimization
from magemin.errors import MAGEMinComputeError, MAGEMinInitError

P, T = 10.0, 1100.0


@pytest.fixture
def mgo_reference(ig: MAGEMin) -> tuple[float, list[float]]:
    """RE46's own MgO chemical potential at (P, T), and RE46 with generous excess MgO."""
    gamma = ig.compute(P, T, bulk_rocks.RE46_IG).gamma[ig.oxide_names.index("MgO")]
    bulk = list(bulk_rocks.RE46_IG.values)
    bulk[ig.oxide_names.index("MgO")] = 60.0
    return gamma, bulk


@pytest.fixture
def ig_mgo(require_library: None) -> Iterator[MAGEMin]:
    with MAGEMin("ig", mu_fix=["MgO"]) as mg:
        yield mg


def _mgo(mg: MAGEMin, values: tuple[float, ...]) -> float:
    return values[mg.oxide_names.index("MgO")]


def test_handle_reports_fixed_oxides(ig: MAGEMin, ig_mgo: MAGEMin) -> None:
    assert ig.mu_fix == ()
    assert ig_mgo.mu_fix == ("MgO",)
    assert ig_mgo._lib.MAGEMin_NMuFix(ig_mgo._handle) == 1
    assert ig_mgo.pure_phase_names[-1] == "mMgO"
    assert ig_mgo.pure_phase_names[:-1] == ig.pure_phase_names


@pytest.mark.parametrize("offset", [0.0, -20.0])
def test_fixed_chemical_potential_is_reached(
    ig_mgo: MAGEMin, mgo_reference: tuple[float, list[float]], offset: float
) -> None:
    gamma, bulk = mgo_reference
    result = ig_mgo.compute(P, T, bulk, "mol", mu_fix_values=[gamma + offset])

    assert result.status == 0
    assert "mMgO" in result.ph
    assert _mgo(ig_mgo, result.gamma) == pytest.approx(gamma + offset, abs=1e-6)


def test_values_are_reapplied_on_every_call(
    ig_mgo: MAGEMin, mgo_reference: tuple[float, list[float]]
) -> None:
    gamma, bulk = mgo_reference
    first = ig_mgo.compute(P, T, bulk, "mol", mu_fix_values=[gamma - 20.0])
    second = ig_mgo.compute(P, T, bulk, "mol", mu_fix_values=[gamma])

    assert _mgo(ig_mgo, first.gamma) == pytest.approx(gamma - 20.0, abs=1e-6)
    assert _mgo(ig_mgo, second.gamma) == pytest.approx(gamma, abs=1e-6)


def test_unreachable_target_warns(
    ig_mgo: MAGEMin, mgo_reference: tuple[float, list[float]]
) -> None:
    """Above what the bulk supports, the fictive phase is not stable and the target is missed."""
    gamma, bulk = mgo_reference
    with pytest.warns(UserWarning, match="MgO was not reached"):
        result = ig_mgo.compute(P, T, bulk, "mol", mu_fix_values=[gamma + 20.0])
    assert "mMgO" not in result.ph


def test_reached_target_does_not_warn(
    ig_mgo: MAGEMin, mgo_reference: tuple[float, list[float]]
) -> None:
    gamma, bulk = mgo_reference
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        ig_mgo.compute(P, T, bulk, "mol", mu_fix_values=[gamma])


def test_fictive_phase_fields_are_sanitized(
    ig_mgo: MAGEMin, mgo_reference: tuple[float, list[float]]
) -> None:
    """MAGEMin leaves the fictive phase's fields uninitialized; they are replaced on copy."""
    gamma, bulk = mgo_reference
    result = ig_mgo.compute(P, T, bulk, "mol", mu_fix_values=[gamma])
    i = result.ph.index("mMgO")
    assert result.ph_type[i] == 0
    assert result.ph_frac[i] == 0.0
    phase = result.pure_phases[result.ph_id[i]]

    one_hot = tuple(1.0 if ox == "MgO" else 0.0 for ox in result.oxides)
    assert phase.comp == phase.comp_wt == phase.comp_apfu == one_hot
    assert all(math.isnan(x) for x in (phase.f, phase.g, phase.rho, phase.entropy, phase.vp))


def test_multi_point_matches_serial(
    ig_mgo: MAGEMin, mgo_reference: tuple[float, list[float]]
) -> None:
    gamma, bulk = mgo_reference
    targets = [gamma, gamma - 10.0, gamma - 20.0]
    serial = [ig_mgo.compute(P, T, bulk, "mol", mu_fix_values=[t]) for t in targets]
    points = [Point(P, T, bulk, "mol", mu_fix_values=[t]) for t in targets]
    parallel = multi_point_minimization("ig", points, mu_fix=["MgO"], max_workers=2)

    for s, p in zip(serial, parallel, strict=True):
        assert sorted(p.ph) == sorted(s.ph)
        assert p.gamma == pytest.approx(s.gamma, abs=1e-6)


@pytest.mark.parametrize(
    ("mu_fix", "match"),
    [
        (["MgO", "MgO"], "more than once"),
        (["XYZ"], "MAGEMin_InitMuFix failed"),
        ([f"X{i}" for i in range(17)], "at most 16"),
        ([1], "oxide names"),
    ],
)
def test_invalid_mu_fix_raises(require_library: None, mu_fix: list, match: str) -> None:
    with pytest.raises(MAGEMinInitError, match=match):
        MAGEMin("ig", mu_fix=mu_fix)


@pytest.mark.parametrize("values", [None, [], [1.0, 2.0]])
def test_mu_fix_values_must_match(
    ig_mgo: MAGEMin, mgo_reference: tuple[float, list[float]], values: list | None
) -> None:
    _, bulk = mgo_reference
    with pytest.raises(MAGEMinComputeError, match="mu_fix_values"):
        ig_mgo.compute(P, T, bulk, "mol", mu_fix_values=values)


def test_mu_fix_values_without_mu_fix_raises(ig: MAGEMin) -> None:
    with pytest.raises(MAGEMinComputeError, match="without mu_fix"):
        ig.compute(P, T, bulk_rocks.RE46_IG, mu_fix_values=[-700.0])


def test_fictive_phase_cannot_be_suppressed(
    ig_mgo: MAGEMin, mgo_reference: tuple[float, list[float]]
) -> None:
    gamma, bulk = mgo_reference
    with pytest.raises(MAGEMinComputeError, match="suppress_phases"):
        ig_mgo.compute(P, T, bulk, "mol", mu_fix_values=[gamma], suppress_phases=["mMgO"])
