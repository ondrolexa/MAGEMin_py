"""Library-gated tests for `PhaseDiagram` (small grids, no network -- default suite)."""

import pytest

from magemin import bulk_rocks
from magemin.diagrams import PhaseDiagram


def test_pt_diagram_covers_bounding_box_with_no_duplicate_points(require_library):
    diagram = PhaseDiagram.pt(
        "ig",
        P=(5, 10),
        T=(700, 900),
        bulk=bulk_rocks.KLB1_IG,
        initial_resolution=1,
        refine=1,
    )
    assert diagram.kind == "PT"
    assert diagram.cells
    assert diagram.points

    xs = [x for cell in diagram.cells for x, _ in cell.corners]
    ys = [y for cell in diagram.cells for _, y in cell.corners]
    assert min(xs) == 5
    assert max(xs) == 10
    assert min(ys) == 700
    assert max(ys) == 900

    coords = [(p.axis1, p.axis2) for p in diagram.points]
    assert len(coords) == len(set(coords))


def test_pt_defaults_refine_to_zero(require_library):
    diagram = PhaseDiagram.pt(
        "ig",
        P=(5, 10),
        T=(700, 900),
        bulk=bulk_rocks.KLB1_IG,
        initial_resolution=2,
    )
    assert diagram.max_depth == diagram.initial_resolution == 2
    # A uniform grid: no cell was ever refined past the initial resolution.
    assert all(cell.depth == 2 for cell in diagram.cells)
    assert len(diagram.cells) == (2**2) ** 2


def test_pt_explicit_refine_still_works(require_library):
    diagram = PhaseDiagram.pt(
        "ig",
        P=(5, 10),
        T=(700, 900),
        bulk=bulk_rocks.KLB1_IG,
        initial_resolution=1,
        refine=2,
    )
    assert diagram.max_depth == 3


def test_px_defaults_refine_to_zero(require_library):
    diagram = PhaseDiagram.px(
        "ig",
        P=(5, 10),
        T=800,
        bulk_a=bulk_rocks.KLB1_IG,
        bulk_b=bulk_rocks.RE46_IG,
        initial_resolution=2,
    )
    assert diagram.max_depth == diagram.initial_resolution == 2


def test_tx_defaults_refine_to_zero(require_library):
    diagram = PhaseDiagram.tx(
        "ig",
        P=8,
        T=(700, 900),
        bulk_a=bulk_rocks.KLB1_IG,
        bulk_b=bulk_rocks.RE46_IG,
        initial_resolution=2,
    )
    assert diagram.max_depth == diagram.initial_resolution == 2


def test_px_diagram(require_library):
    diagram = PhaseDiagram.px(
        "ig",
        P=(5, 10),
        T=800,
        bulk_a=bulk_rocks.KLB1_IG,
        bulk_b=bulk_rocks.RE46_IG,
        initial_resolution=1,
        refine=1,
    )
    assert diagram.kind == "PX"
    assert diagram.axis2_label == "X"
    assert diagram.fixed_label == "T = 800 °C"
    assert diagram.axis2_range == (0.0, 1.0)
    assert diagram.cells


def test_tx_diagram(require_library):
    diagram = PhaseDiagram.tx(
        "ig",
        P=8,
        T=(700, 900),
        bulk_a=bulk_rocks.KLB1_IG,
        bulk_b=bulk_rocks.RE46_IG,
        initial_resolution=1,
        refine=1,
    )
    assert diagram.kind == "TX"
    assert diagram.axis2_label == "X"
    assert diagram.fixed_label == "P = 8 kbar"
    assert diagram.cells


def test_pt_diagram_defaults_match_direct_compute(ig):
    diagram = PhaseDiagram.pt(
        "ig",
        P=(6, 10),
        T=(700, 900),
        bulk=bulk_rocks.KLB1_IG,
        initial_resolution=1,
        refine=0,
    )
    sample = diagram.points[0]

    # light=True default: nested per-phase detail is skipped.
    assert sample.result.solution_phases == ()
    assert sample.result.pure_phases == ()

    # name_solvus=True default threads through to the underlying compute() call.
    expected = ig.compute(
        sample.axis1, sample.axis2, bulk_rocks.KLB1_IG, light=True, name_solvus=True
    )
    assert sample.result.ph == expected.ph


def test_pt_diagram_n_components_matches_database_oxide_count(ig):
    diagram = PhaseDiagram.pt(
        "ig",
        P=(8, 8),
        T=(800, 800),
        bulk=bulk_rocks.KLB1_IG,
        initial_resolution=0,
        refine=0,
    )
    assert diagram.n_components == ig.n_oxides


