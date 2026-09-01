"""Axis-agnostic adaptive quadtree refinement engine for phase diagrams.

Implements the same *intent* as MAGEMin_C.jl's ``julia/AMR.jl`` (compare the
stable-phase assemblage at a cell's 4 corners; subdivide cells whose corners
disagree, since they straddle a phase-assemblage boundary) with a
deliberately simpler data structure: a recursive quadtree per cell, backed by
a shared point cache keyed by integer lattice coordinates rather than
AMR.jl's explicit mesh/``hash_map``/cell-topology bookkeeping.

The integer lattice is what makes the point cache safe: with
``n = 2 ** max_depth`` divisions per axis, every cell corner is an integer
pair ``(i, j)`` with ``0 <= i, j <= n``, and subdivision always bisects via
integer floor division (``(i0 + i1) // 2``). Two different subdivision paths
that reach the "same" shared corner or edge midpoint therefore always compute
an identical ``(i, j)`` key by construction -- never by float comparison --
so a plain ``dict`` cache fully replaces AMR.jl's ``hash_map``.

One deliberate simplification vs. ``AMR.jl``: AMR.jl re-tests previously
"kept" cells against a neighbor's later-created edge midpoint, catching thin
boundary slivers that touch an edge but not a corner. This engine does not:
a cell resolved from its 4 corners is final. The point cache still fully
replicates AMR.jl's redundant-computation avoidance (identical lattice
coordinates are always computed exactly once); only that neighbor-re-test
refinement pass is intentionally dropped, in favor of much less code.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from magemin.bulk_rocks import BulkRock
from magemin.core import Point
from magemin.errors import BulkCompositionError, MAGEMinComputeError

if TYPE_CHECKING:
    from magemin.diagrams import DiagramCell
    from magemin.results import EquilibriumResult

_LatticePoint = tuple[int, int]


@dataclass(frozen=True, slots=True)
class _AxisMapping:
    """Maps normalized ``(u, v)`` in ``[0, 1] x [0, 1]`` to a `Point`.

    Attributes:
        axis1_range: Physical (min, max) range of the first diagram axis.
        axis2_range: Physical (min, max) range of the second diagram axis.
        to_point: Builds a `Point` for normalized coordinates `u`, `v`.
    """

    axis1_range: tuple[float, float]
    axis2_range: tuple[float, float]
    to_point: Callable[[float, float], Point]

    def physical(self, u: float, v: float) -> tuple[float, float]:
        """Convert normalized `(u, v)` to physical `(axis1, axis2)` values."""
        a1_min, a1_max = self.axis1_range
        a2_min, a2_max = self.axis2_range
        return a1_min + u * (a1_max - a1_min), a2_min + v * (a2_max - a2_min)


def _resolve_bulk_for_interpolation(
    bulk_a: Sequence[float] | BulkRock,
    bulk_b: Sequence[float] | BulkRock,
    sys_in: Literal["mol", "wt"] | None,
) -> tuple[tuple[float, ...], tuple[float, ...], Literal["mol", "wt"]]:
    """Resolve two bulk-composition end-members to plain value tuples + sys_in."""
    if isinstance(bulk_a, BulkRock) and isinstance(bulk_b, BulkRock):
        if bulk_a.database != bulk_b.database or bulk_a.oxides != bulk_b.oxides:
            raise BulkCompositionError(
                f"bulk_a ({bulk_a.name!r}, database {bulk_a.database!r}, oxides "
                f"{bulk_a.oxides}) and bulk_b ({bulk_b.name!r}, database "
                f"{bulk_b.database!r}, oxides {bulk_b.oxides}) must share the same "
                "database and oxide order"
            )
        if sys_in is None:
            if bulk_a.sys_in != bulk_b.sys_in:
                raise BulkCompositionError(
                    f"bulk_a and bulk_b have different sys_in ({bulk_a.sys_in!r} vs "
                    f"{bulk_b.sys_in!r}); pass sys_in explicitly to resolve the mismatch"
                )
            sys_in = bulk_a.sys_in
        return bulk_a.values, bulk_b.values, sys_in

    values_a = bulk_a.values if isinstance(bulk_a, BulkRock) else tuple(bulk_a)
    values_b = bulk_b.values if isinstance(bulk_b, BulkRock) else tuple(bulk_b)
    if len(values_a) != len(values_b):
        raise BulkCompositionError(
            f"bulk_a has {len(values_a)} values but bulk_b has {len(values_b)}"
        )
    if sys_in is None:
        raise MAGEMinComputeError(
            "sys_in is required ('mol' or 'wt') when bulk_a/bulk_b are not both BulkRock instances"
        )
    return values_a, values_b, sys_in


def _pt_axis_mapping(
    P: tuple[float, float],
    T: tuple[float, float],
    bulk: Sequence[float] | BulkRock,
    sys_in: Literal["mol", "wt"] | None,
    *,
    buffer: str | None,
    buffer_value: float | None,
    suppress_phases: Sequence[str] | None,
    light: bool,
    name_solvus: bool,
) -> _AxisMapping:
    """Build the normalized-to-physical mapping shared by `PhaseDiagram.pt`/`Pseudosection.pt`."""

    def to_point(u: float, v: float) -> Point:
        p = P[0] + u * (P[1] - P[0])
        t = T[0] + v * (T[1] - T[0])
        return Point(
            P=p,
            T=t,
            bulk=bulk,
            sys_in=sys_in,
            buffer=buffer,
            buffer_value=buffer_value,
            suppress_phases=suppress_phases,
            light=light,
            name_solvus=name_solvus,
        )

    return _AxisMapping(axis1_range=P, axis2_range=T, to_point=to_point)


def _px_axis_mapping(
    P: tuple[float, float],
    T: float,
    bulk_a: Sequence[float] | BulkRock,
    bulk_b: Sequence[float] | BulkRock,
    sys_in: Literal["mol", "wt"] | None,
    *,
    buffer: str | None,
    buffer_value: float | None,
    suppress_phases: Sequence[str] | None,
    light: bool,
    name_solvus: bool,
) -> _AxisMapping:
    """Build the normalized-to-physical mapping shared by `PhaseDiagram.px`/`Pseudosection.px`."""
    values_a, values_b, resolved_sys_in = _resolve_bulk_for_interpolation(bulk_a, bulk_b, sys_in)

    def to_point(u: float, v: float) -> Point:
        p = P[0] + u * (P[1] - P[0])
        bulk = interpolate_bulk(values_a, values_b, v)
        return Point(
            P=p,
            T=T,
            bulk=bulk,
            sys_in=resolved_sys_in,
            buffer=buffer,
            buffer_value=buffer_value,
            suppress_phases=suppress_phases,
            light=light,
            name_solvus=name_solvus,
        )

    return _AxisMapping(axis1_range=P, axis2_range=(0.0, 1.0), to_point=to_point)


def _tx_axis_mapping(
    P: float,
    T: tuple[float, float],
    bulk_a: Sequence[float] | BulkRock,
    bulk_b: Sequence[float] | BulkRock,
    sys_in: Literal["mol", "wt"] | None,
    *,
    buffer: str | None,
    buffer_value: float | None,
    suppress_phases: Sequence[str] | None,
    light: bool,
    name_solvus: bool,
) -> _AxisMapping:
    """Build the normalized-to-physical mapping shared by `PhaseDiagram.tx`/`Pseudosection.tx`."""
    values_a, values_b, resolved_sys_in = _resolve_bulk_for_interpolation(bulk_a, bulk_b, sys_in)

    def to_point(u: float, v: float) -> Point:
        t = T[0] + u * (T[1] - T[0])
        bulk = interpolate_bulk(values_a, values_b, v)
        return Point(
            P=P,
            T=t,
            bulk=bulk,
            sys_in=resolved_sys_in,
            buffer=buffer,
            buffer_value=buffer_value,
            suppress_phases=suppress_phases,
            light=light,
            name_solvus=name_solvus,
        )

    return _AxisMapping(axis1_range=T, axis2_range=(0.0, 1.0), to_point=to_point)


@dataclass(frozen=True, slots=True)
class _LatticeCell:
    """One quadtree cell, expressed in integer lattice coordinates.

    Attributes:
        i0: Lower lattice coordinate along axis 1.
        j0: Lower lattice coordinate along axis 2.
        i1: Upper lattice coordinate along axis 1.
        j1: Upper lattice coordinate along axis 2.
        depth: Refinement depth this cell was created at.
    """

    i0: int
    j0: int
    i1: int
    j1: int
    depth: int

    def corners(self) -> tuple[_LatticePoint, _LatticePoint, _LatticePoint, _LatticePoint]:
        """Return the cell's 4 corners, counter-clockwise from bottom-left."""
        return (
            (self.i0, self.j0),
            (self.i1, self.j0),
            (self.i1, self.j1),
            (self.i0, self.j1),
        )

    def subdivide(self) -> tuple[_LatticeCell, _LatticeCell, _LatticeCell, _LatticeCell]:
        """Bisect this cell into 4 children at `depth + 1`."""
        mi, mj = (self.i0 + self.i1) // 2, (self.j0 + self.j1) // 2
        d = self.depth + 1
        return (
            _LatticeCell(self.i0, self.j0, mi, mj, d),
            _LatticeCell(mi, self.j0, self.i1, mj, d),
            _LatticeCell(mi, mj, self.i1, self.j1, d),
            _LatticeCell(self.i0, mj, mi, self.j1, d),
        )


