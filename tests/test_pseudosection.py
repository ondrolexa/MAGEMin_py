"""Library-gated tests for `Pseudosection` (small windows, no network -- default suite)."""

from magemin import bulk_rocks
from magemin.pseudosection import Pseudosection


def test_pt_pseudosection_covers_bounding_box(require_library, require_mesh):
    mesh = Pseudosection.pt(
        "ig",
        P=(5, 10),
        T=(700, 900),
        bulk=bulk_rocks.KLB1_IG,
        initial_resolution=1,
        refine=1,
        lloyd_iterations=1,
    )
    assert mesh.kind == "PT"
    assert mesh.points
    xs = [p.axis1 for p in mesh.points]
    ys = [p.axis2 for p in mesh.points]
    assert min(xs) == 5
    assert max(xs) == 10
    assert min(ys) == 700
    assert max(ys) == 900


def test_pt_pseudosection_edges_reference_valid_points(require_library, require_mesh):
    mesh = Pseudosection.pt(
        "ig",
        P=(5, 10),
        T=(700, 900),
        bulk=bulk_rocks.KLB1_IG,
        initial_resolution=1,
        refine=1,
        lloyd_iterations=1,
    )
    assert mesh.edges
    for i, j in mesh.edges:
        assert i < j
        assert 0 <= i < len(mesh.points)
        assert 0 <= j < len(mesh.points)


def test_px_pseudosection(require_library, require_mesh):
    mesh = Pseudosection.px(
        "ig",
        P=(5, 10),
        T=800,
        bulk_a=bulk_rocks.KLB1_IG,
        bulk_b=bulk_rocks.RE46_IG,
        initial_resolution=1,
        refine=1,
        lloyd_iterations=1,
    )
    assert mesh.kind == "PX"
    assert mesh.axis2_label == "X"
    assert mesh.fixed_label == "T = 800 °C"
    assert mesh.points


def test_tx_pseudosection(require_library, require_mesh):
    mesh = Pseudosection.tx(
        "ig",
        P=8,
        T=(700, 900),
        bulk_a=bulk_rocks.KLB1_IG,
        bulk_b=bulk_rocks.RE46_IG,
        initial_resolution=1,
        refine=1,
        lloyd_iterations=1,
    )
    assert mesh.kind == "TX"
    assert mesh.axis2_label == "X"
    assert mesh.fixed_label == "P = 8 kbar"
    assert mesh.points


def test_validate_returns_bool(require_library, require_mesh):
    mesh = Pseudosection.pt(
        "ig",
        P=(5, 10),
        T=(700, 900),
        bulk=bulk_rocks.KLB1_IG,
        initial_resolution=1,
        refine=1,
        lloyd_iterations=1,
    )
    assert isinstance(mesh.validate(), bool)


def test_refine_preserves_all_previously_computed_points(require_library, require_mesh):
    mesh = Pseudosection.pt(
        "ig",
        P=(5, 10),
        T=(700, 900),
        bulk=bulk_rocks.KLB1_IG,
        initial_resolution=1,
        refine=1,
        lloyd_iterations=1,
    )
    refined = mesh.refine(refine=1)
    old_coords = {(p.axis1, p.axis2) for p in mesh.points}
    new_coords = {(p.axis1, p.axis2) for p in refined.points}
    assert old_coords <= new_coords


def test_refine_leaves_original_mesh_unchanged(require_library, require_mesh):
    mesh = Pseudosection.pt(
        "ig",
        P=(5, 10),
        T=(700, 900),
        bulk=bulk_rocks.KLB1_IG,
        initial_resolution=1,
        refine=1,
        lloyd_iterations=1,
    )
    n_points_before = len(mesh.points)
    mesh.refine(refine=1)
    assert len(mesh.points) == n_points_before


def test_refine_never_requests_an_already_known_point(require_library, require_mesh, monkeypatch):
    mesh = Pseudosection.pt(
        "ig",
        P=(5, 10),
        T=(700, 900),
        bulk=bulk_rocks.KLB1_IG,
        initial_resolution=1,
        refine=1,
        lloyd_iterations=1,
    )
    known = {(p.axis1, p.axis2) for p in mesh.points}

    from magemin import pseudosection as pseudosection_module

    original = pseudosection_module.multi_point_minimization
    requested: list[tuple[float, float]] = []

    def spy(database, points, **kwargs):
        requested.extend((p.P, p.T) for p in points)
        return original(database, points, **kwargs)

    monkeypatch.setattr(pseudosection_module, "multi_point_minimization", spy)
    mesh.refine(refine=1)

    assert not (set(requested) & known)  # none of the newly requested points were already known


def test_str_reports_kind_database_and_counts(require_library, require_mesh):
    mesh = Pseudosection.pt(
        "ig",
        P=(5, 10),
        T=(700, 900),
        bulk=bulk_rocks.KLB1_IG,
        initial_resolution=1,
        refine=1,
        lloyd_iterations=1,
    )
    text = str(mesh)
    assert text.startswith("PT pseudosection (ig)")
    assert f"Points computed      : {len(mesh.points)}" in text
    assert "Fixed" not in text
