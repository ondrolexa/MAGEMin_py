"""Tests for magemin.core.multi_point_minimization."""

from magemin import MAGEMin, Point, bulk_rocks, multi_point_minimization


def test_multi_point_matches_sequential(require_library: None) -> None:
    """Parallel multi-point results match sequential single-point calls, in order."""
    points = [
        Point(P=p, T=t, bulk=bulk_rocks.KLB1_IG)
        for p, t in [(5, 700), (10, 900), (15, 1100), (20, 1300), (25, 1400), (30, 1500)]
    ]

    parallel_results = multi_point_minimization("ig", points, max_workers=3)

    with MAGEMin("ig") as mg:
        sequential_results = [mg.compute(pt.P, pt.T, pt.bulk) for pt in points]

    assert len(parallel_results) == len(points)
    for parallel, sequential in zip(parallel_results, sequential_results, strict=True):
        assert parallel.p == sequential.p
        assert parallel.t == sequential.t
        assert parallel.g == sequential.g
        assert parallel.ph == sequential.ph


def test_multi_point_empty_input(require_library: None) -> None:
    """An empty points list returns an empty result list."""
    assert multi_point_minimization("ig", []) == []