@dataclass(frozen=True, slots=True)
class _ResolvedCell:
    """A finalized quadtree leaf, in physical axis coordinates.

    Attributes:
        corners: The cell's 4 physical `(axis1, axis2)` corners,
            counter-clockwise from bottom-left.
        lattice_corners: The same 4 corners as exact integer `(i, j)` lattice
            coordinates, `0 <= i, j <= 2 ** max_depth` -- what
            `validate_diagram`'s `build_adjacency` uses for exact-integer
            adjacency instead of float comparison.
        depth: Refinement depth this cell was finalized at.
        resolved: Whether all 4 corners share one stable-phase assemblage.
        assemblage: Sorted shared phase-name tuple when `resolved`; `None`
            otherwise.
    """

    corners: tuple[
        tuple[float, float], tuple[float, float], tuple[float, float], tuple[float, float]
    ]
    lattice_corners: tuple[_LatticePoint, _LatticePoint, _LatticePoint, _LatticePoint]
    depth: int
    resolved: bool
    assemblage: tuple[str, ...] | None


def refine(
    database: str,
    mapping: _AxisMapping,
    *,
    initial_resolution: int,
    max_depth: int,
    max_workers: int | None,
    verbose: bool,
    solver: int,
    batch_fn: Callable[..., list[EquilibriumResult]],
    initial_cache: dict[_LatticePoint, EquilibriumResult] | None = None,
) -> tuple[list[_ResolvedCell], dict[_LatticePoint, EquilibriumResult]]:
    """Adaptively refine a 2D grid until every cell's stable assemblage is resolved.

    Args:
        database: Database acronym, passed through to `batch_fn`.
        mapping: Normalized-to-physical axis mapping for this diagram.
        initial_resolution: The starting grid is `2 ** initial_resolution`
            cells per axis.
        max_depth: Maximum refinement depth below `initial_resolution`.
        max_workers: Passed through to `batch_fn`.
        verbose: Passed through to `batch_fn`.
        solver: Passed through to `batch_fn`.
        batch_fn: Callable with the same signature as
            `magemin.core.multi_point_minimization`, injectable for testing.
        initial_cache: Already-known lattice results to seed the point cache
            with, so a repeat call over the same lattice (e.g.
            `PhaseDiagram.refine()` continuing at a deeper `max_depth`) never
            recomputes an already-known point. Copied, not mutated in place.

    Returns:
        The finalized leaf cells, and the full point cache (lattice
        coordinate to computed result) backing them.
    """
    if initial_resolution > max_depth:
        raise ValueError(
            f"initial_resolution ({initial_resolution}) must not exceed max_depth ({max_depth})"
        )

    n = 2**max_depth
    step = n // (2**initial_resolution)
    n_initial = 2**initial_resolution
    # Cell size is n / 2**depth, so initial (unsubdivided) cells must be
    # tagged with depth=initial_resolution -- not 0 -- for that relationship
    # (and therefore the depth>=max_depth terminal check, which relies on
    # size==1 exactly when depth==max_depth) to hold from the start.
    frontier = [
        _LatticeCell(c * step, r * step, (c + 1) * step, (r + 1) * step, initial_resolution)
        for r in range(n_initial)
        for c in range(n_initial)
    ]

    cache: dict[_LatticePoint, EquilibriumResult] = dict(initial_cache) if initial_cache else {}
    leaves: list[_ResolvedCell] = []

    while frontier:
        needed = sorted({corner for cell in frontier for corner in cell.corners()} - cache.keys())
        if needed:
            points = [mapping.to_point(i / n, j / n) for i, j in needed]
            results = batch_fn(
                database, points, max_workers=max_workers, verbose=verbose, solver=solver
            )
            cache.update(zip(needed, results, strict=True))

        next_frontier: list[_LatticeCell] = []
        for cell in frontier:
            lattice_corners = cell.corners()
            assemblages = [tuple(sorted(cache[corner].ph)) for corner in lattice_corners]
            physical_corners = tuple(mapping.physical(i / n, j / n) for i, j in lattice_corners)
            if len(set(assemblages)) == 1:
                leaves.append(
                    _ResolvedCell(
                        physical_corners, lattice_corners, cell.depth, True, assemblages[0]
                    )
                )
            elif cell.depth >= max_depth:
                leaves.append(
                    _ResolvedCell(physical_corners, lattice_corners, cell.depth, False, None)
                )
            else:
                next_frontier.extend(cell.subdivide())
        frontier = next_frontier

    return leaves, cache


