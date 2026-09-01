"""Offline tests for the adaptive quadtree refinement engine (`magemin._diagrams`).

No C library / network involved -- `refine()` is exercised against a fake
`batch_fn` standing in for `multi_point_minimization`.
"""

from types import SimpleNamespace

import pytest

from magemin import _diagrams
from magemin._diagrams import _resolve_bulk_for_interpolation
from magemin.errors import BulkCompositionError, MAGEMinComputeError


def test_subdivide_covers_parent_corners_edges_and_center() -> None:
    parent = _diagrams._LatticeCell(0, 0, 4, 4, 0)
    children = parent.subdivide()
    assert all(child.depth == 1 for child in children)

    all_corners = {corner for child in children for corner in child.corners()}
    expected = {
        (0, 0),
        (2, 0),
        (4, 0),
        (0, 2),
        (2, 2),
        (4, 2),
        (0, 4),
        (2, 4),
        (4, 4),
    }
    assert all_corners == expected


def test_subdivide_is_exact_no_gaps_or_overlaps() -> None:
    parent = _diagrams._LatticeCell(0, 0, 8, 8, 0)
    children = parent.subdivide()
    areas = [(c.i1 - c.i0) * (c.j1 - c.j0) for c in children]
    assert sum(areas) == (parent.i1 - parent.i0) * (parent.j1 - parent.j0)
    assert len(set(children)) == 4


def _make_mapping(axis1_range=(0.0, 1.0), axis2_range=(0.0, 1.0)):
    def to_point(u, v):
        return SimpleNamespace(P=u, T=v)

    return _diagrams._AxisMapping(
        axis1_range=axis1_range, axis2_range=axis2_range, to_point=to_point
    )


def _boundary_batch_fn(database, points, *, max_workers=None, verbose=False, solver=2):
    """Fake multi_point_minimization: phase boundary at P == 0.5."""
    return [SimpleNamespace(ph=("B",) if point.P >= 0.5 else ("A",)) for point in points]


def test_refine_resolves_uniform_region_without_splitting() -> None:
    calls = []

    def counting_batch_fn(database, points, *, max_workers=None, verbose=False, solver=2):
        calls.append(list(points))
        return _boundary_batch_fn(database, points, max_workers=max_workers, verbose=verbose)

    mapping = _make_mapping()
    leaves, cache = _diagrams.refine(
        "ig",
        mapping,
        initial_resolution=1,
        max_depth=3,
        max_workers=None,
        verbose=False,
        solver=2,
        batch_fn=counting_batch_fn,
    )

    # Right half (P in [0.5, 1]) is uniformly "B" and must resolve at depth 1
    # (the initial grid) without ever being subdivided.
    right_leaves = [leaf for leaf in leaves if leaf.corners[0][0] >= 0.5]
    assert right_leaves
    assert all(leaf.resolved and leaf.assemblage == ("B",) for leaf in right_leaves)
    assert all(leaf.depth == 1 for leaf in right_leaves)


def test_refine_splits_across_boundary_and_terminates() -> None:
    mapping = _make_mapping()
    leaves, cache = _diagrams.refine(
        "ig",
        mapping,
        initial_resolution=1,
        max_depth=3,
        max_workers=None,
        verbose=False,
        solver=2,
        batch_fn=_boundary_batch_fn,
    )

    assert any(leaf.resolved and leaf.assemblage == ("A",) for leaf in leaves)
    assert any(leaf.resolved and leaf.assemblage == ("B",) for leaf in leaves)
    # No leaf ever exceeds max_depth.
    assert all(leaf.depth <= 3 for leaf in leaves)
    # Any unresolved leaf must be exactly at max_depth (the only way to emit one).
    assert all(leaf.depth == 3 for leaf in leaves if not leaf.resolved)


def test_refine_terminal_case_never_resolves_stops_at_max_depth() -> None:
    def never_agrees_batch_fn(database, points, *, max_workers=None, verbose=False, solver=2):
        # Every lattice point gets a unique assemblage, so no cell's 4
        # corners can ever agree -- forces recursion to run to max_depth.
        return [SimpleNamespace(ph=(f"{point.P:.6f}-{point.T:.6f}",)) for point in points]

    mapping = _make_mapping()
    max_depth = 2
    leaves, cache = _diagrams.refine(
        "ig",
        mapping,
        initial_resolution=1,
        max_depth=max_depth,
        max_workers=None,
        verbose=False,
        solver=2,
        batch_fn=never_agrees_batch_fn,
    )

    assert leaves
    assert all(not leaf.resolved for leaf in leaves)
    assert all(leaf.depth == max_depth for leaf in leaves)


