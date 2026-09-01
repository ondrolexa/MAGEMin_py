"""Tests for `PhaseDiagram.plot()` (the optional `matplotlib` extra)."""

import sys

import pytest

from magemin import _diagrams
from magemin.diagrams import DiagramCell, PhaseDiagram
from magemin.errors import MAGEMinPlottingError


def _dummy_mapping(axis1_range, axis2_range) -> _diagrams._AxisMapping:
    return _diagrams._AxisMapping(
        axis1_range=axis1_range, axis2_range=axis2_range, to_point=lambda u, v: None
    )


def _fake_diagram() -> PhaseDiagram:
    cells = (
        DiagramCell(
            corners=((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)),
            lattice_corners=((0, 0), (1, 0), (1, 1), (0, 1)),
            depth=1,
            resolved=True,
            assemblage=("ol", "opx"),
        ),
        DiagramCell(
            corners=((1.0, 0.0), (2.0, 0.0), (2.0, 1.0), (1.0, 1.0)),
            lattice_corners=((1, 0), (2, 0), (2, 1), (1, 1)),
            depth=1,
            resolved=False,
            assemblage=None,
        ),
    )
    return PhaseDiagram(
        kind="PT",
        database="ig",
        axis1_label="P [kbar]",
        axis2_label="T [°C]",
        axis1_range=(0.0, 2.0),
        axis2_range=(0.0, 1.0),
        fixed_label=None,
        fixed_value=None,
        points=(),
        cells=cells,
        n_components=11,
        max_depth=1,
        initial_resolution=1,
        solver=2,
        _mapping=_dummy_mapping((0.0, 2.0), (0.0, 1.0)),
    )


def _oriented_diagram(kind: str) -> PhaseDiagram:
    """A single-cell diagram spanning axis1=(5,10), axis2=(600,700), for axis-orientation checks."""
    cell = DiagramCell(
        corners=((5.0, 600.0), (10.0, 600.0), (10.0, 700.0), (5.0, 700.0)),
        lattice_corners=((0, 0), (1, 0), (1, 1), (0, 1)),
        depth=0,
        resolved=True,
        assemblage=("bi", "g"),
    )
    axis1_label, axis2_label = {
        "PT": ("P [kbar]", "T [°C]"),
        "PX": ("P [kbar]", "X"),
        "TX": ("T [°C]", "X"),
    }[kind]
    return PhaseDiagram(
        kind=kind,
        database="mp",
        axis1_label=axis1_label,
        axis2_label=axis2_label,
        axis1_range=(5.0, 10.0),
        axis2_range=(600.0, 700.0),
        fixed_label=None,
        fixed_value=None,
        points=(),
        cells=(cell,),
        n_components=11,
        max_depth=0,
        initial_resolution=0,
        solver=2,
        _mapping=_dummy_mapping((5.0, 10.0), (600.0, 700.0)),
    )


def test_plot_renders_without_error(require_matplotlib):
    fig = _fake_diagram().plot()
    assert fig is not None


def test_plot_hides_unresolved_cells_when_disabled(require_matplotlib):
    fig = _fake_diagram().plot(show_unresolved=False)
    ax = fig.axes[0]
    assert len(ax.patches) == 1


def test_plot_unresolved_styling_kwargs_apply(require_matplotlib):
    fig = _fake_diagram().plot(
        unresolved_facecolor="red", unresolved_edgecolor="blue", unresolved_hatch="xx"
    )
    unresolved_patch = fig.axes[0].patches[1]
    assert unresolved_patch.get_hatch() == "xx"


def test_plot_annotate_adds_one_label_per_resolved_assemblage(require_matplotlib):
    fig = _fake_diagram().plot(annotate=True)
    ax = fig.axes[0]
    assert len(ax.texts) == 1
    assert ax.texts[0].get_text() == "1"


def test_plot_annotate_disabled_adds_no_labels(require_matplotlib):
    fig = _fake_diagram().plot(annotate=False)
    assert len(fig.axes[0].texts) == 0