def test_pt_diagram_light_false_populates_nested_phases(require_library):
    diagram = PhaseDiagram.pt(
        "ig",
        P=(8, 8),
        T=(800, 800),
        bulk=bulk_rocks.KLB1_IG,
        initial_resolution=0,
        refine=0,
        light=False,
    )
    sample = diagram.points[0]
    assert len(sample.result.solution_phases) + len(sample.result.pure_phases) > 0


def test_refine_default_step_is_one_deeper(require_library):
    diagram = PhaseDiagram.pt(
        "ig", P=(5, 10), T=(700, 900), bulk=bulk_rocks.KLB1_IG, initial_resolution=1, refine=1
    )
    refined = diagram.refine()
    assert refined.max_depth == diagram.max_depth + 1


def test_refine_with_explicit_step(require_library):
    diagram = PhaseDiagram.pt(
        "ig", P=(5, 10), T=(700, 900), bulk=bulk_rocks.KLB1_IG, initial_resolution=1, refine=1
    )
    refined = diagram.refine(refine=2)
    assert refined.max_depth == diagram.max_depth + 2


def test_refine_rejects_non_positive_refine(require_library):
    diagram = PhaseDiagram.pt(
        "ig", P=(5, 10), T=(700, 900), bulk=bulk_rocks.KLB1_IG, initial_resolution=1, refine=1
    )
    with pytest.raises(ValueError, match="refine"):
        diagram.refine(refine=0)
    with pytest.raises(ValueError, match="refine"):
        diagram.refine(refine=-1)


def test_refine_leaves_original_diagram_unchanged(require_library):
    diagram = PhaseDiagram.pt(
        "ig", P=(5, 10), T=(700, 900), bulk=bulk_rocks.KLB1_IG, initial_resolution=1, refine=1
    )
    n_cells_before = len(diagram.cells)
    diagram.refine(refine=1)
    assert diagram.max_depth == 2
    assert len(diagram.cells) == n_cells_before


def test_refine_preserves_all_previously_computed_points(require_library):
    diagram = PhaseDiagram.pt(
        "ig", P=(5, 10), T=(700, 900), bulk=bulk_rocks.KLB1_IG, initial_resolution=1, refine=1
    )
    refined = diagram.refine(refine=1)
    old_coords = {(p.axis1, p.axis2) for p in diagram.points}
    new_coords = {(p.axis1, p.axis2) for p in refined.points}
    assert old_coords <= new_coords
    assert len(new_coords) > len(old_coords)


def test_refine_never_requests_an_already_known_point(require_library, monkeypatch):
    diagram = PhaseDiagram.pt(
        "ig", P=(5, 10), T=(700, 900), bulk=bulk_rocks.KLB1_IG, initial_resolution=1, refine=1
    )
    known = {(p.axis1, p.axis2) for p in diagram.points}

    from magemin import diagrams as diagrams_module

    original = diagrams_module.multi_point_minimization
    requested: list[tuple[float, float]] = []

    def spy(database, points, **kwargs):
        requested.extend((p.P, p.T) for p in points)
        return original(database, points, **kwargs)

    monkeypatch.setattr(diagrams_module, "multi_point_minimization", spy)
    diagram.refine(refine=1)

    assert requested  # genuinely new, deeper points were computed
    assert not (set(requested) & known)  # none of them were already known


def test_str_reports_kind_database_and_counts(require_library):
    diagram = PhaseDiagram.pt(
        "ig", P=(5, 10), T=(700, 900), bulk=bulk_rocks.KLB1_IG, initial_resolution=1, refine=1
    )
    text = str(diagram)
    resolved = sum(1 for c in diagram.cells if c.resolved)
    assert text.startswith("PT diagram (ig)")
    assert f"Points computed      : {len(diagram.points)}" in text
    assert f"({resolved} resolved, {len(diagram.cells) - resolved} unresolved)" in text
    assert "Fixed" not in text


def test_str_includes_fixed_label_for_px(require_library):
    diagram = PhaseDiagram.px(
        "ig",
        P=(5, 10),
        T=800,
        bulk_a=bulk_rocks.KLB1_IG,
        bulk_b=bulk_rocks.RE46_IG,
        initial_resolution=1,
        refine=0,
    )
    text = str(diagram)
    assert "Fixed                : T = 800 °C" in text
