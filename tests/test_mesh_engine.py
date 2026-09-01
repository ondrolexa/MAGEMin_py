"""Tests for `magemin._mesh` (the Delaunay-mesh refinement engine backing `Pseudosection`)."""

from magemin import _diagrams, _mesh, bulk_rocks


class _FakeTri:
    """Stand-in for a `scipy.spatial.Delaunay` triangulation -- only `.simplices` is used by
    `_violating_edges`, so tests for it don't need scipy at all."""

    def __init__(self, simplices):
        self.simplices = simplices


# --- _mesh._violating_edges (no numpy/scipy needed) ---


def test_violating_edges_empty_for_clean_boundary() -> None:
    tri = _FakeTri([(0, 1, 2)])
    assemblages = [("a", "b", "c"), ("a", "b"), None]
    assert _mesh._violating_edges(tri, assemblages, refine_all=False) == set()


def test_violating_edges_flags_non_polymorph_swap() -> None:
    tri = _FakeTri([(0, 1, 2)])
    assemblages = [("a", "b", "c"), ("a", "b", "d"), None]
    assert _mesh._violating_edges(tri, assemblages, refine_all=False) == {(0, 1)}


def test_violating_edges_skips_equal_and_none_endpoints() -> None:
    tri = _FakeTri([(0, 1, 2)])
    assemblages = [("a", "b"), ("a", "b"), None]
    assert _mesh._violating_edges(tri, assemblages, refine_all=False) == set()


def test_violating_edges_refine_all_includes_already_clean_boundary() -> None:
    tri = _FakeTri([(0, 1, 2)])
    assemblages = [("a", "b", "c"), ("a", "b"), None]
    assert _mesh._violating_edges(tri, assemblages, refine_all=True) == {(0, 1)}


def test_violating_edges_recognizes_polymorph_swap_as_clean() -> None:
    tri = _FakeTri([(0, 1, 2)])
    assemblages = [("bt", "g", "and"), ("bt", "g", "sill"), None]
    assert _mesh._violating_edges(tri, assemblages, refine_all=False) == set()


# --- _mesh._densify (needs numpy) ---


def test_densify_adds_midpoint_for_violating_edge(require_mesh) -> None:
    import numpy as np

    points = np.array([[0.0, 0.0], [1.0, 0.0]])
    added = _mesh._densify(points, {(0, 1)}, min_distance=1e-6)
    assert added.shape == (1, 2)
    assert list(added[0]) == [0.5, 0.0]


def test_densify_rejects_midpoint_too_close_to_existing_point(require_mesh) -> None:
    import numpy as np

    points = np.array([[0.0, 0.0], [1.0, 0.0], [0.5, 0.0]])
    added = _mesh._densify(points, {(0, 1)}, min_distance=1e-6)
    assert added.shape == (0, 2)


def test_densify_dedupes_two_violations_sharing_a_midpoint(require_mesh) -> None:
    import numpy as np

    points = np.array([[0.0, 0.0], [1.0, 0.0], [0.0, 0.0], [1.0, 0.0]])
    added = _mesh._densify(points, {(0, 1), (2, 3)}, min_distance=1e-6)
    assert added.shape == (1, 2)


# --- _mesh.validate_mesh (no numpy/scipy needed) ---


def test_validate_mesh_true_for_clean_boundary() -> None:
    assemblages = [("a", "b", "c"), ("a", "b")]
    assert _mesh.validate_mesh(assemblages, [(0, 1)]) is True


def test_validate_mesh_false_for_non_polymorph_swap() -> None:
    assemblages = [("a", "b", "c"), ("a", "b", "d")]
    assert _mesh.validate_mesh(assemblages, [(0, 1)]) is False


def test_validate_mesh_skips_none_and_equal_endpoints() -> None:
    assemblages = [("a", "b"), None, ("a", "b")]
    assert _mesh.validate_mesh(assemblages, [(0, 1), (1, 2), (0, 2)]) is True


def test_validate_mesh_true_for_polymorph_swap() -> None:
    assemblages = [("bt", "g", "and"), ("bt", "g", "sill")]
    assert _mesh.validate_mesh(assemblages, [(0, 1)]) is True


# --- _mesh.refine_mesh (real compute) ---


def test_refine_mesh_real_compute_produces_sane_state(require_library, require_mesh) -> None:
    from magemin.core import Point, multi_point_minimization

    def to_point(u: float, v: float) -> Point:
        p = 5 + u * (10 - 5)
        t = 700 + v * (900 - 700)
        return Point(P=p, T=t, bulk=bulk_rocks.KLB1_IG, light=True)

    mapping = _diagrams._AxisMapping(axis1_range=(5, 10), axis2_range=(700, 900), to_point=to_point)
    state = _mesh.refine_mesh(
        "ig",
        mapping,
        initial_resolution=1,
        max_depth=2,
        refine_all=False,
        seed=0,
        lloyd_iterations=1,
        min_distance=1e-6,
        max_workers=None,
        verbose=False,
        solver=2,
        batch_fn=multi_point_minimization,
    )
    assert len(state.points) > 0
    assert len(state.points) == len(state.results) == len(state.assemblages)
    assert isinstance(state.converged, bool)
    assert state.unresolved_boundaries >= 0
    for i, j in state.edges:
        assert i < j
        assert 0 <= i < len(state.points)
        assert 0 <= j < len(state.points)


def test_refine_mesh_missing_scipy_raises_mesh_error(monkeypatch) -> None:
    import sys

    import pytest

    from magemin.core import Point, multi_point_minimization
    from magemin.errors import MAGEMinMeshError

    monkeypatch.setitem(sys.modules, "scipy", None)
    monkeypatch.setitem(sys.modules, "scipy.spatial", None)

    def to_point(u: float, v: float) -> Point:
        return Point(P=5 + u, T=700 + v, bulk=bulk_rocks.KLB1_IG, light=True)

    mapping = _diagrams._AxisMapping(axis1_range=(5, 6), axis2_range=(700, 701), to_point=to_point)
    with pytest.raises(MAGEMinMeshError, match=r"magemin\[mesh\]"):
        _mesh.refine_mesh(
            "ig",
            mapping,
            initial_resolution=0,
            max_depth=1,
            refine_all=False,
            seed=0,
            lloyd_iterations=0,
            min_distance=1e-6,
            max_workers=None,
            verbose=False,
            solver=2,
            batch_fn=multi_point_minimization,
        )
