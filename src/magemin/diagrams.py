"""Adaptively refined PT, PX, and TX stable-phase-assemblage diagrams.

Built on top of `magemin.multi_point_minimization`: a 2D grid over two of
{pressure, temperature, bulk-composition-interpolation-fraction} is refined
by subdividing cells whose 4 corners disagree on the stable phase assemblage,
stopping once each cell is either uniform or has hit `max_depth`. See
`magemin._diagrams` for the refinement engine and its relationship to
MAGEMin_C.jl's `AMR.jl`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from magemin import _diagrams
from magemin._diagrams import _LatticePoint
from magemin.bulk_rocks import BulkRock
from magemin.core import MAGEMin, multi_point_minimization
from magemin.errors import MAGEMinPlottingError
from magemin.results import EquilibriumResult

if TYPE_CHECKING:
    import matplotlib.figure

_Corners = tuple[tuple[float, float], tuple[float, float], tuple[float, float], tuple[float, float]]


@dataclass(frozen=True, slots=True)
class DiagramPoint:
    """One computed lattice point in a `PhaseDiagram`.

    Attributes:
        axis1: Value along the diagram's first axis (P in kbar / T in Celsius
            / X in `[0, 1]`).
        axis2: Value along the diagram's second axis.
        result: The computed equilibrium result at this point.
    """

    axis1: float
    axis2: float
    result: EquilibriumResult


@dataclass(frozen=True, slots=True)
class DiagramCell:
    """One leaf quadtree cell of a resolved `PhaseDiagram` mesh.

    Attributes:
        corners: The cell's 4 corners as `(axis1, axis2)` pairs,
            counter-clockwise from bottom-left: `(min1, min2)`,
            `(max1, min2)`, `(max1, max2)`, `(min1, max2)`.
        lattice_corners: The same 4 corners as exact integer `(i, j)` lattice
            coordinates, `0 <= i, j <= 2 ** PhaseDiagram.max_depth` -- what
            `PhaseDiagram.validate()` uses for exact-integer cell adjacency.
        depth: Refinement depth this cell was finalized at.
        resolved: True if all 4 corners share one stable-phase assemblage.
            False if the cell still straddles a boundary at `max_depth` (an
            unresolved boundary leaf, not infinitely recursed).
        assemblage: Sorted shared phase-name tuple when `resolved`; `None`
            otherwise.
    """

    corners: _Corners
    lattice_corners: tuple[_LatticePoint, _LatticePoint, _LatticePoint, _LatticePoint]
    depth: int
    resolved: bool
    assemblage: tuple[str, ...] | None


@dataclass(frozen=True, slots=True)
class PhaseDiagram:
    """An adaptively refined PT, PX, or TX stable-phase-assemblage diagram.

    Construct via `PhaseDiagram.pt`/`.px`/`.tx` -- not directly.

    Attributes:
        kind: Which two parameters vary: `"PT"`, `"PX"`, or `"TX"`.
        database: The database acronym this diagram was computed with.
        axis1_label: Human-readable label for the first (horizontal) axis.
        axis2_label: Human-readable label for the second (vertical) axis.
        axis1_range: Physical `(min, max)` range of the first axis.
        axis2_range: Physical `(min, max)` range of the second axis.
        fixed_label: Human-readable description of the held-fixed parameter
            (e.g. `"T = 900 °C"`) for PX/TX diagrams; `None` for PT.
        fixed_value: The raw held-fixed value (`T` for PX, `P` for TX) `fixed_label`
            describes; `None` for PT. Lets callers use the value programmatically
            without parsing it back out of `fixed_label`'s formatted string.
        points: Every computed lattice point, in ascending lattice order.
        cells: The finalized quadtree leaf cells making up the diagram mesh.
        n_components: Number of independent system components (the
            database's oxide count). Used by `plot()` to compute each
            assemblage's Gibbs-phase-rule variance, `n_components -
            len(assemblage) + 2`.
        max_depth: Maximum quadtree refinement depth this diagram was
            computed with. `cells[i].lattice_corners` coordinates range over
            `0 <= i, j <= 2 ** max_depth`. Used by `validate()`.
        initial_resolution: The `initial_resolution` this diagram was
            computed with. Used by `refine()` to reproduce the same starting
            grid before continuing past `max_depth`.
        solver: The `solver` this diagram was computed with. Used by
            `refine()` so newly computed points stay consistent with the
            rest of the diagram.
    """

    kind: Literal["PT", "PX", "TX"]
    database: str
    axis1_label: str
    axis2_label: str
    axis1_range: tuple[float, float]
    axis2_range: tuple[float, float]
    fixed_label: str | None
    fixed_value: float | None
    points: tuple[DiagramPoint, ...]
    cells: tuple[DiagramCell, ...]
    n_components: int
    max_depth: int
    initial_resolution: int
    solver: int
    # Not part of the public contract (hence no Attributes: entry above): the
    # normalized-to-physical mapping (including the to_point closure covering
    # bulk/buffer/suppress_phases/etc, none of which are otherwise retained on
    # this dataclass) needed to compute further points in refine().
    _mapping: _diagrams._AxisMapping = field(repr=False)

    def __str__(self) -> str:
        """Return a human-readable summary."""
        resolved = sum(1 for cell in self.cells if cell.resolved)
        n_assemblages = len({cell.assemblage for cell in self.cells if cell.resolved})
        lines = [f"{self.kind} diagram ({self.database})"]
        if self.fixed_label:
            lines.append(f"  Fixed                : {self.fixed_label}")
        lines.append(f"  {self.axis1_label:<21}: {self.axis1_range[0]:g} - {self.axis1_range[1]:g}")
        lines.append(f"  {self.axis2_label:<21}: {self.axis2_range[0]:g} - {self.axis2_range[1]:g}")
        lines.append(
            f"  Refinement           : initial_resolution={self.initial_resolution}, "
            f"max_depth={self.max_depth}, solver={self.solver}"
        )
        lines.append(f"  Points computed      : {len(self.points)}")
        lines.append(
            f"  Mesh cells           : {len(self.cells)} "
            f"({resolved} resolved, {len(self.cells) - resolved} unresolved)"
        )
        lines.append(f"  Distinct assemblages : {n_assemblages}")
        return "\n".join(lines)

    @classmethod
    def _from_leaves(
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
        max_depth: int,
        solver: int,
        n_components: int,
        leaves: list[_diagrams._ResolvedCell],
        cache: dict[_LatticePoint, EquilibriumResult],
    ) -> PhaseDiagram:
        """Assemble a `PhaseDiagram` from a `_diagrams.refine()` result.

        Shared by `_construct` (a fresh diagram) and `refine` (continuing an existing one).
        """
        n = 2**max_depth
        points = tuple(
            DiagramPoint(*mapping.physical(i / n, j / n), result)
            for (i, j), result in sorted(cache.items())
        )
        cells = tuple(
            DiagramCell(
                corners=leaf.corners,
                lattice_corners=leaf.lattice_corners,
                depth=leaf.depth,
                resolved=leaf.resolved,
                assemblage=leaf.assemblage,
            )
            for leaf in leaves
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
            cells=cells,
            n_components=n_components,
            max_depth=max_depth,
            initial_resolution=initial_resolution,
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
        max_depth: int,
        max_workers: int | None,
        verbose: bool,
        solver: int,
    ) -> PhaseDiagram:
        with MAGEMin(database, solver=solver) as mg:
            n_components = mg.n_oxides

        leaves, cache = _diagrams.refine(
            database,
            mapping,
            initial_resolution=initial_resolution,
            max_depth=max_depth,
            max_workers=max_workers,
            verbose=verbose,
            solver=solver,
            batch_fn=multi_point_minimization,
        )
        return cls._from_leaves(
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
            max_depth=max_depth,
            solver=solver,
            n_components=n_components,
            leaves=leaves,
            cache=cache,
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
        max_workers: int | None = None,
        verbose: bool = False,
        solver: int = 2,
    ) -> PhaseDiagram:
        """Compute an adaptive pressure-temperature diagram at fixed bulk composition.

        Args:
            database: Database acronym, as for `MAGEMin(database)`.
            P: Pressure range `(min, max)` in kbar.
            T: Temperature range `(min, max)` in Celsius.
            bulk: Bulk composition, as for `MAGEMin.compute`.
            sys_in: Composition unit, as for `MAGEMin.compute`.
            buffer: As for `MAGEMin.compute`.
            buffer_value: As for `MAGEMin.compute`.
            suppress_phases: As for `MAGEMin.compute`.
            light: As for `MAGEMin.compute`; defaults to `True` here since the
                refiner only ever reads `.ph`.
            name_solvus: As for `MAGEMin.compute` (defaults to `True` there
                too) -- the corner-comparison refinement criterion depends on
                solvus-disambiguated phase names to detect real solvus
                boundaries (see `magemin.solvus_name`).
            initial_resolution: The starting grid is `2 ** initial_resolution`
                cells per axis.
            refine: Number of quadtree refinement steps beyond `initial_resolution`
                (must be `>= 0`). Defaults to `0` -- a plain uniform grid with no
                adaptive refinement -- so pass a positive value to actually refine.
            max_workers: As for `multi_point_minimization`.
            verbose: As for `multi_point_minimization`.
            solver: As for `MAGEMin.__init__`.

        Returns:
            The computed diagram.
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
            max_depth=initial_resolution + refine,
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
        max_workers: int | None = None,
        verbose: bool = False,
        solver: int = 2,
    ) -> PhaseDiagram:
        """Compute an adaptive pressure-composition diagram at fixed temperature.

        `X` is a bulk-composition interpolation fraction in `[0, 1]`: `X=0` is
        `bulk_a`, `X=1` is `bulk_b`, linearly interpolated per-oxide in
        between.

        Args:
            database: Database acronym, as for `MAGEMin(database)`.
            P: Pressure range `(min, max)` in kbar.
            T: Fixed temperature in Celsius.
            bulk_a: Bulk composition at `X=0`.
            bulk_b: Bulk composition at `X=1`; must share `bulk_a`'s oxide
                set/order (and `sys_in`, unless `sys_in` is given explicitly).
            sys_in: Composition unit. Required unless `bulk_a`/`bulk_b` are
                both `BulkRock` instances with a matching `sys_in`.
            buffer: As for `MAGEMin.compute`.
            buffer_value: As for `MAGEMin.compute`.
            suppress_phases: As for `MAGEMin.compute`.
            light: As for `PhaseDiagram.pt`.
            name_solvus: As for `PhaseDiagram.pt`.
            initial_resolution: As for `PhaseDiagram.pt`.
            refine: As for `PhaseDiagram.pt`.
            max_workers: As for `multi_point_minimization`.
            verbose: As for `multi_point_minimization`.
            solver: As for `MAGEMin.__init__`.

        Returns:
            The computed diagram.
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
            max_depth=initial_resolution + refine,
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
        max_workers: int | None = None,
        verbose: bool = False,
        solver: int = 2,
    ) -> PhaseDiagram:
        """Compute an adaptive temperature-composition diagram at fixed pressure.

        `X` is a bulk-composition interpolation fraction in `[0, 1]`: `X=0` is
        `bulk_a`, `X=1` is `bulk_b`, linearly interpolated per-oxide in
        between.

        Args:
            database: Database acronym, as for `MAGEMin(database)`.
            P: Fixed pressure in kbar.
            T: Temperature range `(min, max)` in Celsius.
            bulk_a: Bulk composition at `X=0`.
            bulk_b: Bulk composition at `X=1`; must share `bulk_a`'s oxide
                set/order (and `sys_in`, unless `sys_in` is given explicitly).
            sys_in: Composition unit. Required unless `bulk_a`/`bulk_b` are
                both `BulkRock` instances with a matching `sys_in`.
            buffer: As for `MAGEMin.compute`.
            buffer_value: As for `MAGEMin.compute`.
            suppress_phases: As for `MAGEMin.compute`.
            light: As for `PhaseDiagram.pt`.
            name_solvus: As for `PhaseDiagram.pt`.
            initial_resolution: As for `PhaseDiagram.pt`.
            refine: As for `PhaseDiagram.pt`.
            max_workers: As for `multi_point_minimization`.
            verbose: As for `multi_point_minimization`.
            solver: As for `MAGEMin.__init__`.

        Returns:
            The computed diagram.
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
            max_depth=initial_resolution + refine,
            max_workers=max_workers,
            verbose=verbose,
            solver=solver,
        )

    def plot(
        self,
        *,
        figsize: tuple[float, float] | None = None,
        cmap: str = "Blues",
        show_unresolved: bool = True,
        unresolved_facecolor: str = "lightgray",
        unresolved_edgecolor: str = "dimgray",
        unresolved_hatch: str = "//",
        annotate: bool = True,
        annotate_fontsize: float = 6,
        annotate_color: str = "black",
        annotate_stroke_color: str = "white",
        annotate_stroke_width: float = 2.5,
        legend: bool = True,
        legend_loc: str = "outside right upper",
        legend_fontsize: str | float = "small",
        colorbar: bool = True,
        colorbar_label: str = "variance",
    ) -> matplotlib.figure.Figure:
        """Render this diagram as a matplotlib assemblage map.

        Pressure is always plotted on the vertical axis and temperature
        always on the horizontal axis, when either is present (PT: T
        horizontal / P vertical; PX: X horizontal / P vertical; TX: T
        horizontal / X vertical) -- the diagram's own `axis1`/`axis2` fields
        are unaffected by this, only the rendered orientation.

        Each resolved field is colored by its assemblage's Gibbs-phase-rule
        variance (`n_components - len(assemblage) + 2`) via `cmap`, numbered
        at the centroid of its largest cell, and listed in a numbered,
        color-swatch-free legend. Requires the optional `matplotlib`
        dependency (`pip install magemin[plot]`).

        Args:
            figsize: Figure size in inches; `None` (default) auto-sizes based on whether
                `colorbar` is drawn (wider to leave room for it and the legend).
            cmap: Matplotlib sequential colormap name used to color resolved
                cells by their assemblage's variance.
            show_unresolved: Whether to draw cells that never fully resolved
                by `max_depth` rather than omitting them.
            unresolved_facecolor: Fill color for unresolved cells.
            unresolved_edgecolor: Edge color for unresolved cells.
            unresolved_hatch: Hatch pattern for unresolved cells.
            annotate: Whether to number each resolved field at the centroid
                of its largest cell.
            annotate_fontsize: Font size for field-number annotations.
            annotate_color: Fill color for field-number annotation text.
            annotate_stroke_color: Outline color drawn around annotation
                text, so numbers stay legible over both light and dark
                field colors.
            annotate_stroke_width: Outline width for annotation text; `0`
                disables the outline.
            legend: Whether to draw the numbered assemblage legend.
            legend_loc: `loc` passed to `Figure.legend` -- an "outside" location string
                (e.g. `"outside right upper"`) so matplotlib's constrained-layout engine
                automatically reserves space for it (and for the colorbar, if drawn) with
                no manual offset tuning needed.
            legend_fontsize: `fontsize` passed to `Axes.legend`.
            colorbar: Whether to draw a colorbar mapping `cmap` to variance.
            colorbar_label: Label for the colorbar.

        Returns:
            The created figure.

        Raises:
            MAGEMinPlottingError: If matplotlib is not installed.
        """
        try:
            import matplotlib as mpl
            import matplotlib.patheffects as patheffects
            import matplotlib.pyplot as plt
            from matplotlib.patches import Patch, Polygon
            from matplotlib.ticker import MaxNLocator
        except ImportError as exc:
            raise MAGEMinPlottingError(
                "matplotlib is required for PhaseDiagram.plot(); install it with "
                "`pip install magemin[plot]`"
            ) from exc

        if figsize is None:
            width_factor = 1.30 if colorbar else 1.25
            figsize = (6.4 * width_factor, 4.8)
        fig, ax = plt.subplots(figsize=figsize, layout="constrained")

        swap = self.kind in ("PT", "PX")
        if swap:
            x_label, y_label = self.axis2_label, self.axis1_label
            x_range, y_range = self.axis2_range, self.axis1_range
        else:
            x_label, y_label = self.axis1_label, self.axis2_label
            x_range, y_range = self.axis1_range, self.axis2_range

        def to_xy(
            corners: _Corners,
        ) -> list[tuple[float, float]]:
            return [(c[1], c[0]) if swap else (c[0], c[1]) for c in corners]

        resolved = [cell for cell in self.cells if cell.resolved]
        assemblages = sorted({cell.assemblage for cell in resolved})
        numbers = {assemblage: i + 1 for i, assemblage in enumerate(assemblages)}

        def variance(assemblage: tuple[str, ...]) -> int:
            return self.n_components - len(assemblage) + 2

        variances = {variance(a) for a in assemblages}
        vmin, vmax = (min(variances), max(variances)) if variances else (0, 1)
        if vmin == vmax:
            vmin, vmax = vmin - 1, vmax + 1
        norm = mpl.colors.Normalize(vmin=vmin, vmax=vmax)
        colormap = mpl.colormaps[cmap]

        def area(corners: _Corners) -> float:
            xs = [c[0] for c in corners]
            ys = [c[1] for c in corners]
            return abs(sum(xs[i] * ys[(i + 1) % 4] - xs[(i + 1) % 4] * ys[i] for i in range(4))) / 2

        largest_cell: dict[tuple[str, ...], tuple[float, DiagramCell]] = {}
        for cell in resolved:
            cell_area = area(cell.corners)
            current = largest_cell.get(cell.assemblage)
            if current is None or cell_area > current[0]:
                largest_cell[cell.assemblage] = (cell_area, cell)

        any_unresolved = False
        for cell in self.cells:
            points_xy = to_xy(cell.corners)
            if cell.resolved:
                ax.add_patch(
                    Polygon(
                        points_xy, closed=True, facecolor=colormap(norm(variance(cell.assemblage)))
                    )
                )
            elif show_unresolved:
                any_unresolved = True
                ax.add_patch(
                    Polygon(
                        points_xy,
                        closed=True,
                        facecolor=unresolved_facecolor,
                        hatch=unresolved_hatch,
                        edgecolor=unresolved_edgecolor,
                    )
                )

        if annotate:
            stroke = (
                [
                    patheffects.withStroke(
                        linewidth=annotate_stroke_width, foreground=annotate_stroke_color
                    )
                ]
                if annotate_stroke_width > 0
                else None
            )
            for assemblage, (_, cell) in largest_cell.items():
                points_xy = to_xy(cell.corners)
                cx = sum(p[0] for p in points_xy) / 4
                cy = sum(p[1] for p in points_xy) / 4
                ax.text(
                    cx,
                    cy,
                    str(numbers[assemblage]),
                    ha="center",
                    va="center",
                    fontsize=annotate_fontsize,
                    color=annotate_color,
                    path_effects=stroke,
                )

        ax.set_xlim(*x_range)
        ax.set_ylim(*y_range)
        ax.set_xlabel(x_label)
        ax.set_ylabel(y_label)
        title = f"{self.kind} diagram ({self.database})"
        if self.fixed_label:
            title += f", {self.fixed_label}"
        ax.set_title(title)

        # matplotlib's constrained-layout engine (enabled above) automatically arranges the
        # colorbar and legend around `ax` regardless of the order they're added in.
        if colorbar:
            sm = mpl.cm.ScalarMappable(norm=norm, cmap=colormap)
            sm.set_array([])
            cb = fig.colorbar(sm, ax=ax, label=colorbar_label, fraction=0.046, pad=0.04)
            cb.locator = MaxNLocator(integer=True)
            cb.update_ticks()

        if legend:
            handles = [
                Patch(facecolor="none", edgecolor="none", label=f"{numbers[a]}: {'+'.join(a)}")
                for a in assemblages
            ]
            if any_unresolved:
                handles.append(
                    Patch(facecolor="none", edgecolor="none", label="unresolved (hatched)")
                )
            fig.legend(
                handles=handles,
                loc=legend_loc,
                fontsize=legend_fontsize,
                handlelength=0,
                handletextpad=0,
                frameon=False,
            )

        return fig

    def plot_grid(
        self,
        *,
        figsize: tuple[float, float] | None = None,
        cmap: str = "viridis",
        facecolor: str | None = None,
        edgecolor: str = "black",
        linewidth: float = 0.5,
        unresolved: bool = False,
        unresolved_hatch: str = "//",
        colorbar: bool = True,
        colorbar_label: str = "depth",
    ) -> matplotlib.figure.Figure:
        """Render this diagram's current quadtree mesh cells, colored by refinement depth.

        Draws the raw mesh geometry -- every cell's outline, regardless of resolved/
        unresolved status or stable assemblage -- which `plot()` doesn't otherwise show
        directly. Useful for seeing where adaptive refinement concentrated: deeper
        (smaller) cells cluster near phase boundaries. Same P-vertical/T-horizontal
        axis convention as `plot()`. Requires the optional `matplotlib` extra (`pip
        install magemin[plot]`).

        Args:
            figsize: Figure size in inches; `None` (default) auto-sizes based on whether
                `colorbar` is drawn (wider to leave room for it).
            cmap: Matplotlib sequential colormap name used to color cells by depth.
                Ignored if `facecolor` is given.
            facecolor: If given, every cell is filled with this single color instead
                of being colored by depth, and no colorbar is drawn.
            edgecolor: Cell outline color.
            linewidth: Cell outline width.
            unresolved: Whether cells that never fully resolved by `max_depth` are
                additionally hatched, on top of their usual depth/`facecolor` fill, so
                they stand out from resolved cells at the same depth.
            unresolved_hatch: Hatch pattern for unresolved cells. Ignored if
                `unresolved` is `False`.
            colorbar: Whether to draw a colorbar mapping `cmap` to depth. Ignored if
                `facecolor` is given.
            colorbar_label: Label for the colorbar.

        Returns:
            The created figure.

        Raises:
            MAGEMinPlottingError: If matplotlib is not installed.
        """
        try:
            import matplotlib as mpl
            import matplotlib.pyplot as plt
            from matplotlib.patches import Polygon
            from matplotlib.ticker import MaxNLocator
        except ImportError as exc:
            raise MAGEMinPlottingError(
                "matplotlib is required for PhaseDiagram.plot_grid(); install it with "
                "`pip install magemin[plot]`"
            ) from exc

        if figsize is None:
            width_factor = 1.30 if (colorbar and facecolor is None) else 1.25
            figsize = (6.4 * width_factor, 4.8)
        fig, ax = plt.subplots(figsize=figsize, layout="constrained")

        swap = self.kind in ("PT", "PX")
        if swap:
            x_label, y_label = self.axis2_label, self.axis1_label
            x_range, y_range = self.axis2_range, self.axis1_range
        else:
            x_label, y_label = self.axis1_label, self.axis2_label
            x_range, y_range = self.axis1_range, self.axis2_range

        def to_xy(corners: _Corners) -> list[tuple[float, float]]:
            return [(c[1], c[0]) if swap else (c[0], c[1]) for c in corners]

        depths = [cell.depth for cell in self.cells]
        dmin, dmax = (min(depths), max(depths)) if depths else (0, 1)
        if dmin == dmax:
            dmin, dmax = dmin - 1, dmax + 1
        norm = mpl.colors.Normalize(vmin=dmin, vmax=dmax)
        colormap = mpl.colormaps[cmap]

        for cell in self.cells:
            points_xy = to_xy(cell.corners)
            cell_facecolor = colormap(norm(cell.depth)) if facecolor is None else facecolor
            hatch = unresolved_hatch if unresolved and not cell.resolved else None
            ax.add_patch(
                Polygon(
                    points_xy,
                    closed=True,
                    facecolor=cell_facecolor,
                    edgecolor=edgecolor,
                    linewidth=linewidth,
                    hatch=hatch,
                )
            )

        ax.set_xlim(*x_range)
        ax.set_ylim(*y_range)
        ax.set_xlabel(x_label)
        ax.set_ylabel(y_label)
        title = f"{self.kind} diagram mesh ({self.database})"
        if self.fixed_label:
            title += f", {self.fixed_label}"
        ax.set_title(title)

        if colorbar and facecolor is None:
            sm = mpl.cm.ScalarMappable(norm=norm, cmap=colormap)
            sm.set_array([])
            cb = fig.colorbar(sm, ax=ax, label=colorbar_label, fraction=0.046, pad=0.04)
            cb.locator = MaxNLocator(integer=True)
            cb.update_ticks()

        return fig

    def show(self, **kwargs: object) -> None:
        """Render this diagram with `plot()` and immediately display it.

        Creates a new figure, calls `plot(**kwargs)`, then `plt.show()`.
        Requires the optional `matplotlib` extra (`pip install magemin[plot]`).

        Args:
            **kwargs: Passed through to `plot()`.

        Raises:
            MAGEMinPlottingError: If matplotlib is not installed.
        """
        try:
            import matplotlib.pyplot as plt
        except ImportError as exc:
            raise MAGEMinPlottingError(
                "matplotlib is required for PhaseDiagram.show(); install it with "
                "`pip install magemin[plot]`"
            ) from exc

        self.plot(**kwargs)
        plt.show()

    def show_grid(self, **kwargs: object) -> None:
        """Render this diagram's mesh with `plot_grid()` and immediately display it.

        Creates a new figure, calls `plot_grid(**kwargs)`, then `plt.show()`.
        Requires the optional `matplotlib` extra (`pip install magemin[plot]`).

        Args:
            **kwargs: Passed through to `plot_grid()`.

        Raises:
            MAGEMinPlottingError: If matplotlib is not installed.
        """
        try:
            import matplotlib.pyplot as plt
        except ImportError as exc:
            raise MAGEMinPlottingError(
                "matplotlib is required for PhaseDiagram.show_grid(); install it with "
                "`pip install magemin[plot]`"
            ) from exc

        self.plot_grid(**kwargs)
        plt.show()

    def refine(
        self,
        *,
        refine: int = 1,
        max_workers: int | None = None,
        verbose: bool = False,
    ) -> PhaseDiagram:
        """Refine this diagram by further quadtree levels, reusing every already-computed point.

        Every point this diagram already holds is rescaled onto the new, finer lattice and
        seeded into the refinement engine's point cache, so continuing past the current
        `max_depth` never recomputes an already-known point -- only the genuinely new, deeper
        corners are computed. This instance is left unchanged; a new `PhaseDiagram` is returned.

        Args:
            refine: Number of additional refinement steps beyond this diagram's current
                `max_depth` (must be `>= 1`). Defaults to `1` (one further refinement round).
            max_workers: As for `multi_point_minimization`.
            verbose: As for `multi_point_minimization`.

        Returns:
            The more deeply refined diagram.

        Raises:
            ValueError: If `refine` is not a positive integer.
        """
        if refine < 1:
            raise ValueError(f"refine ({refine}) must be a positive integer")
        new_max_depth = self.max_depth + refine

        physical_to_lattice: dict[tuple[float, float], _LatticePoint] = {}
        for cell in self.cells:
            physical_to_lattice.update(zip(cell.corners, cell.lattice_corners, strict=True))

        scale = 2 ** (new_max_depth - self.max_depth)
        initial_cache: dict[_LatticePoint, EquilibriumResult] = {}
        for point in self.points:
            old_i, old_j = physical_to_lattice[(point.axis1, point.axis2)]
            initial_cache[(old_i * scale, old_j * scale)] = point.result

        leaves, cache = _diagrams.refine(
            self.database,
            self._mapping,
            initial_resolution=self.initial_resolution,
            max_depth=new_max_depth,
            max_workers=max_workers,
            verbose=verbose,
            solver=self.solver,
            batch_fn=multi_point_minimization,
            initial_cache=initial_cache,
        )
        return PhaseDiagram._from_leaves(
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
            max_depth=new_max_depth,
            solver=self.solver,
            n_components=self.n_components,
            leaves=leaves,
            cache=cache,
        )

    def validate(self) -> bool:
        """Check that every pair of nearby, resolved cells forms a legitimate boundary.

        "Nearby" means directly adjacent (sharing a lattice edge), or adjacent through exactly
        one shared unresolved buffer cell -- a real boundary between two different resolved
        fields almost always leaves at least one still-unresolved cell straddling it, so
        bridging one such cell is what lets this reach the diagram's real reaction-line network.
        Two such resolved cells with different assemblages must differ either by exactly one
        phase (an ordinary zero-mode univariant crossing) or by one phase on each side that are
        polymorphs of each other (e.g. `ky`/`sill`). Cells sharing the same assemblage are
        skipped rather than checked -- this validates mesh structure only where the mesh
        actually reached a decision on both sides, not full Schreinemakers rigor (no
        invariant-point/angular-ordering analysis).

        Returns:
            Whether every such nearby resolved pair is a clean boundary or a polymorph swap.
        """
        return _diagrams.validate_diagram(self.cells)
