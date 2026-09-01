# Usage

## Predefined bulk-rock composition

```python
from magemin import MAGEMin, bulk_rocks

with MAGEMin("ig") as mg:
    result = mg.compute(P=8, T=800, bulk=bulk_rocks.KLB1_IG)
    print(result)
    print(result.ph, result.ph_frac)  # phase names / mol fractions
    print(result.rho, result.vp, result.vs)  # density, seismic velocities
```

`MAGEMin(database)` initializes one thermodynamic-database handle, which can be reused across many
[`compute()`][magemin.core.MAGEMin.compute] calls -- there's no need to re-create it per point. Using
it as a context manager (`with MAGEMin(...) as mg:`) closes the underlying C handle automatically;
without one, call [`mg.close()`][magemin.core.MAGEMin.close] explicitly when you're done.

See [Predefined bulk rocks](api/bulk_rocks.md) for the full list of predefined compositions, and
[`BulkRock`][magemin.bulk_rocks.BulkRock] for what each one holds.

## Custom bulk composition

A plain sequence of values, in the database's own oxide order, works too. Discover that order with
[`oxide_names`][magemin.core.MAGEMin.oxide_names]:

```python
with MAGEMin("ig") as mg:
    print(mg.oxide_names)
    #  ('SiO2', 'Al2O3', 'CaO', 'MgO', 'FeO', 'K2O', 'Na2O', 'TiO2', 'O', 'Cr2O3', 'H2O')

    bulk = [50.0, 15.0, 10.0, 8.0, 9.0, 0.5, 3.0, 1.5, 0.0, 0.0, 2.0]
    result = mg.compute(P=10, T=1100, bulk=bulk, sys_in="wt")
    print(result.ph, result.ph_frac)
```

`sys_in` (`"mol"` or `"wt"`) is required for a plain sequence; it's optional -- and defaults to
`bulk.sys_in` -- when `bulk` is a [`BulkRock`][magemin.bulk_rocks.BulkRock].

## Inspecting a result in detail

[`compute()`][magemin.core.MAGEMin.compute] returns an
[`EquilibriumResult`][magemin.results.EquilibriumResult]. System-level thermodynamic and elastic
properties are plain attributes; per-phase detail lives in three tuples of nested dataclasses:

```python
result = mg.compute(P=8, T=800, bulk=bulk_rocks.KLB1_IG)

for phase in result.solution_phases:  # magemin.results.SolutionPhase
    print(phase.em_names, phase.em_frac)  # endmember names / mol fractions

for phase in result.pure_phases:  # magemin.results.PurePhase
    print(phase.g, phase.rho)

for phase in result.metastable_phases:  # magemin.results.MetastableSolutionPhase
    print(phase.ph_name, phase.g_ppc)
```

See the [Results API reference](api/results.md) for every attribute on
[`EquilibriumResult`][magemin.results.EquilibriumResult],
[`SolutionPhase`][magemin.results.SolutionPhase],
[`MetastableSolutionPhase`][magemin.results.MetastableSolutionPhase], and
[`PurePhase`][magemin.results.PurePhase].

!!! note "Temperature is reported back in Kelvin"
    `compute()` takes `T` in Celsius, but `EquilibriumResult.t` reports it back in **Kelvin**
    (`t == T_celsius + 273.15`); `EquilibriumResult.p` stays in kbar, matching the input. The
    `str(result)` summary already converts back to Celsius for display.

## Oxygen buffers and fixed activities

Pass `buffer` and `buffer_value` to `compute()` to fix an oxygen buffer or an oxide activity for that
point. This is re-applied (or explicitly cleared) on **every** `compute()` call, so it never silently
carries over from a previous call on the same `MAGEMin` instance:

```python
# Redox buffer: buffer_value is an additive log-unit offset (e.g. dQFM-style)
result = mg.compute(P=8, T=800, bulk=bulk_rocks.KLB1_IG, buffer="cco", buffer_value=-1.0)
print(result.buffer, result.buffer_n, result.f_o2)

# Fixed activity: buffer_value IS the activity value itself, in (0, 1)
result = mg.compute(P=8, T=800, bulk=bulk_rocks.KLB1_IG, buffer="aH2O", buffer_value=0.5)
```

Redox buffers: `O2`, `qfm`, `mw`, `qif`, `nno`, `hm`, `iw`, `cco`. Fixed-activity constraints: `aH2O`,
`aO2`, `aMgO`, `aFeO`, `aAl2O3`, `aTiO2`. Not every name is available for every database -- an
unavailable-but-recognized name raises [`MAGEMinComputeError`][magemin.errors.MAGEMinComputeError].

## Suppressing phases