def test_plot_legend_is_numbered_with_no_color_patches(require_matplotlib):
    fig = _fake_diagram().plot(legend=True)
    # A figure-level legend (Figure.legend(), placed via an "outside" loc so matplotlib's
    # constrained layout can reserve space for it) -- not an axes-level one.
    legend = fig.legends[0]
    assert legend is not None
    labels = [text.get_text() for text in legend.get_texts()]
    assert labels[0] == "1: ol+opx"
    assert labels[1] == "unresolved (hatched)"
    for handle in legend.legend_handles:
        assert handle.get_facecolor()[3] == 0  # fully transparent -- no visible patch


def test_plot_colorbar_default_adds_a_second_axes(require_matplotlib):
    fig = _fake_diagram().plot(colorbar=True)
    assert len(fig.axes) == 2


def test_plot_legend_does_not_overlap_colorbar(require_matplotlib):
    # matplotlib's constrained-layout engine (enabled on the figure) plus an "outside" loc
    # (Figure.legend(loc="outside right upper")) automatically reserves non-overlapping space
    # for both the legend and the colorbar, with no manual offset tuning needed.
    fig = _fake_diagram().plot()
    fig.canvas.draw()
    legend_bbox = fig.legends[0].get_window_extent()
    colorbar_bbox = fig.axes[1].get_window_extent()
    assert not legend_bbox.overlaps(colorbar_bbox)


def test_plot_colorbar_disabled_keeps_one_axes(require_matplotlib):
    fig = _fake_diagram().plot(colorbar=False)
    assert len(fig.axes) == 1


def test_plot_figsize_widens_more_with_colorbar(require_matplotlib):
    width_with_cb, height_with_cb = _fake_diagram().plot(colorbar=True).get_size_inches()
    width_without_cb, height_without_cb = _fake_diagram().plot(colorbar=False).get_size_inches()
    assert width_with_cb == pytest.approx(6.4 * 1.30)
    assert width_without_cb == pytest.approx(6.4 * 1.25)
    assert height_with_cb == pytest.approx(4.8)
    assert height_without_cb == pytest.approx(4.8)


def test_plot_figsize_override_is_respected(require_matplotlib):
    fig = _fake_diagram().plot(figsize=(10.0, 8.0))
    assert fig.get_size_inches() == pytest.approx((10.0, 8.0))


def test_plot_pt_orientation_is_temperature_horizontal_pressure_vertical(require_matplotlib):
    fig = _oriented_diagram("PT").plot()
    ax = fig.axes[0]
    assert ax.get_xlabel() == "T [°C]"
    assert ax.get_ylabel() == "P [kbar]"
    assert ax.get_xlim() == (600.0, 700.0)
    assert ax.get_ylim() == (5.0, 10.0)
    xs = [x for x, _ in ax.patches[0].get_xy()]
    ys = [y for _, y in ax.patches[0].get_xy()]
    assert set(xs) == {600.0, 700.0}
    assert set(ys) == {5.0, 10.0}


def test_plot_px_orientation_is_x_horizontal_pressure_vertical(require_matplotlib):
    fig = _oriented_diagram("PX").plot()
    ax = fig.axes[0]
    assert ax.get_xlabel() == "X"
    assert ax.get_ylabel() == "P [kbar]"
    assert ax.get_xlim() == (600.0, 700.0)
    assert ax.get_ylim() == (5.0, 10.0)


def test_plot_tx_orientation_is_temperature_horizontal_x_vertical(require_matplotlib):
    fig = _oriented_diagram("TX").plot()
    ax = fig.axes[0]
    assert ax.get_xlabel() == "T [°C]"
    assert ax.get_ylabel() == "X"
    assert ax.get_xlim() == (5.0, 10.0)
    assert ax.get_ylim() == (600.0, 700.0)


def test_plot_raises_without_matplotlib(monkeypatch):
    monkeypatch.setitem(sys.modules, "matplotlib", None)
    monkeypatch.setitem(sys.modules, "matplotlib.pyplot", None)
    monkeypatch.setitem(sys.modules, "matplotlib.patches", None)
    with pytest.raises(MAGEMinPlottingError, match=r"magemin\[plot\]"):
        _fake_diagram().plot()


