"""Regression tests for concurrent MAGEMin use across threads.

Through MAGEMin 2.0.2, the vendored C library kept its EM/DEW/PP endmember-lookup
tables as unsynchronized process-wide globals, rebuilt on every handle creation, and
concurrent MAGEMin_InitEx/MAGEMin_ComputeEquilibriumEx calls intermittently corrupted the
heap (reproducible with as few as 3 workers). magemin_ext.c guarded this with a
pthread_rwlock_t; MAGEMin 2.0.6 replaced the tables with an append-only per-(research
group, dataset) registry, so the lock was removed and >= 2.0.6 is required. A single pytest
run can't reliably catch an intermittent crash, so these are bounded regression guards.
"""

import os
import threading

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


def test_concurrent_handles_for_different_databases_match_serial(
    require_library: None,
) -> None:
    """Concurrent handles on different databases give the same results as serial runs.

    Before MAGEMin 2.0.6 the global lookup tables held only one database at a time, so
    this pattern was memory-safe (with the old lock) but not guaranteed correct.
    """
    cases = {
        "mp": bulk_rocks.FPWM_PELITE_MP,
        "ig": bulk_rocks.KLB1_IG,
        "mb": bulk_rocks.SM89_MORB_MB,
        "sb11": bulk_rocks.KLB1_SB,
    }

    def run(database: str, out: dict) -> None:
        with MAGEMin(database) as mg:
            out[database] = [
                (tuple(sorted(r.ph)), round(r.g, 6))
                for r in (
                    mg.compute(P=5 + i, T=700 + 20 * i, bulk=cases[database]) for i in range(4)
                )
            ]

    serial: dict = {}
    for database in cases:
        run(database, serial)

    for _round in range(3):
        concurrent: dict = {}
        threads = [threading.Thread(target=run, args=(db, concurrent)) for db in cases]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert concurrent == serial
