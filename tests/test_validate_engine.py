"""Offline tests for `magemin._diagrams`'s cell-adjacency and boundary-validity engine.

No C library / network involved -- `DiagramCell`s are hand-built directly.
"""

from magemin import _diagrams
from magemin.diagrams import DiagramCell


def _cell(
    i0: int, j0: int, i1: int, j1: int, *, resolved: bool = False, assemblage=None
) -> DiagramCell:
    corners = (
        (float(i0), float(j0)),
        (float(i1), float(j0)),
        (float(i1), float(j1)),
        (float(i0), float(j1)),
    )
    lattice_corners = ((i0, j0), (i1, j0), (i1, j1), (i0, j1))
    return DiagramCell(
        corners=corners,
        lattice_corners=lattice_corners,
        depth=0,
        resolved=resolved,
        assemblage=assemblage,
    )


# --- _diagrams.build_adjacency ---


def test_adjacency_detects_shared_horizontal_edge() -> None:
    left = _cell(0, 0, 1, 2)
    right = _cell(1, 0, 2, 2)
    adjacency = _diagrams.build_adjacency([left, right])
    assert adjacency[0] == {1}
    assert adjacency[1] == {0}


def test_adjacency_rejects_corner_only_touch() -> None:
    bottom_left = _cell(0, 0, 1, 1)
    top_right = _cell(1, 1, 2, 2)
    adjacency = _diagrams.build_adjacency([bottom_left, top_right])
    assert adjacency.get(0, set()) == set()
    assert adjacency.get(1, set()) == set()


def test_adjacency_handles_differently_sized_neighbors() -> None:
    # A large cell on the left, two smaller cells stacked on the right --
    # a common shape where a coarser and a more-refined neighbor meet.
    big = _cell(0, 0, 2, 4)
    small_top = _cell(2, 2, 3, 4)
    small_bottom = _cell(2, 0, 3, 2)
    adjacency = _diagrams.build_adjacency([big, small_top, small_bottom])
    assert adjacency[0] == {1, 2}
    # small_top and small_bottom also share an edge with each other (j == 2).
    assert adjacency[1] == {0, 2}
    assert adjacency[2] == {0, 1}


# --- _diagrams._is_clean_boundary ---


def test_clean_boundary_superset_a_bigger() -> None:
    assert _diagrams._is_clean_boundary(("a", "b", "c"), ("a", "b")) is True


def test_clean_boundary_superset_b_bigger() -> None:
    assert _diagrams._is_clean_boundary(("a", "b"), ("a", "b", "c")) is True


def test_clean_boundary_equal_sets_returns_false() -> None:
    assert _diagrams._is_clean_boundary(("a", "b"), ("a", "b")) is False


def test_clean_boundary_non_polymorph_swap_returns_false() -> None:
    assert _diagrams._is_clean_boundary(("a", "b", "c"), ("a", "b", "d")) is False


def test_clean_boundary_larger_difference_returns_false() -> None:
    assert _diagrams._is_clean_boundary(("a", "b", "c"), ("a",)) is False


def test_clean_boundary_polymorph_swap_is_clean() -> None:
    # "and" vs "sill" is a polymorphic transition, not a phase appearing/disappearing.
    assert _diagrams._is_clean_boundary(("bt", "g", "and"), ("bt", "g", "sill")) is True


def test_clean_boundary_polymorph_swap_order_independent() -> None:
    assert _diagrams._is_clean_boundary(("bt", "sill"), ("bt", "and")) is True


def test_clean_boundary_sio2_polymorph_swap_is_clean() -> None:
    assert _diagrams._is_clean_boundary(("bt", "coe"), ("bt", "stv")) is True


def test_polymorph_group_recognizes_al2sio5_and_sio2_groups() -> None:
    assert _diagrams._polymorph_group("sill") == {"ky", "sill", "and"}
    assert _diagrams._polymorph_group("qtz") == {"q", "qtz", "crst", "trd", "coe", "stv"}