def interpolate_bulk(
    values_a: Sequence[float], values_b: Sequence[float], x: float
) -> tuple[float, ...]:
    """Linearly interpolate between two bulk-composition value sequences.

    Args:
        values_a: Values at `x == 0`.
        values_b: Values at `x == 1`.
        x: Interpolation fraction, typically in `[0, 1]`.

    Returns:
        Per-oxide interpolated values, `a + x * (b - a)`.
    """
    return tuple(a + x * (b - a) for a, b in zip(values_a, values_b, strict=True))


# Groups of phase abbreviations that are polymorphs of one another (same composition, different
# structure) across the datasets this project wires up (see MAGEMin/README.md's per-dataset
# phase lists): swapping between members of one of these groups is a genuine, clean
# Schreinemakers reaction (e.g. `and = sill`) even though it doesn't fit the plain "one assemblage
# is the other plus one phase" pattern -- the phase count doesn't change, one polymorph simply
# replaces another. `"q"`/`"qtz"` are both included since the abbreviation differs between the
# Holland/White/Green-family datasets (`"q"`) and the Stixrude & Lithgow-Bertelloni mantle dataset
# (`"qtz"`).
_POLYMORPH_GROUPS: tuple[frozenset[str], ...] = (
    frozenset({"ky", "sill", "and"}),  # Al2SiO5: kyanite, sillimanite, andalusite
    frozenset({"q", "qtz", "crst", "trd", "coe", "stv"}),  # SiO2: quartz, cristobalite,
    # tridymite, coesite, stishovite
)


