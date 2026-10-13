"""Tests for MAGEMin(..., seismic_scheme=..., seismic_weight=...) (MAGEMin_SetSeismicScheme)."""

import pytest

from magemin import MAGEMin, Point, bulk_rocks, multi_point_minimization
from magemin.errors import MAGEMinInitError

P, T = 10.0, 900.0


def _compute(scheme: str = "VRH", weight: float = 0.5):
    with MAGEMin("ig", seismic_scheme=scheme, seismic_weight=weight) as mg:
        return mg.compute(P, T, bulk_rocks.RE46_IG)


def test_defaults(ig: MAGEMin) -> None:
    assert ig.seismic_scheme == "VRH"
    assert ig.seismic_weight == 0.5
    default = ig.compute(P, T, bulk_rocks.RE46_IG)
    assert _compute("VRH", 0.5).vp == default.vp


def test_vrh_weight_moves_from_reuss_to_voigt(require_library: None) -> None:
    """Weight 0 is the soft (Reuss) bound, 1 the stiff (Voigt) bound."""
    reuss, vrh, voigt = (_compute("VRH", w) for w in (0.0, 0.5, 1.0))
    assert reuss.vp < vrh.vp < voigt.vp
    assert reuss.shear_mod < vrh.shear_mod < voigt.shear_mod
    # Only the averaging changes, not the equilibrium itself.
    assert reuss.ph == vrh.ph == voigt.ph
    assert reuss.g == pytest.approx(voigt.g)


def test_hashin_shtrikman_differs_from_vrh(require_library: None) -> None:
    hs_soft, hs_stiff = _compute("HS", 0.0), _compute("HS", 1.0)
    assert hs_soft.vp < hs_stiff.vp
    assert _compute("HS", 0.5).vp != _compute("VRH", 0.5).vp


@pytest.mark.parametrize(
    ("scheme", "weight", "match"),
    [
        ("bogus", 0.5, "seismic_scheme"),
        ("VRH", -0.1, "seismic_weight"),
        ("HS", 1.5, "seismic_weight"),
    ],
)
def test_invalid_settings_raise(
    require_library: None, scheme: str, weight: float, match: str
) -> None:
    with pytest.raises(MAGEMinInitError, match=match):
        MAGEMin("ig", seismic_scheme=scheme, seismic_weight=weight)


def test_multi_point_passes_settings_through(require_library: None) -> None:
    [result] = multi_point_minimization(
        "ig", [Point(P, T, bulk_rocks.RE46_IG)], seismic_scheme="HS", seismic_weight=1.0
    )
    assert result.vp == pytest.approx(_compute("HS", 1.0).vp)