def test_refine_never_requests_a_lattice_point_twice() -> None:
    requested: list[tuple[int, int]] = []

    def recording_batch_fn(database, points, *, max_workers=None, verbose=False, solver=2):
        results = _boundary_batch_fn(database, points, max_workers=max_workers, verbose=verbose)
        for point, _result in zip(points, results, strict=True):
            requested.append((point.P, point.T))
        return results

    mapping = _make_mapping()
    _diagrams.refine(
        "ig",
        mapping,
        initial_resolution=1,
        max_depth=4,
        max_workers=None,
        verbose=False,
        solver=2,
        batch_fn=recording_batch_fn,
    )

    assert len(requested) == len(set(requested))


def test_refine_seeded_cache_skips_already_known_points() -> None:
    mapping = _make_mapping()
    # A full run at max_depth=2, whose cache fully covers that same lattice.
    _leaves, cache = _diagrams.refine(
        "ig",
        mapping,
        initial_resolution=1,
        max_depth=2,
        max_workers=None,
        verbose=False,
        solver=2,
        batch_fn=_boundary_batch_fn,
    )

    def unreachable_batch_fn(database, points, *, max_workers=None, verbose=False, solver=2):
        raise AssertionError("batch_fn should not be called -- initial_cache already covers this")

    # Re-running refine() over the *same* lattice with that cache fully seeded must
    # never call batch_fn at all -- every corner it would need is already known.
    _diagrams.refine(
        "ig",
        mapping,
        initial_resolution=1,
        max_depth=2,
        max_workers=None,
        verbose=False,
        solver=2,
        batch_fn=unreachable_batch_fn,
        initial_cache=cache,
    )


def test_refine_seeded_cache_is_not_mutated_by_the_caller() -> None:
    mapping = _make_mapping()
    seed = {(0, 0): SimpleNamespace(ph=("A",))}
    original_keys = set(seed.keys())

    _diagrams.refine(
        "ig",
        mapping,
        initial_resolution=1,
        max_depth=1,
        max_workers=None,
        verbose=False,
        solver=2,
        batch_fn=_boundary_batch_fn,
        initial_cache=seed,
    )

    assert set(seed.keys()) == original_keys


def test_refine_rejects_initial_resolution_above_max_depth() -> None:
    mapping = _make_mapping()
    with pytest.raises(ValueError, match="initial_resolution"):
        _diagrams.refine(
            "ig",
            mapping,
            initial_resolution=4,
            max_depth=2,
            max_workers=None,
            verbose=False,
            solver=2,
            batch_fn=_boundary_batch_fn,
        )


def test_interpolate_bulk_at_endpoints_and_midpoint() -> None:
    a = (0.0, 10.0, 2.0)
    b = (2.0, 20.0, 2.0)
    assert _diagrams.interpolate_bulk(a, b, 0.0) == a
    assert _diagrams.interpolate_bulk(a, b, 1.0) == b
    assert _diagrams.interpolate_bulk(a, b, 0.5) == (1.0, 15.0, 2.0)


def test_resolve_bulk_for_interpolation_plain_sequences() -> None:
    values_a, values_b, sys_in = _resolve_bulk_for_interpolation([1.0, 2.0], [3.0, 4.0], "wt")
    assert values_a == (1.0, 2.0)
    assert values_b == (3.0, 4.0)
    assert sys_in == "wt"


def test_resolve_bulk_for_interpolation_requires_sys_in_for_plain_sequences() -> None:
    with pytest.raises(MAGEMinComputeError, match="sys_in"):
        _resolve_bulk_for_interpolation([1.0, 2.0], [3.0, 4.0], None)


def test_resolve_bulk_for_interpolation_rejects_length_mismatch() -> None:
    with pytest.raises(BulkCompositionError):
        _resolve_bulk_for_interpolation([1.0, 2.0], [3.0, 4.0, 5.0], "wt")


def test_resolve_bulk_for_interpolation_bulkrock_pair() -> None:
    from magemin.bulk_rocks import KLB1_IG, RE46_IG

    values_a, values_b, sys_in = _resolve_bulk_for_interpolation(KLB1_IG, RE46_IG, None)
    assert values_a == KLB1_IG.values
    assert values_b == RE46_IG.values
    assert sys_in == KLB1_IG.sys_in == RE46_IG.sys_in


def test_resolve_bulk_for_interpolation_rejects_mismatched_bulkrocks() -> None:
    from magemin.bulk_rocks import FPWM_PELITE_MP, KLB1_IG

    with pytest.raises(BulkCompositionError):
        _resolve_bulk_for_interpolation(KLB1_IG, FPWM_PELITE_MP, None)
