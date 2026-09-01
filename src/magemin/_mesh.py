"""Adaptive Delaunay-mesh refinement engine backing `magemin.pseudosection`.

Ported from the sibling `pseudo_graph` project's `mesh.py`: a perturbed hexagonal lattice over
normalized `[0,1]^2` is triangulated with `scipy.spatial.Delaunay`, then repeatedly densified
wherever two triangle-adjacent points disagree in a way that isn't a legitimate boundary
(`magemin._diagrams._is_clean_boundary` -- the same clean/polymorph-swap predicate
`PhaseDiagram.validate()` already uses, reused here rather than re-derived). Refinement is done in
normalized coordinates specifically so a skewed axis window never distorts triangle shape;
`magemin._diagrams._AxisMapping` (already used by `PhaseDiagram.pt/px/tx`) converts back to
physical coordinates.

Unlike `magemin._diagrams.refine` (the quadtree engine), this module has no persistent point
cache keyed by exact coordinates -- every call works on a plain, growing point list, mutated
locally within `refine_mesh` and never exposed outside it. `magemin.pseudosection.Pseudosection`
stores only the frozen `_MeshState` snapshot this returns; continuing refinement
(`Pseudosection.refine()`) re-derives normalized coordinates from the previous snapshot's physical
points and starts a fresh round loop from there -- floating-point round-trip is harmless here,
since Delaunay only needs coordinates, not exact cache-key equality.

`numpy`/`scipy` are only imported lazily, inside each function that needs them (guarded once, in
`refine_mesh`, which raises `MAGEMinMeshError` up front if they're missing before any of its
helpers run), so importing this module (and therefore `magemin` itself) never requires the
optional `mesh` extra -- only actually building or refining a `Pseudosection` does.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from magemin._diagrams import _is_clean_boundary
from magemin.errors import MAGEMinMeshError

if TYPE_CHECKING:
    import numpy as np
    from scipy.spatial import Delaunay

    from magemin._diagrams import _AxisMapping
    from magemin.results import EquilibriumResult

_Assemblage = tuple[str, ...] | None


@dataclass(frozen=True, slots=True)
class _MeshState:
    """Final snapshot of a refined Delaunay mesh, in physical axis coordinates.

    Attributes:
        points: Physical `(axis1, axis2)` coordinates, in mesh-index order.
        results: Computed result per point (`None` where the computation failed --
            non-zero status or no stable phases), same order/length as `points`.
        assemblages: Sorted stable-phase-name tuple per point, `None` wherever `results` is.
        edges: Deduplicated `(i, j)` index pairs, `i < j`, for every Delaunay-edge-adjacent
            point pair in the final triangulation.
        converged: Whether every edge was a clean boundary (or shared/omitted an endpoint) by
            the time refinement stopped.
        unresolved_boundaries: Count of edges failing the clean-boundary check when refinement
            stopped (`0` if `converged`).
    """

    points: tuple[tuple[float, float], ...]
    results: tuple[EquilibriumResult | None, ...]
    assemblages: tuple[_Assemblage, ...]
    edges: tuple[tuple[int, int], ...]
    converged: bool
    unresolved_boundaries: int


def _seed_hex_lattice(resolution: int, seed: int) -> np.ndarray:
    """Build a perturbed hexagonal point lattice over normalized `[0,1]^2`.

    Domain-edge points stay exactly on `u`/`v` in `{0, 1}` (no jitter) so the mesh always
    samples the requested physical boundary; only interior points are randomly perturbed.
    """
    import numpy as np

    spacing = 1.0 / (2**resolution)
    x = np.arange(0.0, 1.0 + spacing / 2, spacing)
    y = np.arange(0.0, 1.0 + spacing / 2, spacing * np.sqrt(3) / 2)
    xx, yy = np.meshgrid(x, y)
    for i in range(len(y)):
        if i % 2 == 1:
            xx[i, :] += spacing / 2
    points = np.column_stack([xx.ravel(), yy.ravel()])
    points = np.clip(points, 0.0, 1.0)

    rng = np.random.default_rng(seed)
    jitter = rng.uniform(-spacing * 0.15, spacing * 0.15, size=points.shape)
    interior = (points[:, 0] > 0) & (points[:, 0] < 1) & (points[:, 1] > 0) & (points[:, 1] < 1)
    points[interior] += jitter[interior]
    return np.clip(points, 0.0, 1.0)


def _lloyd_relax(points: np.ndarray, iterations: int) -> np.ndarray:
    """Relax `points` toward their Voronoi-cell centroids, `iterations` times.

    Only bounded Voronoi cells (not touching the unbounded region, i.e. not an edge/corner
    point) are moved.
    """
    import numpy as np
    from scipy.spatial import Voronoi

    for _ in range(iterations):
        vor = Voronoi(points)
        new_points = points.copy()
        for i, region_idx in enumerate(vor.point_region):
            region = vor.regions[region_idx]
            if region and -1 not in region:
                centroid = vor.vertices[region].mean(axis=0)
                new_points[i] = centroid
        points = np.clip(new_points, 0.0, 1.0)
    return points


def _violating_edges(
    tri: Delaunay, assemblages: Sequence[_Assemblage], refine_all: bool
) -> set[tuple[int, int]]:
    """Delaunay-triangle edges needing densification.

    By default, only edges that are neither a clean single-phase boundary nor a polymorphic
    swap. With `refine_all`, every edge whose endpoints disagree at all -- including
    already-legitimate boundaries -- so densification continues along every boundary.
    """
    violations: set[tuple[int, int]] = set()
    for simplex in tri.simplices:
        for k in range(3):
            i, j = int(simplex[k]), int(simplex[(k + 1) % 3])
            if i > j:
                i, j = j, i
            a, b = assemblages[i], assemblages[j]
            if a is None or b is None or a == b:
                continue
            if refine_all or not _is_clean_boundary(a, b):
                violations.add((i, j))
    return violations


def _densify(
    points: np.ndarray, violations: set[tuple[int, int]], min_distance: float
) -> np.ndarray:
    """Return one midpoint per violating edge.

    Rejects any midpoint within `min_distance` of an existing or already-accepted-this-round
    point.
    """
    import numpy as np

    new_points: list[np.ndarray] = []
    for i, j in violations:
        midpoint = (points[i] + points[j]) / 2
        pool = points if not new_points else np.vstack([points, new_points])
        if np.min(np.linalg.norm(pool - midpoint, axis=1)) > min_distance:
            new_points.append(midpoint)
    return np.array(new_points) if new_points else np.empty((0, 2))


def refine_mesh(
    database: str,
    mapping: _AxisMapping,
    *,
    initial_resolution: int,
    max_depth: int,
    refine_all: bool,
    seed: int,
    lloyd_iterations: int,
    min_distance: float,
    max_workers: int | None,
    verbose: bool,
    solver: int,
    batch_fn: Callable[..., list[EquilibriumResult]],
    initial_points: Sequence[tuple[float, float]] | None = None,
    initial_results: Sequence[EquilibriumResult | None] | None = None,
) -> _MeshState:
    """Build (or continue) an adaptive Delaunay mesh until every boundary is resolved.

    Args:
        database: Database acronym, passed through to `batch_fn`.
        mapping: Normalized-to-physical axis mapping for this pseudosection.
        initial_resolution: Starting hex-lattice density (ignored when `initial_points` is
            given). Only meaningful for a fresh mesh.
        max_depth: Maximum number of densification rounds.
        refine_all: If True, keep densifying already-clean boundaries too (uniformly denser
            sampling), instead of stopping once every boundary is recognized as clean.
        seed: RNG seed for the initial lattice's jitter (ignored when `initial_points` is
            given).
        lloyd_iterations: Voronoi-relaxation passes on the initial lattice (ignored when
            `initial_points` is given).
        min_distance: Minimum allowed distance (normalized `[0,1]^2` units) between any two
            points -- a new midpoint closer than this to an existing point is rejected.
        max_workers: Passed through to `batch_fn`.
        verbose: Passed through to `batch_fn`.
        solver: Passed through to `batch_fn`.
        batch_fn: Callable with the same signature as
            `magemin.core.multi_point_minimization`, injectable for testing.
        initial_points: Already-known physical `(axis1, axis2)` points to continue from (e.g.
            `Pseudosection.refine()` continuing an existing mesh), instead of seeding a fresh
            lattice.
        initial_results: Already-known results for `initial_points`, same order/length.
            `None` entries (never computed, or a previous compute failure) are retried.

    Returns:
        The refined mesh's final snapshot.

    Raises:
        MAGEMinMeshError: If `numpy`/`scipy` are not installed.
    """
    try:
        import numpy as np
        from scipy.spatial import Delaunay
    except ImportError as exc:
        raise MAGEMinMeshError(
            "numpy/scipy are required for Pseudosection; install them with "
            "`pip install magemin[mesh]`"
        ) from exc

    if initial_points is None:
        points = _seed_hex_lattice(initial_resolution, seed)
        if lloyd_iterations:
            points = _lloyd_relax(points, lloyd_iterations)
        results: list[EquilibriumResult | None] = [None] * len(points)
    else:
        a1_min, a1_max = mapping.axis1_range
        a2_min, a2_max = mapping.axis2_range
        points = np.array(
            [
                ((p[0] - a1_min) / (a1_max - a1_min), (p[1] - a2_min) / (a2_max - a2_min))
                for p in initial_points
            ]
        )
        results = list(initial_results) if initial_results is not None else [None] * len(points)

    assemblages: list[_Assemblage] = [
        tuple(sorted(r.ph)) if r is not None else None for r in results
    ]

    def compute_batch(indices: Sequence[int]) -> None:
        batch_points = [mapping.to_point(*points[i]) for i in indices]
        batch_results = batch_fn(
            database, batch_points, max_workers=max_workers, verbose=verbose, solver=solver
        )
        for idx, result in zip(indices, batch_results, strict=True):
            ok = result.status == 0 and bool(result.ph)
            results[idx] = result if ok else None
            assemblages[idx] = tuple(sorted(result.ph)) if ok else None

    pending = [i for i, r in enumerate(results) if r is None]
    if pending:
        compute_batch(pending)

    tri = Delaunay(points)
    converged = False
    unresolved = 0
    for _ in range(max_depth):
        violations = _violating_edges(tri, assemblages, refine_all)
        if not violations:
            converged = True
            unresolved = 0
            break
        unresolved = len(violations)

        n_before = len(points)
        added = _densify(points, violations, min_distance)
        if len(added) == 0:
            converged = False
            break

        points = np.vstack([points, added])
        results.extend([None] * len(added))
        assemblages.extend([None] * len(added))
        tri = Delaunay(points)

        new_indices = list(range(n_before, n_before + len(added)))
        compute_batch(new_indices)
    else:
        violations = _violating_edges(tri, assemblages, refine_all)
        converged = not violations
        unresolved = len(violations)

    edges: set[tuple[int, int]] = set()
    for simplex in tri.simplices:
        for k in range(3):
            i, j = int(simplex[k]), int(simplex[(k + 1) % 3])
            edges.add((i, j) if i < j else (j, i))

    physical_points = tuple(mapping.physical(float(u), float(v)) for u, v in points)

    return _MeshState(
        points=physical_points,
        results=tuple(results),
        assemblages=tuple(assemblages),
        edges=tuple(sorted(edges)),
        converged=converged,
        unresolved_boundaries=unresolved,
    )


def validate_mesh(assemblages: Sequence[_Assemblage], edges: Sequence[tuple[int, int]]) -> bool:
    """Check that every edge between two differently-assembled points is a legitimate boundary.

    Edges where either endpoint has no assemblage (a failed computation), or where both
    endpoints share the same assemblage, are skipped rather than checked. Needs neither
    `numpy` nor `scipy` -- pure Python over an already-built mesh snapshot.

    Args:
        assemblages: Per-point sorted stable-phase-name tuples (or `None`), by point index.
        edges: `(i, j)` index pairs to check (e.g. `Pseudosection.edges`).

    Returns:
        Whether every such edge is a clean boundary (see `magemin._diagrams._is_clean_boundary`).
    """
    for i, j in edges:
        a, b = assemblages[i], assemblages[j]
        if a is None or b is None or a == b:
            continue
        if not _is_clean_boundary(a, b):
            return False
    return True