def _polymorph_group(phase: str) -> frozenset[str] | None:
    """The polymorph group `phase` belongs to, or `None` if it isn't a recognized polymorph."""
    for group in _POLYMORPH_GROUPS:
        if phase in group:
            return group
    return None


def _is_clean_boundary(assemblage_a: tuple[str, ...], assemblage_b: tuple[str, ...]) -> bool:
    """Whether two adjacent cells' assemblages form a legitimate univariant boundary.

    "Clean" means either one assemblage is exactly the other plus one extra phase (the common
    zero-mode case), or the two assemblages are otherwise identical except for one phase on each
    side that are polymorphs of each other, e.g. `{..., and}` vs. `{..., sill}`. Anything else
    (equal sets, a swap between non-polymorphs, a larger symmetric difference) is not clean.

    Args:
        assemblage_a: One cell's assemblage.
        assemblage_b: The other cell's assemblage.

    Returns:
        Whether the pair is a legitimate boundary.
    """
    set_a, set_b = set(assemblage_a), set(assemblage_b)
    diff_a, diff_b = set_a - set_b, set_b - set_a
    if len(diff_a) == 1 and not diff_b:
        return True
    if len(diff_b) == 1 and not diff_a:
        return True
    if len(diff_a) == 1 and len(diff_b) == 1:
        phase_a, phase_b = next(iter(diff_a)), next(iter(diff_b))
        group = _polymorph_group(phase_a)
        return group is not None and phase_b in group
    return False


