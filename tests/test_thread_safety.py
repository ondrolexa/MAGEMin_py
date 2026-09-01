"""Regression test for the multi_point_minimization heap-corruption race.

Before the pthread_rwlock_t fix in magemin_ext.c (guarding the vendored C
library's unsynchronized global EM/DEW/PP endmember-lookup tables -- see
CLAUDE.md's "Project status" section), concurrent MAGEMin_InitEx/
MAGEMin_ComputeEquilibriumEx calls from multiple threads intermittently
corrupted the heap, reproducible with as few as 3 concurrent workers and a
single multi_point_minimization call. A single pytest run can't reliably
catch a ~20% intermittent crash rate on its own -- the real proof is the
repeated-run verification described in CLAUDE.md -- so this is a bounded
regression guard, not the primary evidence the fix works.
"""

import os

from magemin import MAGEMin, Point, bulk_rocks, multi_point_minimization


def test_concurrent_init_and_compute_survives_multiple_rounds(require_library: None) -> None:
    """Many concurrent handles, opened and computed with repeatedly, don't crash."""
    n_points = max(2 * (os.cpu_count() or 4), 8)

    for _round in range(5):
        points = [
            Point(P=2 + i * 0.3, T=700 + i * 5, bulk=bulk_rocks.KLB1_IG) for i in range(n_points)
        ]
        results = multi_point_minimization("ig", points, max_workers=None)
        assert len(results) == n_points
        assert all(result.ph for result in results)


def test_concurrent_handles_for_same_database_agree_with_sequential(
    require_library: None,
) -> None:
    """Concurrent same-database results still match sequential ones (not just crash-free)."""
    points = [
        Point(P=p, T=t, bulk=bulk_rocks.KLB1_IG) for p, t in [(4, 750), (12, 950), (22, 1250)]
    ]

    parallel_results = multi_point_minimization("ig", points, max_workers=None)

    with MAGEMin("ig") as mg:
        sequential_results = [mg.compute(pt.P, pt.T, pt.bulk) for pt in points]

    for parallel, sequential in zip(parallel_results, sequential_results, strict=True):
        assert parallel.ph == sequential.ph
        assert parallel.g == sequential.g
