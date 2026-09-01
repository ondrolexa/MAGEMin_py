"""Tests for `Pseudosection.plot()` (the optional `matplotlib` extra)."""

import sys

import pytest

from magemin import _diagrams
from magemin.errors import MAGEMinPlottingError
from magemin.pseudosection import MeshPoint, Pseudosection


def _dummy_mapping(axis1_range, axis2_range) -> _diagrams._AxisMapping:
    return _diagrams._AxisMapping(
        axis1_range=axis1_range, axis2_range=axis2_range, to_point=lambda u, v: None
    )


def _fake_mesh() -> Pseudosection:
    points = (
        MeshPoint(axis1=5.0, axis2=700.0, result=None, assemblage=("ol", "opx")),
        MeshPoint(axis1=10.0, axis2=700.0, result=None, assemblage=("ol", "opx")),
        MeshPoint(axis1=5.0, axis2=900.0, result=None, assemblage=("cpx", "ol", "opx")),
        MeshPoint(axis1=10.0, axis2=900.0, result=None, assemblage=None),
    )
    edges = ((0, 1), (0, 2), (1, 3), (2, 3))
    return Pseudosection(
        kind="PT",
        database="ig",
        axis1_label="P [kbar]",
        axis2_label="T [°C]",
        axis1_range=(5.0, 10.0),
        axis2_range=(700.0, 900.0),
        fixed_label=None,
        fixed_value=None,
        points=points,
        edges=edges,
        converged=False,
        unresolved_boundaries=1,
        initial_resolution=1,
        rounds=1,
        solver=2,
        _mapping=_dummy_mapping((5.0, 10.0), (700.0, 900.0)),
    )


def _oriented_mesh(kind: str) -> Pseudosection:
    """A two-point mesh spanning axis1=(5,10), axis2=(600,700), for axis-orientation checks."""
    axis1_label, axis2_label = {
        "PT": ("P [kbar]", "T [°C]"),
        "PX": ("P [kbar]", "X"),
        "TX": ("T [°C]", "X"),
    }[kind]
    points = (
        MeshPoint(axis1=5.0, axis2=600.0, result=None, assemblage=("bi", "g")),
        MeshPoint(axis1=10.0, axis2=700.0, result=None, assemblage=("bi", "g")),
    )
    return Pseudosection(
        kind=kind,
        database="mp",
        axis1_label=axis1_label,
        axis2_label=axis2_label,
        axis1_range=(5.0, 10.0),
        axis2_range=(600.0, 700.0),
        fixed_label=None,
        fixed_value=None,
        points=points,
        edges=((0, 1),),
        converged=True,
        unresolved_boundaries=0,
        initial_resolution=0,
        rounds=0,
        solver=2,
        _mapping=_dummy_mapping((5.0, 10.0), (600.0, 700.0)),
    )


def test_plot_renders_without_error(require_matplotlib):
    fig = _fake_mesh().plot()
    assert fig is not None


def test_plot_omits_points_with_no_assemblage(require_matplotlib):
    fig = _fake_mesh().plot()
    ax = fig.axes[0]
    # 3 of the 4 points have an assemblage, across 2 distinct fields -- the unassembled 4th
    # point (a failed computation) contributes to neither scatter collection.
    total_offsets = sum(len(c.get_offsets()) for c in ax.collections)
    assert total_offsets == 3


def test_plot_distinct_fields_get_distinct_colors(require_matplotlib):
    fig = _fake_mesh().plot()
    ax = fig.axes[0]
    assert len(ax.collections) == 2
    colors = [tuple(c.get_facecolor()[0]) for c in ax.collections]
    assert colors[0] != colors[1]


def test_plot_legend_labels_are_space_joined_assemblages(require_matplotlib):
    fig = _fake_mesh().plot()
    legend = fig.legends[0]
    labels = sorted(text.get_text() for text in legend.get_texts())
    assert labels == ["cpx ol opx", "ol opx"]


def test_plot_axis_orientation_pt(require_matplotlib):
    fig = _oriented_mesh("PT").plot()
    ax = fig.axes[0]
    assert ax.get_xlabel() == "T [°C]"
    assert ax.get_ylabel() == "P [kbar]"
    assert ax.get_xlim() == (600.0, 700.0)
    assert ax.get_ylim() == (5.0, 10.0)


def test_plot_axis_orientation_px(require_matplotlib):
    fig = _oriented_mesh("PX").plot()
    ax = fig.axes[0]
    assert ax.get_xlabel() == "X"
    assert ax.get_ylabel() == "P [kbar]"
    assert ax.get_xlim() == (600.0, 700.0)
    assert ax.get_ylim() == (5.0, 10.0)


def test_plot_axis_orientation_tx(require_matplotlib):
    fig = _oriented_mesh("TX").plot()
    ax = fig.axes[0]
    assert ax.get_xlabel() == "T [°C]"
    assert ax.get_ylabel() == "X"
    assert ax.get_xlim() == (5.0, 10.0)
    assert ax.get_ylim() == (600.0, 700.0)


def test_plot_raises_without_matplotlib(monkeypatch):
    monkeypatch.setitem(sys.modules, "matplotlib", None)
    monkeypatch.setitem(sys.modules, "matplotlib.pyplot", None)
    with pytest.raises(MAGEMinPlottingError, match=r"magemin\[plot\]"):
        _fake_mesh().plot()


def test_show_creates_a_figure_and_calls_plot(require_matplotlib, monkeypatch):
    import matplotlib.pyplot as plt

    shown = []
    monkeypatch.setattr(plt, "show", lambda: shown.append(True))
    _fake_mesh().show()
    assert shown == [True]


def test_show_raises_without_matplotlib(monkeypatch):
    monkeypatch.setitem(sys.modules, "matplotlib", None)
    monkeypatch.setitem(sys.modules, "matplotlib.pyplot", None)
    with pytest.raises(MAGEMinPlottingError, match=r"magemin\[plot\]"):
        _fake_mesh().show()