def test_plot_grid_renders_without_error(require_matplotlib):
    fig = _fake_diagram().plot_grid()
    assert fig is not None


def test_plot_grid_draws_one_patch_per_cell(require_matplotlib):
    diagram = _fake_diagram()
    fig = diagram.plot_grid()
    assert len(fig.axes[0].patches) == len(diagram.cells)


def test_plot_grid_colors_cells_by_depth(require_matplotlib):
    cells = (
        DiagramCell(
            corners=((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)),
            lattice_corners=((0, 0), (1, 0), (1, 1), (0, 1)),
            depth=1,
            resolved=True,
            assemblage=("ol",),
        ),
        DiagramCell(
            corners=((1.0, 0.0), (2.0, 0.0), (2.0, 1.0), (1.0, 1.0)),
            lattice_corners=((1, 0), (2, 0), (2, 1), (1, 1)),
            depth=3,
            resolved=True,
            assemblage=("ol",),
        ),
    )
    diagram = PhaseDiagram(
        kind="PT",
        database="ig",
        axis1_label="P [kbar]",
        axis2_label="T [°C]",
        axis1_range=(0.0, 2.0),
        axis2_range=(0.0, 1.0),
        fixed_label=None,
        fixed_value=None,
        points=(),
        cells=cells,
        n_components=11,
        max_depth=3,
        initial_resolution=1,
        solver=2,
        _mapping=_dummy_mapping((0.0, 2.0), (0.0, 1.0)),
    )
    ax = diagram.plot_grid().axes[0]
    assert ax.patches[0].get_facecolor() != ax.patches[1].get_facecolor()


def test_plot_grid_facecolor_override_applies_to_every_cell(require_matplotlib):
    diagram = _fake_diagram()
    ax = diagram.plot_grid(facecolor="red").axes[0]
    for patch in ax.patches:
        assert patch.get_facecolor() == (1.0, 0.0, 0.0, 1.0)


def test_plot_grid_unresolved_defaults_to_no_hatching(require_matplotlib):
    ax = _fake_diagram().plot_grid().axes[0]
    assert all(patch.get_hatch() is None for patch in ax.patches)


def test_plot_grid_unresolved_hatches_only_unresolved_cells(require_matplotlib):
    diagram = _fake_diagram()  # cells[0] resolved, cells[1] unresolved
    ax = diagram.plot_grid(unresolved=True).axes[0]
    assert ax.patches[0].get_hatch() is None
    assert ax.patches[1].get_hatch() == "//"


def test_plot_grid_unresolved_hatch_pattern_is_configurable(require_matplotlib):
    diagram = _fake_diagram()
    ax = diagram.plot_grid(unresolved=True, unresolved_hatch="xx").axes[0]
    assert ax.patches[1].get_hatch() == "xx"


def test_plot_grid_colorbar_default_adds_a_second_axes(require_matplotlib):
    fig = _fake_diagram().plot_grid(colorbar=True)
    assert len(fig.axes) == 2


def test_plot_grid_colorbar_disabled_keeps_one_axes(require_matplotlib):
    fig = _fake_diagram().plot_grid(colorbar=False)
    assert len(fig.axes) == 1


def test_plot_grid_facecolor_override_skips_colorbar_even_if_requested(require_matplotlib):
    fig = _fake_diagram().plot_grid(facecolor="white", colorbar=True)
    assert len(fig.axes) == 1


def test_plot_grid_figsize_widens_more_with_colorbar(require_matplotlib):
    width_with_cb, _ = _fake_diagram().plot_grid(colorbar=True).get_size_inches()
    width_without_cb, _ = _fake_diagram().plot_grid(colorbar=False).get_size_inches()
    assert width_with_cb == pytest.approx(6.4 * 1.30)
    assert width_without_cb == pytest.approx(6.4 * 1.25)


def test_plot_grid_figsize_override_is_respected(require_matplotlib):
    fig = _fake_diagram().plot_grid(figsize=(10.0, 8.0))
    assert fig.get_size_inches() == pytest.approx((10.0, 8.0))