def _cell_bounds(cell: DiagramCell) -> tuple[int, int, int, int]:
    """Return a cell's `(i0, j0, i1, j1)` lattice bounds from its 4 corners."""
    (i0, j0), (i1, _), (_, j1), _ = cell.lattice_corners
    return i0, j0, i1, j1


def build_adjacency(cells: Sequence[DiagramCell]) -> dict[int, set[int]]:
    """Find every pair of cells sharing a lattice boundary segment.

    Built via edge-coordinate bucketing (cells are grouped by each of their 4 edge coordinates,
    and only compared within a matching bucket) rather than an all-pairs scan, so this stays
    efficient at the few-thousand-cell scale a diagram's mesh reaches.

    Args:
        cells: The diagram's mesh cells.

    Returns:
        Cell index to the set of adjacent cell indices.
    """
    right_edges: dict[int, list[tuple[int, int, int]]] = defaultdict(list)
    left_edges: dict[int, list[tuple[int, int, int]]] = defaultdict(list)
    top_edges: dict[int, list[tuple[int, int, int]]] = defaultdict(list)
    bottom_edges: dict[int, list[tuple[int, int, int]]] = defaultdict(list)

    for idx, cell in enumerate(cells):
        i0, j0, i1, j1 = _cell_bounds(cell)
        right_edges[i1].append((idx, j0, j1))
        left_edges[i0].append((idx, j0, j1))
        top_edges[j1].append((idx, i0, i1))
        bottom_edges[j0].append((idx, i0, i1))

    adjacency: dict[int, set[int]] = defaultdict(set)

    def link(idx_a: int, idx_b: int) -> None:
        adjacency[idx_a].add(idx_b)
        adjacency[idx_b].add(idx_a)

    for coord, right_group in right_edges.items():
        for idx_a, aj0, aj1 in right_group:
            for idx_b, bj0, bj1 in left_edges.get(coord, ()):
                if max(aj0, bj0) < min(aj1, bj1):
                    link(idx_a, idx_b)

    for coord, top_group in top_edges.items():
        for idx_a, ai0, ai1 in top_group:
            for idx_b, bi0, bi1 in bottom_edges.get(coord, ()):
                if max(ai0, bi0) < min(ai1, bi1):
                    link(idx_a, idx_b)

    return adjacency


def validate_diagram(cells: Sequence[DiagramCell]) -> bool:
    """Check that every pair of nearby, resolved cells forms a legitimate boundary.

    "Nearby" means directly adjacent, or adjacent through exactly one shared unresolved buffer
    cell -- a real boundary between two different resolved fields almost always leaves at least
    one still-unresolved cell straddling it (same-size directly-adjacent resolved leaves are
    mathematically forced to agree, since they share the exact corner points that made each of
    them resolve in the first place), so bridging one such cell is what actually lets this reach
    the diagram's real reaction-line network rather than only the rare differently-sized-neighbor
    edge case. Cell pairs sharing the same assemblage are skipped rather than checked -- this
    validates mesh structure only where the mesh actually reached a decision on both sides.

    Args:
        cells: The diagram's mesh cells.

    Returns:
        Whether every such nearby resolved pair with differing assemblages is a clean boundary
        (see `_is_clean_boundary`).
    """
    adjacency = build_adjacency(cells)
    checked: set[tuple[int, int]] = set()

    def check_pair(i: int, j: int) -> bool:
        key = (i, j) if i < j else (j, i)
        if key in checked:
            return True
        checked.add(key)
        a, b = cells[i], cells[j]
        return a.assemblage == b.assemblage or _is_clean_boundary(a.assemblage, b.assemblage)

    for i, neighbors in adjacency.items():
        a = cells[i]
        if not a.resolved:
            continue
        for j in neighbors:
            b = cells[j]
            if b.resolved:
                if not check_pair(i, j):
                    return False
            else:
                for k in adjacency.get(j, ()):
                    if k == i or not cells[k].resolved:
                        continue
                    if not check_pair(i, k):
                        return False
    return True
