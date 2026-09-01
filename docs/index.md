# magemin

Python interface to [MAGEMin](https://github.com/ComputationalThermodynamics/MAGEMin), a C
package that performs Gibbs energy minimization to compute the thermodynamically most stable
mineral assemblage for a given bulk-rock composition and pressure/temperature condition.

## Relation to MAGEMin / MAGEMin_C.jl

This project vendors a copy of the upstream `MAGEMin` C library and its Julia bindings,
[`MAGEMin_C.jl`](https://github.com/ComputationalThermodynamics/MAGEMin_C.jl), for reference.
`magemin` wraps MAGEMin's own official minimal C API (`MAGEMin_api.h`) via
[`ctypes`](https://docs.python.org/3/library/ctypes.html) -- a small, stable 5-function surface
(`MAGEMin_Init`, `MAGEMin_NOxides`, `MAGEMin_OxideNames`, `MAGEMin_ComputeEquilibrium`,
`MAGEMin_Free`) intended by upstream for external C/C++ callers. A companion C extension,
`magemin_ext/`, extends this with oxygen-buffer/fixed-activity constraints, phase suppression,
`sb`/`gh` (Stixrude & Lithgow-Bertelloni / MELTS) database support, and reduced-memory output --
by calling MAGEMin's existing internal functions through its unmodified headers, so a future
MAGEMin update just drops in a fresh copy and rebuilds.

Concretely, this means `magemin`:

- Wraps [`MAGEMin.compute()`][magemin.core.MAGEMin.compute] around one well-defined entry point
  (`MAGEMin_ComputeEquilibriumEx`), returning a fully self-contained
  [`EquilibriumResult`][magemin.results.EquilibriumResult] (no live pointers into C memory survive
  the call).
- Ships a handful of hand-curated [predefined bulk-rock compositions][magemin.bulk_rocks.BulkRock]
  as plain Python data, rather than binding MAGEMin's internal composition-lookup functions.
- Parallelizes [`multi_point_minimization()`][magemin.core.multi_point_minimization] with a plain
  Python thread pool (one MAGEMin handle per worker thread) instead of MPI.
- Builds adaptively refined PT/PX/TX pseudosections two ways:
  [`PhaseDiagram`][magemin.diagrams.PhaseDiagram] (a quadtree grid, filled-region plotting) and
  [`Pseudosection`][magemin.pseudosection.Pseudosection] (a Delaunay mesh, scatter plotting;
  needs the optional `mesh` extra).

See [Scope and limitations](#scope-and-limitations) for what this means you *can't* do (yet).

## Quickstart

```python
from magemin import MAGEMin, bulk_rocks

with MAGEMin("ig") as mg:
    result = mg.compute(P=8, T=800, bulk=bulk_rocks.KLB1_IG)
    print(result)
```

```text
Pressure          : 8 [kbar]
Temperature       : 800 [Celsius]
Stable phase | Fraction (mol)  | Fraction (wt)
  opx          0.22805          0.23531
  ol           0.61182          0.58281
  cpx          0.13759          0.14893
  spl          0.02254          0.03294
Gibbs free energy : -797.787387
Density           : 3282.5560 [kg/m3]
Oxygen fugacity   : -13.5735
```

Oxygen buffers, phase suppression, and light-weight output are all one keyword argument each:

```python
result = mg.compute(P=8, T=800, bulk=bulk_rocks.KLB1_IG, buffer="cco", buffer_value=-1.0)
result = mg.compute(P=8, T=800, bulk=bulk_rocks.KLB1_IG, suppress_phases=["spl"])
result = mg.compute(P=8, T=800, bulk=bulk_rocks.KLB1_IG, light=True)
```

Adaptively refined PT/PX/TX pseudosections (`pip install magemin[plot]` for plotting):

```python
from magemin import PhaseDiagram

diagram = PhaseDiagram.pt(
    "ig", P=(2, 20), T=(700, 1300), bulk=bulk_rocks.KLB1_IG, initial_resolution=4, refine=3
)
diagram.show()
```

See [Installation](installation.md) to get set up, [Usage](usage.md) for the full walkthrough
(custom compositions, multi-point parallel runs, `Pseudosection`'s Delaunay-mesh alternative,
inspecting individual phases), and the [pseudosection tutorial](tutorial_pseudosection.md) for a
worked example end to end.

## Supported databases

| Acronym | Dataset |
|---|---|
| `ig` | Igneous (Green et al. 2025, updates Holland et al. 2018) |
| `igd`, `igad` | Igneous dry / alkaline dry variants |
| `mp`, `mpe` | Metapelite (White et al. 2014) / extended |
| `mb`, `mbe` | Metabasite (Green et al. 2016) / extended |
| `um`, `ume` | Ultramafic (Evans & Frost 2021) / extended |
| `mtl` | Mantle (Holland et al. 2013) |
| `sb11`, `sb21`, `sb24` | Stixrude & Lithgow-Bertelloni (2011/2021/2024) |
| `xMELTS`, `rMELTS`, `pMELTS` | MELTS |

`MAGEMin(database)` infers the research group (`tc`/`sb`/`gh`) from the acronym automatically.

## Scope and limitations

This package wraps MAGEMin's minimal C API plus the `magemin_ext/` companion extension. It does
**not** support (all of which `MAGEMin_C.jl` does, via its much larger internal-API bindings):

- Predefined bulk-rock compositions beyond the small hand-curated set in `bulk_rocks` (no lookup of
  MAGEMin's full internal `--test` composition tables)
- Fractional crystallization / PT-path drivers (build one yourself with repeated `compute()` calls,
  as `MAGEMin_C.jl`'s own examples do)
- Trace-element partitioning, melt-viscosity, or volatile-saturation post-processing models
- MPI-based multi-node parallelism (this package parallelizes with a thread pool instead, see
  `multi_point_minimization`)

If you need any of these, see
[`MAGEMin_C.jl`](https://github.com/ComputationalThermodynamics/MAGEMin_C.jl).

## License

GPLv3, matching the vendored `MAGEMin` C library this package wraps.