Pass `suppress_phases` to exclude specific solution or pure phases from a point's minimization.
Discover valid names for the current database with
[`solution_phase_names`][magemin.core.MAGEMin.solution_phase_names]/
[`pure_phase_names`][magemin.core.MAGEMin.pure_phase_names]:

```python
print(mg.solution_phase_names)  # e.g. ('spl', 'bi', 'cd', 'cpx', ..., 'liq', ...)

result = mg.compute(P=8, T=800, bulk=bulk_rocks.KLB1_IG, suppress_phases=["spl"])
assert "spl" not in result.ph
```

A few databases hard-code a single default variant for a near-degenerate phase-model pair (e.g.
`mp`'s two ilmenite-group models, `"ilm"` and `"ilmm"`) -- without `suppress_phases`, only the
default variant's pseudocompounds are ever generated at all, so the other one can never appear
regardless of P/T/bulk. Passing any `suppress_phases` (not necessarily naming that pair) makes
`compute()` generate both variants before applying the suppression, so suppressing the default one
correctly lets the other take its place:

```python
result = mg.compute(P=6, T=660, bulk=bulk, sys_in="mol", suppress_phases=["ilm"])
assert "ilmm" in result.ph  # only reachable now that ilm has been suppressed
```

## Solvus disambiguation

Some solution-phase models split into mineralogically distinct end-members across a solvus (e.g.
`fsp` into plagioclase `pl` / alkali feldspar `afs`, `spl` into spinel/chromite/magnetite/ulvospinel).
`name_solvus` defaults to `True`, renaming such phases in the result's `ph` from the raw
solution-model name to the disambiguated mineral name, based on each phase's converged
compositional variables. This works independently of `light`:

```python
result = mg.compute(P=10, T=1100, bulk=bulk, sys_in="wt")
print(result.ph)  # (..., 'pl', ...) instead of (..., 'fsp', ...)
```

Pass `name_solvus=False` to get the raw solution-model names instead -- needed e.g. to match
`solution_phase_names`/`pure_phase_names` for `suppress_phases`, which always expects raw names:

```python
result = mg.compute(P=10, T=1100, bulk=bulk, sys_in="wt", name_solvus=False)
print(result.ph)  # (..., 'fsp', ...) -- raw solution-model name, undisambiguated
```

[`solvus_name`][magemin._solvus.solvus_name]/[`base_phase_name`][magemin._solvus.base_phase_name] are the underlying
functions, usable directly on a `database` string, a phase name, and compositional variables (or a
mineral name for the reverse direction) without a `MAGEMin` instance. `base_phase_name` is useful to
convert a disambiguated name back to its raw solution-model name before passing it to
`suppress_phases`:

```python
from magemin import base_phase_name

raw_name = base_phase_name(result.database, "pl")  # "fsp"
mg.compute(P=10, T=1100, bulk=bulk, sys_in="wt", suppress_phases=[raw_name])
```

## Choosing a solver

`MAGEMin(database, solver=...)` selects which local-minimizer algorithm the underlying C library
uses: `0` (legacy), `1` (PGE + legacy hybrid), or `2` (hybrid PGE/LP -- the library's own default,
and this package's default). `multi_point_minimization` and `PhaseDiagram.pt`/`.px`/`.tx` accept
the same kwarg, threaded through to every worker's handle.

This matters because two near-degenerate phases -- distinct solution models that are both close to
stable for the same bulk/P/T -- can resolve differently depending on solver. For example, at
`P=10, T=790` for a typical `mp`-database metapelite bulk, the default `solver=2` finds only `pl`
(plagioclase) stable, while `solver=0` finds the feldspar solvus splits into *both* `afs` and `pl`:

```python
with MAGEMin("mp", solver=0) as mg:
    result = mg.compute(P=10, T=790, bulk=bulk, sys_in="mol", name_solvus=True)
    print(result.ph)  # includes 'afs' -- solver=2 (the default) would not
```

`solver` is forced to `0` by the underlying library for `sb`/`gh`-family databases regardless of
what's requested -- those only support the legacy solver upstream. Avoid `solver=3`: it's a
"metastable calculation, no minimization" diagnostic mode, not a normal alternate equilibrium
solver, and can return duplicate phase-name entries in `ph` rather than a single converged answer.

## Light mode for bulk sweeps

Pass `light=True` to skip building `solution_phases`/`metastable_phases`/`pure_phases` on the
result -- deep-copying each phase's endmember/composition arrays is the expensive part of building a
result, so this is meaningfully faster for large sweeps that only need the phase-summary arrays
(`ph`, `ph_frac`, ...):

```python
result = mg.compute(P=8, T=800, bulk=bulk_rocks.KLB1_IG, light=True)
assert result.solution_phases == ()
print(result.ph, result.ph_frac)  # still populated
```

## sb/gh database families

Alongside the `tc`-family databases (`ig`, `mp`, `mb`, ...), `MAGEMin` also accepts the `sb`
(Stixrude & Lithgow-Bertelloni: `sb11`, `sb21`, `sb24`) and `gh` (MELTS: `xMELTS`, `rMELTS`,
`pMELTS`) families -- the research group is inferred from the acronym automatically:

```python
with MAGEMin("sb11") as mg:
    result = mg.compute(P=10, T=800, bulk=bulk_rocks.KLB1_SB)

with MAGEMin("xMELTS") as mg:
    result = mg.compute(P=10, T=800, bulk=bulk_rocks.BASALT_GH)
```

## Many points in parallel

[`multi_point_minimization()`][magemin.core.multi_point_minimization] spreads a list of
[`Point`][magemin.core.Point]s across a thread pool, one `MAGEMin` handle per worker thread.
`Point` carries the same `buffer`/`buffer_value`/`suppress_phases`/`light`/`name_solvus` options as
`compute()`:

```python
from magemin import Point, bulk_rocks, multi_point_minimization

points = [
    Point(P=p, T=t, bulk=bulk_rocks.KLB1_IG, light=True)
    for p, t in [(5, 700), (10, 900), (15, 1100), (20, 1300)]
]
results = multi_point_minimization("ig", points, max_workers=4)
# results[i] corresponds to points[i], regardless of completion order
```

## Phase diagrams

[`PhaseDiagram`][magemin.diagrams.PhaseDiagram] builds an adaptively refined PT, PX, or TX
stable-phase-assemblage diagram on top of `multi_point_minimization`: a 2D grid is refined by
subdividing cells whose 4 corners disagree on the stable phase assemblage, so resolution
concentrates near phase boundaries rather than being spent uniformly everywhere.

```python
from magemin import PhaseDiagram, bulk_rocks

diagram = PhaseDiagram.pt(
    "ig",
    P=(2, 20),
    T=(700, 1300),
    bulk=bulk_rocks.KLB1_IG,
    initial_resolution=4,
    refine=3,
)
print(len(diagram.cells), "cells")
```

`refine` (number of quadtree refinement steps beyond `initial_resolution`) defaults to `0` -- a
plain uniform grid with no adaptive refinement at all -- so pass a positive `refine` (as above) to
actually get one.

`PX`/`TX` diagrams vary pressure/temperature against `X`, a bulk-composition interpolation
fraction in `[0, 1]` between two end-member compositions:

```python
diagram = PhaseDiagram.px(
    "ig",
    P=(2, 20),
    T=800,
    bulk_a=bulk_rocks.KLB1_IG,
    bulk_b=bulk_rocks.RE46_IG,
    initial_resolution=4,
    refine=3,
)
```

Unlike `compute()`, `PhaseDiagram` construction defaults to `light=True` (the refiner only ever
reads a point's stable-phase names). It also relies on `name_solvus=True` (`compute()`'s own
default too) -- solvus disambiguation is exactly what lets the refiner tell a real solvus boundary
apart from a shared raw phase name like `"fsp"`.

Rendering requires the optional `matplotlib` extra (`pip install magemin[plot]`). Pressure plots
vertical and temperature horizontal by convention; each field is numbered and colored by its
assemblage's Gibbs-phase-rule variance, with a numbered (color-swatch-free) legend and a variance
colorbar -- every part of that styling is a `plot()` keyword argument. See the [pseudosection
tutorial](tutorial_pseudosection.md) for a full walkthrough of reading one:

```python
diagram.plot()
```

[`PhaseDiagram.show()`][magemin.diagrams.PhaseDiagram.show] is a shortcut for interactive use:
it creates a figure, calls `plot()` with whatever keyword arguments you pass it, and calls
`plt.show()`.

[`PhaseDiagram.plot_grid()`][magemin.diagrams.PhaseDiagram.plot_grid] renders the raw quadtree
mesh instead -- every cell's outline colored by refinement depth, regardless of resolved status
or assemblage. Useful for seeing where adaptive refinement actually concentrated. Pass
`unresolved=True` to additionally hatch cells that never resolved by the diagram's `max_depth`:

```python
diagram.plot_grid()
diagram.plot_grid(unresolved=True)
```

[`PhaseDiagram.show_grid()`][magemin.diagrams.PhaseDiagram.show_grid] is `show()`'s counterpart
for `plot_grid()`.

## Validating a diagram

[`PhaseDiagram.validate()`][magemin.diagrams.PhaseDiagram.validate] checks that every pair of
*nearby* resolved cells with different stable-phase assemblages forms a legitimate
[Schreinemakers](https://en.wikipedia.org/wiki/Schreinemaker%27s_analysis) boundary: either a
clean univariant crossing (the assemblages differ by exactly one phase) or a polymorph swap (the
one differing phase on each side is a polymorph of the other, e.g. `and`/`sill`). "Nearby" means
directly adjacent, or adjacent through exactly one shared unresolved buffer cell -- a real
boundary between two different resolved fields almost always leaves at least one still-unresolved
cell straddling it, so bridging one such cell is what lets this reach the diagram's real
reaction-line network. Pairs sharing the same assemblage, and any gap wider than one unresolved
cell, are skipped rather than checked:

```python
diagram.validate()  # True or False
```

This checks mesh structure only where the mesh actually reached a decision on both sides of a
boundary -- it is not full Schreinemakers rigor (no invariant-point/angular-ordering analysis).
`False` commonly just means the mesh needs deeper refinement to pull nearby reactions apart:
[`PhaseDiagram.refine()`][magemin.diagrams.PhaseDiagram.refine] returns a new, more deeply refined
diagram, reusing every already-computed point -- only the genuinely new, deeper corners get
recomputed:

```python
diagram = diagram.refine()  # one further refinement step
diagram = diagram.refine(refine=3)  # or several more steps at once
```

There is no automatic refine-and-retry loop yet; `validate()` returning `False` is meant to make
one straightforward to add later.

See the [pseudosection tutorial](tutorial_pseudosection.md#6-validating-the-pseudosection) for a
full example next to the diagram it validates.

## Delaunay-mesh pseudosections

[`Pseudosection`][magemin.pseudosection.Pseudosection] is an alternative to `PhaseDiagram`, ported
from the sibling `pseudo_graph` project: instead of a quadtree grid, points are sampled on a
perturbed hexagonal lattice, Delaunay-triangulated, and densified wherever two triangle-adjacent
points disagree in a way that isn't a legitimate boundary. Requires the optional `mesh` extra
(`pip install magemin[mesh]`) to build or refine one -- `.validate()`/`.plot()`/`.show()` don't
need it (the latter two need the `plot` extra instead).

```python
from magemin import Pseudosection, bulk_rocks

mesh = Pseudosection.pt(
    "ig", P=(2, 20), T=(700, 1300), bulk=bulk_rocks.KLB1_IG, initial_resolution=5, refine=3
)
print(mesh.converged, mesh.unresolved_boundaries)
```

`.px`/`.tx` mirror `PhaseDiagram.px`/`.tx`'s two-bulk-endmember interpolation. `refine` here is
the maximum number of densification rounds (not a quadtree depth, unlike `PhaseDiagram`'s own
`refine`), and `refine_all=True` keeps densifying already-clean boundaries too, for uniformly
denser sampling.

`.validate()` checks the same clean-boundary-or-polymorph-swap criterion as
`PhaseDiagram.validate()`, but pairwise over the mesh's Delaunay edges directly -- every point
already has a determinate assemblage (or `None`, on a failed computation), so there's no
"unresolved cell" concept to bridge:

```python
mesh.validate()  # True or False
```

[`Pseudosection.refine()`][magemin.pseudosection.Pseudosection.refine] returns a new, further
densified mesh, reusing every already-computed point (retrying any that previously failed) --
calling it on an already-`converged` mesh is cheap:

```python
mesh = mesh.refine(refine=8)
```

[`Pseudosection.plot()`][magemin.pseudosection.Pseudosection.plot] renders a scatter plot instead
of `PhaseDiagram.plot()`'s filled regions: one field per color/marker-shape combination (colors
cycle through 10 qualitative hues, then marker shape cycles every 10 fields), points with no
assemblage omitted. [`Pseudosection.show()`][magemin.pseudosection.Pseudosection.show] is the same
`plot()` + `plt.show()` shortcut as `PhaseDiagram.show()`.

## Error handling

All exceptions this package raises derive from
[`MAGEMinError`][magemin.errors.MAGEMinError]:

```python
from magemin import MAGEMin, BulkCompositionError, MAGEMinComputeError, bulk_rocks

with MAGEMin("ig") as mg:
    try:
        mg.compute(P=8, T=800, bulk=[1.0, 2.0], sys_in="mol")  # wrong length
    except BulkCompositionError as exc:
        print(exc)

    try:
        mg.compute(P=8, T=800, bulk=bulk_rocks.KLB1_IG, sys_in="bogus")
    except MAGEMinComputeError as exc:
        print(exc)
```

See the [Errors API reference](api/errors.md) for the full exception hierarchy and when each is
raised.