def test_plot_grid_pt_orientation_is_temperature_horizontal_pressure_vertical(require_matplotlib):
    fig = _oriented_diagram("PT").plot_grid()
    ax = fig.axes[0]
    assert ax.get_xlabel() == "T [°C]"
    assert ax.get_ylabel() == "P [kbar]"
    assert ax.get_xlim() == (600.0, 700.0)
    assert ax.get_ylim() == (5.0, 10.0)


def test_plot_grid_title_mentions_mesh(require_matplotlib):
    fig = _fake_diagram().plot_grid()
    assert "mesh" in fig.axes[0].get_title()


def test_plot_grid_raises_without_matplotlib(monkeypatch):
    monkeypatch.setitem(sys.modules, "matplotlib", None)
    monkeypatch.setitem(sys.modules, "matplotlib.pyplot", None)
    monkeypatch.setitem(sys.modules, "matplotlib.patches", None)
    with pytest.raises(MAGEMinPlottingError, match=r"magemin\[plot\]"):
        _fake_diagram().plot_grid()


def test_show_creates_a_figure_and_calls_plot(require_matplotlib, monkeypatch):
    import matplotlib.pyplot as plt

    shown = []
    monkeypatch.setattr(plt, "show", lambda: shown.append(True))

    n_figs_before = len(plt.get_fignums())
    _fake_diagram().show()
    assert len(plt.get_fignums()) == n_figs_before + 1
    assert shown == [True]


def test_show_passes_kwargs_through_to_plot(require_matplotlib, monkeypatch):
    import matplotlib.pyplot as plt

    from magemin.diagrams import PhaseDiagram

    monkeypatch.setattr(plt, "show", lambda: None)
    captured = {}
    original_plot = PhaseDiagram.plot

    def spy_plot(self, **kwargs):
        captured.update(kwargs)
        return original_plot(self, **kwargs)

    monkeypatch.setattr(PhaseDiagram, "plot", spy_plot)
    _fake_diagram().show(show_unresolved=False)
    assert captured["show_unresolved"] is False


def test_show_raises_without_matplotlib(monkeypatch):
    monkeypatch.setitem(sys.modules, "matplotlib", None)
    monkeypatch.setitem(sys.modules, "matplotlib.pyplot", None)
    monkeypatch.setitem(sys.modules, "matplotlib.patches", None)
    with pytest.raises(MAGEMinPlottingError, match=r"magemin\[plot\]"):
        _fake_diagram().show()


def test_show_grid_creates_a_figure_and_calls_plot_grid(require_matplotlib, monkeypatch):
    import matplotlib.pyplot as plt

    shown = []
    monkeypatch.setattr(plt, "show", lambda: shown.append(True))

    n_figs_before = len(plt.get_fignums())
    _fake_diagram().show_grid()
    assert len(plt.get_fignums()) == n_figs_before + 1
    assert shown == [True]


def test_show_grid_passes_kwargs_through_to_plot_grid(require_matplotlib, monkeypatch):
    import matplotlib.pyplot as plt

    from magemin.diagrams import PhaseDiagram

    monkeypatch.setattr(plt, "show", lambda: None)
    captured = {}
    original_plot_grid = PhaseDiagram.plot_grid

    def spy_plot_grid(self, **kwargs):
        captured.update(kwargs)
        return original_plot_grid(self, **kwargs)

    monkeypatch.setattr(PhaseDiagram, "plot_grid", spy_plot_grid)
    _fake_diagram().show_grid(facecolor="red")
    assert captured["facecolor"] == "red"


def test_show_grid_raises_without_matplotlib(monkeypatch):
    monkeypatch.setitem(sys.modules, "matplotlib", None)
    monkeypatch.setitem(sys.modules, "matplotlib.pyplot", None)
    monkeypatch.setitem(sys.modules, "matplotlib.patches", None)
    with pytest.raises(MAGEMinPlottingError, match=r"magemin\[plot\]"):
        _fake_diagram().show_grid()
