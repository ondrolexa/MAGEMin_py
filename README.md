# magemin

Python interface to [MAGEMin](https://github.com/ComputationalThermodynamics/MAGEMin), a C
package that performs Gibbs energy minimization to compute the thermodynamically most stable
mineral assemblage for a given bulk-rock composition and pressure/temperature condition.

## Relation to MAGEMin / MAGEMin_C.jl

This repository vendors a copy of the upstream `MAGEMin` C library (`MAGEMin/`) and its Julia
bindings (`MAGEMin_C.jl/`) for reference. `magemin` wraps `MAGEMin`'s own official minimal C API
(`MAGEMin_api.h`) via [`ctypes`](https://docs.python.org/3/library/ctypes.html) -- a small, stable
5-function surface (`MAGEMin_Init`, `MAGEMin_NOxides`, `MAGEMin_OxideNames`,
`MAGEMin_ComputeEquilibrium`, `MAGEMin_Free`) intended by upstream for external C/C++ callers.
`magemin_ext/` adds a small companion C extension on top of it (buffer/activity fixing, phase
suppression, `sb`/`gh` database support, phase-name discovery) by calling MAGEMin's existing
internal functions through its unmodified headers -- nothing under `MAGEMin/` is ever edited, so a
future MAGEMin update just drops in a fresh copy and rebuilds. See [Scope and
limitations](#scope-and-limitations) for what's still out of scope.

## Installation

```sh
uv sync
```

Building the C library additionally requires:

- A C compiler (e.g. `gcc` or `clang`)
- `liblapacke-dev`
- `libnlopt-dev`

On Debian/Ubuntu:

```sh
sudo apt install liblapacke-dev libnlopt-dev
```

Then build the library:

```sh
./scripts/build_lib.sh
```

This runs `make lib` inside `MAGEMin/` (with `USE_MPI=0`, since neither the API nor this package's
parallelism needs MPI), compiles the `magemin_ext/` companion extension, and links everything into
one `MAGEMin/libMAGEMin.so`. The vendored source location defaults to `./MAGEMin` and can be
overridden with `MAGEMIN_SRC_DIR`; nothing under it is ever modified by this build.

If your compiled library lives elsewhere, point `magemin` at it with:

```sh
export MAGEMIN_LIB_PATH=/path/to/libMAGEMin.so
```

Don't have a vendored `MAGEMin/` tree? `magemin-install` downloads and builds one automatically
(Linux/macOS/Windows -- see `docs/installation.md` for version pinning, custom compiler/flag
options, and Windows/MSYS2 notes):

```sh
uv run magemin-install
```

Want `PhaseDiagram.plot()`? Install the optional `plot` extra:

```sh
pip install magemin[plot]
```

## Quickstart

Predefined composition:

```python
from magemin import MAGEMin, bulk_rocks

with MAGEMin("ig") as mg:
    result = mg.compute(P=8, T=800, bulk=bulk_rocks.KLB1_IG)
    print(result)
```

```
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

Custom composition:

```python
with MAGEMin("ig") as mg:
    print(mg.oxide_names)
    #  ('SiO2', 'Al2O3', 'CaO', 'MgO', 'FeO', 'K2O', 'Na2O', 'TiO2', 'O', 'Cr2O3', 'H2O')
    bulk = [50.0, 15.0, 10.0, 8.0, 9.0, 0.5, 3.0, 1.5, 0.0, 0.0, 2.0]
    result = mg.compute(P=10, T=1100, bulk=bulk, sys_in="wt")
    print(result.rho, result.ph, result.ph_frac)
```

Many points in parallel (one `MAGEMin` handle per worker thread):

```python
from magemin import Point, bulk_rocks, multi_point_minimization

points = [Point(P=p, T=t, bulk=bulk_rocks.KLB1_IG) for p, t in [(5, 700), (10, 900), (15, 1100)]]
results = multi_point_minimization("ig", points)
```

Adaptively refined PT/PX/TX phase diagrams (`pip install magemin[plot]` for plotting):

```python
from magemin import PhaseDiagram

diagram = PhaseDiagram.pt(
    "ig", P=(2, 20), T=(700, 1300), bulk=bulk_rocks.KLB1_IG, initial_resolution=4, refine=3
)
diagram.show()
```

Or the same idea on a Delaunay mesh instead of a quadtree grid
(`pip install magemin[mesh]` for `numpy`/`scipy`):

```python
from magemin import Pseudosection

mesh = Pseudosection.pt(
    "ig", P=(2, 20), T=(700, 1300), bulk=bulk_rocks.KLB1_IG, initial_resolution=4, refine=3
)
mesh.show()
```

Oxygen buffers, phase suppression, and light-weight output (see `docs/usage.md`, or the published
docs site, for the full walkthrough):

```python
result = mg.compute(P=8, T=800, bulk=bulk_rocks.KLB1_IG, buffer="cco", buffer_value=-1.0)
result = mg.compute(P=8, T=800, bulk=bulk_rocks.KLB1_IG, suppress_phases=["spl"])
result = mg.compute(P=8, T=800, bulk=bulk_rocks.KLB1_IG, light=True)
```

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

## Development

```sh
uv sync --group dev
uv run pytest
uv run ruff check .
uv run ruff format .
```

Most tests require the compiled library (`./scripts/build_lib.sh`) and are skipped gracefully if
it isn't built.

### Documentation site

Full documentation (installation, usage examples, and a detailed API reference for every public
class/function/dataclass field) is built with [MkDocs](https://www.mkdocs.org/) +
[mkdocstrings](https://mkdocstrings.github.io/):

```sh
uv sync --group docs
uv run mkdocs serve   # live-reloading local preview at http://127.0.0.1:8000
uv run mkdocs build   # static site in site/
```

## Scope and limitations

This package wraps MAGEMin's minimal C API plus a small companion extension (`magemin_ext/`) for
buffer/activity fixing, phase suppression, `sb`/`gh` database support, and light output mode. It
does **not** support (all of which `MAGEMin_C.jl` does, via its much larger internal-API bindings):

- Predefined bulk-rock compositions beyond the small hand-curated set in `bulk_rocks` (no lookup of
  MAGEMin's full internal `--test` composition tables)
- Fractional crystallization / PT-path drivers (build one yourself with repeated `compute()` calls,
  as MAGEMin_C.jl's own examples do)
- Trace-element partitioning, melt-viscosity, or volatile-saturation post-processing models
- MPI-based multi-node parallelism (this package parallelizes with a thread pool instead, see
  `multi_point_minimization`)

If you need any of these, see [`MAGEMin_C.jl`](https://github.com/ComputationalThermodynamics/MAGEMin_C.jl).

## License

GPLv3, matching the vendored `MAGEMin` C library this package wraps. See `LICENSE`.
