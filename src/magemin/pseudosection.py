"""Adaptive Delaunay-mesh PT, PX, and TX stable-phase-assemblage pseudosections.

Built on top of `magemin.multi_point_minimization`, using a perturbed-hex-lattice Delaunay mesh
(ported from the sibling `pseudo_graph` project) instead of `magemin.diagrams.PhaseDiagram`'s
quadtree grid: points are densified wherever two Delaunay-triangle-adjacent points disagree in a
way that isn't a legitimate single-phase or polymorph-swap boundary. See `magemin._mesh` for the
refinement engine. Requires the optional `mesh` extra (`pip install magemin[mesh]`) to actually
build or refine a pseudosection; `.validate()` and `.plot()`/`.show()` do not (the latter needs
the optional `plot` extra instead).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from magemin import _diagrams, _mesh
from magemin.bulk_rocks import BulkRock
from magemin.core import multi_point_minimization
from magemin.errors import MAGEMinPlottingError
from magemin.results import EquilibriumResult

if TYPE_CHECKING:
    import matplotlib.figure

# tab10, not tab20 -- tab20's light/dark shade pairs are easy to confuse at a glance.
_N_COLORS = 10
_MARKERS = ["o", "s", "^", "v", "D", "P", "X", "*", "<", ">", "p", "h", "8", "d"]


@dataclass(frozen=True, slots=True)
class MeshPoint:
    """One computed point in a `Pseudosection`'s Delaunay mesh.

    Attributes:
        axis1: Physical value along the pseudosection's first axis (P in kbar / T in Celsius /
            X in `[0, 1]`).
        axis2: Physical value along the pseudosection's second axis.
        result: The computed equilibrium result, or `None` if the computation failed (non-zero
            status or no stable phases).
        assemblage: Sorted stable-phase-name tuple, or `None` when `result` is `None`.
    """

    axis1: float
    axis2: float
    result: EquilibriumResult | None
    assemblage: tuple[str, ...] | None


@dataclass(frozen=True, slots=True)
class Pseudosection:
    """An adaptive Delaunay-mesh PT, PX, or TX stable-phase-assemblage pseudosection.

    Construct via `Pseudosection.pt`/`.px`/`.tx` -- not directly. Unlike `PhaseDiagram`'s
    quadtree grid, points are sampled on a perturbed hexagonal lattice and densified wherever
    two Delaunay-triangle-adjacent points disagree in a way that isn't a legitimate boundary
    (see `magemin._mesh`).

    Attributes:
        kind: Which two parameters vary: `"PT"`, `"PX"`, or `"TX"`.
        database: The database acronym this pseudosection was computed with.
        axis1_label: Human-readable label for the first (horizontal) axis.
        axis2_label: Human-readable label for the second (vertical) axis.
        axis1_range: Physical `(min, max)` range of the first axis.
        axis2_range: Physical `(min, max)` range of the second axis.
        fixed_label: Human-readable description of the held-fixed parameter
            (e.g. `"T = 900 °C"`) for PX/TX pseudosections; `None` for PT.
        fixed_value: The raw held-fixed value (`T` for PX, `P` for TX) `fixed_label`
            describes; `None` for PT.
        points: Every computed mesh point, in mesh-index order.
        edges: Deduplicated `(i, j)` index pairs into `points`, for every Delaunay-edge-adjacent
            point pair in the mesh.
        converged: Whether every edge was a clean boundary (or shared/omitted an endpoint) by
            the time refinement stopped.
        unresolved_boundaries: Count of edges failing the clean-boundary check when refinement
            stopped (`0` if `converged`).
        initial_resolution: The `initial_resolution` this pseudosection was computed with.
        rounds: The number of densification rounds used by the most recent
            `.pt`/`.px`/`.tx`/`.refine()` call -- a per-call round cap, not a cumulative depth
            like `PhaseDiagram.max_depth` (it does not grow across `.refine()` calls the way
            that attribute does, so it isn't called `max_depth` here).
        solver: The `solver` this pseudosection was computed with. Used by `refine()` so newly
            computed points stay consistent with the rest of the mesh.
    """

    kind: Literal["PT", "PX", "TX"]
    database: str
    axis1_label: str
    axis2_label: str
    axis1_range: tuple[float, float]
    axis2_range: tuple[float, float]
    fixed_label: str | None
    fixed_value: float | None
    points: tuple[MeshPoint, ...]
    edges: tuple[tuple[int, int], ...]
    converged: bool
    unresolved_boundaries: int
    initial_resolution: int
    rounds: int
    solver: int
    # Not part of the public contract (hence no Attributes: entry above): the
    # normalized-to-physical mapping (including the to_point closure covering
    # bulk/buffer/suppress_phases/etc, none of which are otherwise retained on this dataclass)
    # needed to compute further points in refine().
    _mapping: _diagrams._AxisMapping = field(repr=False)

    def __str__(self) -> str:
        """Return a human-readable summary."""
        n_fields = len({p.assemblage for p in self.points if p.assemblage is not None})
        lines = [f"{self.kind} pseudosection ({self.database})"]
        if self.fixed_label:
            lines.append(f"  Fixed                : {self.fixed_label}")
        lines.append(f"  {self.axis1_label:<21}: {self.axis1_range[0]:g} - {self.axis1_range[1]:g}")
        lines.append(f"  {self.axis2_label:<21}: {self.axis2_range[0]:g} - {self.axis2_range[1]:g}")
        lines.append(
            f"  Refinement           : initial_resolution={self.initial_resolution}, "
            f"rounds={self.rounds}, solver={self.solver}"
        )
        lines.append(f"  Points computed      : {len(self.points)}")
        lines.append(f"  Distinct assemblages : {n_fields}")
        lines.append(f"  Converged            : {self.converged}")
        return "\n".join(lines)

    @classmethod
    def _from_state(
        cls,
        *,
        kind: Literal["PT", "PX", "TX"],
        database: str,
        axis1_label: str,
        axis2_label: str,
        axis1_range: tuple[float, float],
        axis2_range: tuple[float, float],
        fixed_label: str | None,
        fixed_value: float | None,
        mapping: _diagrams._AxisMapping,
        initial_resolution: int,
        refine: int,
        solver: int,
        state: _mesh._MeshState,
    ) -> Pseudosection:
        """Assemble a `Pseudosection` from a `_mesh.refine_mesh()` result."""
        points = tuple(
            MeshPoint(axis1=p[0], axis2=p[1], result=r, assemblage=a)
            for p, r, a in zip(state.points, state.results, state.assemblages, strict=True)
        )
        return cls(
            kind=kind,
            database=database,
            axis1_label=axis1_label,
            axis2_label=axis2_label,
            axis1_range=axis1_range,
            axis2_range=axis2_range,
            fixed_label=fixed_label,
            fixed_value=fixed_value,
            points=points,
            edges=state.edges,
            converged=state.converged,
            unresolved_boundaries=state.unresolved_boundaries,
            initial_resolution=initial_resolution,
            rounds=refine,
            solver=solver,
            _mapping=mapping,
        )

    @classmethod
    def _construct(
        cls,
        *,
        kind: Literal["PT", "PX", "TX"],
        database: str,
        axis1_label: str,
        axis2_label: str,
        axis1_range: tuple[float, float],
        axis2_range: tuple[float, float],
        fixed_label: str | None,
        fixed_value: float | None,
        mapping: _diagrams._AxisMapping,
        initial_resolution: int,
        refine: int,
        refine_all: bool,
        seed: int,
        lloyd_iterations: int,
        min_distance: float,
        max_workers: int | None,
        verbose: bool,
        solver: int,
    ) -> Pseudosection:
        state = _mesh.refine_mesh(
            database,
            mapping,
            initial_resolution=initial_resolution,
            max_depth=refine,
            refine_all=refine_all,
            seed=seed,
            lloyd_iterations=lloyd_iterations,
            min_distance=min_distance,
            max_workers=max_workers,
            verbose=verbose,
            solver=solver,
            batch_fn=multi_point_minimization,
        )
        return cls._from_state(
            kind=kind,
            database=database,
            axis1_label=axis1_label,
            axis2_label=axis2_label,
            axis1_range=axis1_range,
            axis2_range=axis2_range,
            fixed_label=fixed_label,
            fixed_value=fixed_value,
            mapping=mapping,
            initial_resolution=initial_resolution,
            refine=refine,
            solver=solver,
            state=state,
        )

    @classmethod
    def pt(
        cls,
        database: str,
        P: tuple[float, float],
        T: tuple[float, float],
        bulk: Sequence[float] | BulkRock,
        sys_in: Literal["mol", "wt"] | None = None,
        *,
        buffer: str | None = None,
        buffer_value: float | None = None,
        suppress_phases: Sequence[str] | None = None,
        light: bool = True,
        name_solvus: bool = True,
        initial_resolution: int = 4,
        refine: int = 0,
        refine_all: bool = False,
        seed: int = 0,
        lloyd_iterations: int = 2,
        min_distance: float = 1e-6,
        max_workers: int | None = None,
        verbose: bool = False,
        solver: int = 2,
    ) -> Pseudosection:
        """Compute an adaptive Delaunay-mesh pressure-temperature pseudosection.

        Args:
            database: Database acronym, as for `MAGEMin(database)`.
            P: Pressure range `(min, max)` in kbar.
            T: Temperature range `(min, max)` in Celsius.
            bulk: Bulk composition, as for `MAGEMin.compute`.
            sys_in: Composition unit, as for `MAGEMin.compute`.
            buffer: As for `MAGEMin.compute`.
            buffer_value: As for `MAGEMin.compute`.
            suppress_phases: As for `MAGEMin.compute`.
            light: As for `MAGEMin.compute`; defaults to `True` here since the mesh only ever
                reads `.ph`/`.status`.
            name_solvus: As for `MAGEMin.compute` (defaults to `True` there too) -- the
                boundary-checking criterion depends on solvus-disambiguated phase names to
                detect real solvus boundaries (see `magemin.solvus_name`).
            initial_resolution: The starting hex lattice has roughly `(2 **
                initial_resolution + 1) ** 2` points.
            refine: Maximum number of densification rounds (must be `>= 0`). Defaults to `0`
                -- just the initial lattice, no densification -- so pass a positive value to
                actually refine (matches `PhaseDiagram.pt`'s `refine` convention).
            refine_all: If True, keep densifying already-clean boundaries too (uniformly denser
                sampling), instead of stopping once every boundary is recognized as clean.
            seed: RNG seed for the initial lattice's jitter.
            lloyd_iterations: Voronoi-relaxation passes applied to the initial lattice.
            min_distance: Minimum allowed distance (normalized `[0,1]^2` units) between any two
                points -- a new densification midpoint closer than this to an existing point is
                rejected, capping how far refinement can go.
            max_workers: As for `multi_point_minimization`.
            verbose: As for `multi_point_minimization`.
            solver: As for `MAGEMin.__init__`.

        Returns:
            The computed pseudosection.

        Raises:
            MAGEMinMeshError: If `numpy`/`scipy` are not installed.
        """
        mapping = _diagrams._pt_axis_mapping(
            P,
            T,
            bulk,
            sys_in,
            buffer=buffer,
            buffer_value=buffer_value,
            suppress_phases=suppress_phases,
            light=light,
            name_solvus=name_solvus,
        )
        return cls._construct(
            kind="PT",
            database=database,
            axis1_label="P [kbar]",
            axis2_label="T [°C]",
            axis1_range=P,
            axis2_range=T,
            fixed_label=None,
            fixed_value=None,
            mapping=mapping,
            initial_resolution=initial_resolution,
            refine=refine,
            refine_all=refine_all,
            seed=seed,
            lloyd_iterations=lloyd_iterations,
            min_distance=min_distance,
            max_workers=max_workers,
            verbose=verbose,
            solver=solver,
        )

    @classmethod
    def px(
        cls,
        database: str,
        P: tuple[float, float],
        T: float,
        bulk_a: Sequence[float] | BulkRock,
        bulk_b: Sequence[float] | BulkRock,
        sys_in: Literal["mol", "wt"] | None = None,
        *,
        buffer: str | None = None,
        buffer_value: float | None = None,
        suppress_phases: Sequence[str] | None = None,
        light: bool = True,
        name_solvus: bool = True,
        initial_resolution: int = 4,
        refine: int = 0,
        refine_all: bool = False,
        seed: int = 0,
        lloyd_iterations: int = 2,
        min_distance: float = 1e-6,
        max_workers: int | None = None,
        verbose: bool = False,
        solver: int = 2,
    ) -> Pseudosection:
        """Compute an adaptive Delaunay-mesh PX pseudosection at fixed temperature.

        `X` is a bulk-composition interpolation fraction in `[0, 1]`: `X=0` is `bulk_a`, `X=1`
        is `bulk_b`, linearly interpolated per-oxide in between.

        Args:
            database: Database acronym, as for `MAGEMin(database)`.
            P: Pressure range `(min, max)` in kbar.
            T: Fixed temperature in Celsius.
            bulk_a: Bulk composition at `X=0`.
            bulk_b: Bulk composition at `X=1`; must share `bulk_a`'s oxide set/order (and
                `sys_in`, unless `sys_in` is given explicitly).
            sys_in: Composition unit. Required unless `bulk_a`/`bulk_b` are both `BulkRock`
                instances with a matching `sys_in`.
            buffer: As for `MAGEMin.compute`.
            buffer_value: As for `MAGEMin.compute`.
            suppress_phases: As for `MAGEMin.compute`.
            light: As for `Pseudosection.pt`.
            name_solvus: As for `Pseudosection.pt`.
            initial_resolution: As for `Pseudosection.pt`.
            refine: As for `Pseudosection.pt`.
            refine_all: As for `Pseudosection.pt`.
            seed: As for `Pseudosection.pt`.
            lloyd_iterations: As for `Pseudosection.pt`.
            min_distance: As for `Pseudosection.pt`.
            max_workers: As for `multi_point_minimization`.
            verbose: As for `multi_point_minimization`.
            solver: As for `MAGEMin.__init__`.

        Returns:
            The computed pseudosection.
        """
        mapping = _diagrams._px_axis_mapping(
            P,
            T,
            bulk_a,
            bulk_b,
            sys_in,
            buffer=buffer,
            buffer_value=buffer_value,
            suppress_phases=suppress_phases,
            light=light,
            name_solvus=name_solvus,
        )
        return cls._construct(
            kind="PX",
            database=database,
            axis1_label="P [kbar]",
            axis2_label="X",
            axis1_range=P,
            axis2_range=(0.0, 1.0),
            fixed_label=f"T = {T:g} °C",
            fixed_value=T,
            mapping=mapping,
            initial_resolution=initial_resolution,
            refine=refine,
            refine_all=refine_all,
            seed=seed,
            lloyd_iterations=lloyd_iterations,
            min_distance=min_distance,
            max_workers=max_workers,
            verbose=verbose,
            solver=solver,
        )

    @classmethod
    def tx(
        cls,
        database: str,
        P: float,
        T: tuple[float, float],
        bulk_a: Sequence[float] | BulkRock,
        bulk_b: Sequence[float] | BulkRock,
        sys_in: Literal["mol", "wt"] | None = None,
        *,
        buffer: str | None = None,
        buffer_value: float | None = None,
        suppress_phases: Sequence[str] | None = None,
        light: bool = True,
        name_solvus: bool = True,
        initial_resolution: int = 4,
        refine: int = 0,
        refine_all: bool = False,
        seed: int = 0,
        lloyd_iterations: int = 2,
        min_distance: float = 1e-6,
        max_workers: int | None = None,
        verbose: bool = False,
        solver: int = 2,
    ) -> Pseudosection:
        """Compute an adaptive Delaunay-mesh TX pseudosection at fixed pressure.

        `X` is a bulk-composition interpolation fraction in `[0, 1]`: `X=0` is `bulk_a`, `X=1`
        is `bulk_b`, linearly interpolated per-oxide in between.

        Args:
            database: Database acronym, as for `MAGEMin(database)`.
            P: Fixed pressure in kbar.
            T: Temperature range `(min, max)` in Celsius.
            bulk_a: Bulk composition at `X=0`.
            bulk_b: Bulk composition at `X=1`; must share `bulk_a`'s oxide set/order (and
                `sys_in`, unless `sys_in` is given explicitly).
            sys_in: Composition unit. Required unless `bulk_a`/`bulk_b` are both `BulkRock`
                instances with a matching `sys_in`.
            buffer: As for `MAGEMin.compute`.
            buffer_value: As for `MAGEMin.compute`.
            suppress_phases: As for `MAGEMin.compute`.
            light: As for `Pseudosection.pt`.
            name_solvus: As for `Pseudosection.pt`.
            initial_resolution: As for `Pseudosection.pt`.
            refine: As for `Pseudosection.pt`.
            refine_all: As for `Pseudosection.pt`.
            seed: As for `Pseudosection.pt`.
            lloyd_iterations: As for `Pseudosection.pt`.
            min_distance: As for `Pseudosection.pt`.
            max_workers: As for `multi_point_minimization`.
            verbose: As for `multi_point_minimization`.
            solver: As for `MAGEMin.__init__`.

        Returns:
            The computed pseudosection.
        """
        mapping = _diagrams._tx_axis_mapping(
            P,
            T,
            bulk_a,
            bulk_b,
            sys_in,
            buffer=buffer,
            buffer_value=buffer_value,
            suppress_phases=suppress_phases,
            light=light,
            name_solvus=name_solvus,
        )
        return cls._construct(
            kind="TX",
            database=database,
            axis1_label="T [°C]",
            axis2_label="X",
            axis1_range=T,
            axis2_range=(0.0, 1.0),
            fixed_label=f"P = {P:g} kbar",
            fixed_value=P,
            mapping=mapping,
            initial_resolution=initial_resolution,
            refine=refine,
            refine_all=refine_all,
            seed=seed,
            lloyd_iterations=lloyd_iterations,
            min_distance=min_distance,
            max_workers=max_workers,
            verbose=verbose,
            solver=solver,
        )

    def refine(
        self,
        *,
        refine: int = 1,
        refine_all: bool = False,
        min_distance: float = 1e-6,
        max_workers: int | None = None,
        verbose: bool = False,
    ) -> Pseudosection:
        """Continue densifying this mesh, reusing every already-computed point.

        Every point this pseudosection already holds is reused as a starting point for a fresh
        densification round loop (up to `refine` more rounds) -- only genuinely new midpoints
        are computed. A point whose previous computation failed (`result is None`) is retried.
        This instance is left unchanged; a new `Pseudosection` is returned. Calling this on an
        already-`converged` mesh is cheap: the first violation check finds none and returns
        immediately.

        Args:
            refine: Maximum number of additional densification rounds.
            refine_all: As for `Pseudosection.pt`.
            min_distance: As for `Pseudosection.pt`.
            max_workers: As for `multi_point_minimization`.
            verbose: As for `multi_point_minimization`.

        Returns:
            The further-refined pseudosection.
        """
        initial_points = tuple((p.axis1, p.axis2) for p in self.points)
        initial_results = tuple(p.result for p in self.points)
        state = _mesh.refine_mesh(
            self.database,
            self._mapping,
            initial_resolution=self.initial_resolution,
            max_depth=refine,
            refine_all=refine_all,
            seed=0,
            lloyd_iterations=0,
            min_distance=min_distance,
            max_workers=max_workers,
            verbose=verbose,
            solver=self.solver,
            batch_fn=multi_point_minimization,
            initial_points=initial_points,
            initial_results=initial_results,
        )
        return Pseudosection._from_state(
            kind=self.kind,
            database=self.database,
            axis1_label=self.axis1_label,
            axis2_label=self.axis2_label,
            axis1_range=self.axis1_range,
            axis2_range=self.axis2_range,
            fixed_label=self.fixed_label,
            fixed_value=self.fixed_value,
            mapping=self._mapping,
            initial_resolution=self.initial_resolution,
            refine=refine,
            solver=self.solver,
            state=state,
        )

    def validate(self) -> bool:
        """Check that every mesh edge between two differently-assembled points is legitimate.

        Two Delaunay-edge-adjacent points with different assemblages must differ either by
        exactly one phase (an ordinary zero-mode univariant crossing) or by one phase on each
        side that are polymorphs of each other (e.g. `ky`/`sill`). Points with no assemblage
        (a failed computation) and edges between equal assemblages are skipped rather than
        checked.

        Returns:
            Whether every such edge is a clean boundary or a polymorph swap.
        """
        return _mesh.validate_mesh([p.assemblage for p in self.points], self.edges)

    def plot(
        self,
        *,
        figsize: tuple[float, float] | None = None,
        cmap: str = "tab10",
        marker_size: float = 10.0,
        alpha: float = 0.85,
        legend: bool = True,
        legend_loc: str = "outside right upper",
        legend_fontsize: str | float = "small",
    ) -> matplotlib.figure.Figure:
        """Render this pseudosection as a scatter plot, colored/shaped by stable assemblage.

        Pressure is always plotted on the vertical axis and temperature always on the
        horizontal axis, when either is present (PT: T horizontal / P vertical; PX: X
        horizontal / P vertical; TX: T horizontal / X vertical) -- the pseudosection's own
        `axis1`/`axis2` fields are unaffected by this, only the rendered orientation.

        Each field is drawn as a scatter of its own points: colors cycle through `cmap`'s first
        10 entries, then marker shape cycles through a 14-shape list every 10 fields, so any two
        same-colored fields always differ in shape too (ported from `pseudo_graph`'s
        `plot_field_points`). No region fill, no unresolved-cell shading, no colorbar -- points
        with no assemblage (a failed computation) are omitted entirely. Requires the optional
        `matplotlib` dependency (`pip install magemin[plot]`).

        Args:
            figsize: Figure size in inches; `None` (default) uses `(8.0, 6.0)`.
            cmap: Matplotlib qualitative colormap name; only its first 10 entries are used.
            marker_size: Scatter marker size (`s` passed to `Axes.scatter`).
            alpha: Scatter marker opacity.
            legend: Whether to draw the per-field legend.
            legend_loc: `loc` passed to `Figure.legend` -- an "outside" location string (e.g.
                `"outside right upper"`) so matplotlib's constrained-layout engine automatically
                reserves space for it, with no manual offset tuning needed.
            legend_fontsize: `fontsize` passed to `Figure.legend`.

        Returns:
            The created figure.

        Raises:
            MAGEMinPlottingError: If matplotlib is not installed.
        """
        try:
            import matplotlib as mpl
            import matplotlib.pyplot as plt
        except ImportError as exc:
            raise MAGEMinPlottingError(
                "matplotlib is required for Pseudosection.plot(); install it with "
                "`pip install magemin[plot]`"
            ) from exc

        if figsize is None:
            figsize = (8.0, 6.0)
        fig, ax = plt.subplots(figsize=figsize, layout="constrained")

        swap = self.kind in ("PT", "PX")
        if swap:
            x_label, y_label = self.axis2_label, self.axis1_label
            x_range, y_range = self.axis2_range, self.axis1_range
        else:
            x_label, y_label = self.axis1_label, self.axis2_label
            x_range, y_range = self.axis1_range, self.axis2_range

        fields: dict[tuple[str, ...], list[MeshPoint]] = {}
        for point in self.points:
            if point.assemblage is not None:
                fields.setdefault(point.assemblage, []).append(point)

        colormap = mpl.colormaps[cmap]
        for i, assemblage in enumerate(sorted(fields)):
            points = fields[assemblage]
            xs = [p.axis2 if swap else p.axis1 for p in points]
            ys = [p.axis1 if swap else p.axis2 for p in points]
            color = colormap(i % _N_COLORS)
            marker = _MARKERS[(i // _N_COLORS) % len(_MARKERS)]
            ax.scatter(
                xs,
                ys,
                s=marker_size,
                alpha=alpha,
                color=color,
                marker=marker,
                label=" ".join(assemblage),
            )

        ax.set_xlim(*x_range)
        ax.set_ylim(*y_range)
        ax.set_xlabel(x_label)
        ax.set_ylabel(y_label)
        title = f"{self.kind} pseudosection ({self.database})"
        if self.fixed_label:
            title += f", {self.fixed_label}"
        ax.set_title(title)

        if legend and fields:
            fig.legend(loc=legend_loc, fontsize=legend_fontsize, frameon=False)

        return fig

    def show(self, **kwargs: object) -> None:
        """Render this pseudosection with `plot()` and immediately display it.

        Creates a new figure, calls `plot(**kwargs)`, then `plt.show()`. Requires the optional
        `matplotlib` extra (`pip install magemin[plot]`).

        Args:
            **kwargs: Passed through to `plot()`.

        Raises:
            MAGEMinPlottingError: If matplotlib is not installed.
        """
        try:
            import matplotlib.pyplot as plt
        except ImportError as exc:
            raise MAGEMinPlottingError(
                "matplotlib is required for Pseudosection.show(); install it with "
                "`pip install magemin[plot]`"
            ) from exc

        self.plot(**kwargs)
        plt.show()