def test_polymorph_group_returns_none_for_unrecognized_phase() -> None:
    assert _diagrams._polymorph_group("liq") is None


# --- _diagrams.validate_diagram ---


def test_validate_diagram_true_for_clean_boundary() -> None:
    a = _cell(0, 0, 1, 1, resolved=True, assemblage=("a", "b", "c"))
    b = _cell(1, 0, 2, 1, resolved=True, assemblage=("a", "b"))
    assert _diagrams.validate_diagram([a, b]) is True


def test_validate_diagram_true_for_polymorph_swap() -> None:
    a = _cell(0, 0, 1, 1, resolved=True, assemblage=("bt", "g", "and"))
    b = _cell(1, 0, 2, 1, resolved=True, assemblage=("bt", "g", "sill"))
    assert _diagrams.validate_diagram([a, b]) is True


def test_validate_diagram_false_for_non_polymorph_swap() -> None:
    a = _cell(0, 0, 1, 1, resolved=True, assemblage=("a", "b", "c"))
    b = _cell(1, 0, 2, 1, resolved=True, assemblage=("a", "b", "d"))
    assert _diagrams.validate_diagram([a, b]) is False


def test_validate_diagram_true_for_unresolved_cell_with_no_further_neighbors() -> None:
    a = _cell(0, 0, 1, 1, resolved=True, assemblage=("a", "b"))
    unresolved = _cell(1, 0, 2, 1, resolved=False, assemblage=None)
    assert _diagrams.validate_diagram([a, unresolved]) is True


def test_validate_diagram_bridges_one_unresolved_buffer_cell_clean() -> None:
    # A real boundary almost always leaves one unresolved cell straddling it -- bridging
    # through it is what lets validate_diagram reach the real reaction-line network.
    a = _cell(0, 0, 1, 1, resolved=True, assemblage=("a", "b", "c"))
    u = _cell(1, 0, 2, 1, resolved=False, assemblage=None)
    b = _cell(2, 0, 3, 1, resolved=True, assemblage=("a", "b"))
    assert _diagrams.validate_diagram([a, u, b]) is True


def test_validate_diagram_bridges_one_unresolved_buffer_cell_dirty() -> None:
    a = _cell(0, 0, 1, 1, resolved=True, assemblage=("a", "b", "c"))
    u = _cell(1, 0, 2, 1, resolved=False, assemblage=None)
    b = _cell(2, 0, 3, 1, resolved=True, assemblage=("a", "b", "d"))
    assert _diagrams.validate_diagram([a, u, b]) is False


def test_validate_diagram_does_not_bridge_two_unresolved_cells() -> None:
    # A 2-cell-wide unresolved gap is outside this design's scope (bridging exactly one
    # buffer cell) -- the two resolved cells on either side are never compared directly.
    a = _cell(0, 0, 1, 1, resolved=True, assemblage=("a", "b", "c"))
    u1 = _cell(1, 0, 2, 1, resolved=False, assemblage=None)
    u2 = _cell(2, 0, 3, 1, resolved=False, assemblage=None)
    b = _cell(3, 0, 4, 1, resolved=True, assemblage=("a", "b", "d"))
    assert _diagrams.validate_diagram([a, u1, u2, b]) is True


def test_validate_diagram_skips_equal_assemblage_neighbors() -> None:
    a = _cell(0, 0, 1, 1, resolved=True, assemblage=("a", "b"))
    b = _cell(1, 0, 2, 1, resolved=True, assemblage=("a", "b"))
    assert _diagrams.validate_diagram([a, b]) is True


def test_validate_diagram_ignores_non_adjacent_cells() -> None:
    # These two cells only touch at a corner, not along a shared edge -- outside this
    # design's scope (edge-adjacency only), so a bad "boundary" between them is never checked.
    a = _cell(0, 0, 1, 1, resolved=True, assemblage=("a", "b", "c"))
    b = _cell(1, 1, 2, 2, resolved=True, assemblage=("a", "b", "d"))
    assert _diagrams.validate_diagram([a, b]) is True
