"""Library-gated tests for `PhaseDiagram.validate()` (small grids, no network -- default suite)."""

from magemin import _diagrams, bulk_rocks
from magemin.diagrams import PhaseDiagram


def test_validate_returns_bool(require_library):
    diagram = PhaseDiagram.pt(
        "ig", P=(5, 10), T=(700, 900), bulk=bulk_rocks.KLB1_IG, initial_resolution=1, refine=2
    )
    assert isinstance(diagram.validate(), bool)


def test_polymorph_swap_boundaries_in_real_diagram_are_recognized_as_clean(require_library):
    # Same tutorial mp diagram known (from the previous DiagramTopology-based tests) to contain
    # a genuine Al2SiO5 polymorph-swap boundary (ky/sill/and) -- confirm validate()'s underlying
    # pairwise check recognizes it as clean rather than spuriously flagging it.
    bulk = [
        61.5428,
        10.7347,
        1.2660,
        3.2294,
        5.3527,
        2.1983,
        1.5273,
        0.6297,
        0.1500,
        0.1001,
        13.2691,
    ]
    diagram = PhaseDiagram.pt(
        "mp",
        P=(5, 12),
        T=(600, 720),
        bulk=bulk,
        sys_in="mol",
        suppress_phases=["ilm"],
        initial_resolution=3,
        refine=4,
    )

    # A real boundary almost always leaves an unresolved cell straddling it (see
    # validate_diagram's docstring), so mirror its "bridge one unresolved buffer cell" reach
    # when searching for a real polymorph-swap pair here.
    cells = diagram.cells
    adjacency = _diagrams.build_adjacency(cells)
    nearby_pairs: set[tuple[int, int]] = set()
    for i, neighbors in adjacency.items():
        if not cells[i].resolved:
            continue
        for j in neighbors:
            if cells[j].resolved:
                nearby_pairs.add((i, j) if i < j else (j, i))
            else:
                for k in adjacency.get(j, ()):
                    if k != i and cells[k].resolved:
                        nearby_pairs.add((i, k) if i < k else (k, i))

    swaps: list[tuple[tuple[str, ...], tuple[str, ...]]] = []
    for i, j in nearby_pairs:
        a, b = cells[i], cells[j]
        if a.assemblage == b.assemblage:
            continue
        diff = set(a.assemblage) ^ set(b.assemblage)
        if len(diff) != 2:
            continue
        phase_a, phase_b = diff
        group = _diagrams._polymorph_group(phase_a)
        if group is not None and phase_b in group:
            swaps.append((a.assemblage, b.assemblage))

    assert swaps  # this diagram is known to have polymorph-swap boundaries
    for assemblage_a, assemblage_b in swaps:
        assert _diagrams._is_clean_boundary(assemblage_a, assemblage_b) is True
