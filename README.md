# magemin

Python interface to [MAGEMin](https://github.com/ComputationalThermodynamics/MAGEMin), a C
package that performs Gibbs energy minimization to compute the thermodynamically most stable
mineral assemblage for a given bulk-rock composition and pressure/temperature condition.

## Relation to MAGEMin

`magemin` wraps `MAGEMin`'s own official C API (`MAGEMin_api.h`) via
[`ctypes`](https://docs.python.org/3/library/ctypes.html) -- a small, stable surface intended by
upstream for external C/C++ callers: init/compute/free, oxide and phase names, solver choice,
oxygen buffer / fixed activity, and phase suppression. This package contains no C code of its
own; it loads the official prebuilt MAGEMin library (see [Installation](#installation)). See
[Scope and limitations](#scope-and-limitations) for what's still out of scope.

## Installation

```sh
pip install magemin
# or: uv add magemin
```

Then install the MAGEMin library itself (MAGEMin 2.0.8 or newer):

```sh
magemin-install
# or: uv run magemin-install
```

This downloads the official prebuilt MAGEMin binaries (`MAGEMin_jll`, built by Julia's
Yggdrasil for Linux, macOS and Windows) together with the runtime libraries they need into a
per-user cache directory -- no compiler or system packages required. Pin a release with
`magemin-install X.Y.Z`. See the [installation guide](https://github.com/ondrolexa/MAGEMin_py/blob/main/docs/installation.md) for all options.

If your compiled library lives elsewhere, point `magemin` at it with:

```sh
export MAGEMIN_LIB_PATH=/path/to/libMAGEMin.so
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

Want a pseudosection diagrams? For adaptively refined PT/PX/TX phase diagrams
(`pip install magemin[plot]` for plotting):

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

Oxygen buffers, phase suppression, and light-weight output (see the [usage guide](https://github.com/ondrolexa/MAGEMin_py/blob/main/docs/usage.md) for the full
walkthrough):

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
| `all` | All (union of mp/mb/mbe/ig/igd/igad/um/ume/mpe) + DEW aqueous-fluid model |
| `mtl` | Mantle (Holland et al. 2013) |
| `sb11`, `sb21`, `sb24` | Stixrude & Lithgow-Bertelloni (2011/2021/2024) |

`MAGEMin(database)` infers the research group (`tc`/`sb`) from the acronym automatically.

## Development

Clone this repo, then:

```sh
uv sync --group dev
uv run pytest
uv run ruff check .
uv run ruff format .
```

Most tests require the compiled library (`uv run magemin-install`, or
`MAGEMIN_SRC_DIR=/path/to/MAGEMin ./scripts/build_lib.sh` for a MAGEMin source checkout) and are
skipped gracefully if it isn't available.

### Building MAGEMin's main branch

To use unreleased MAGEMin changes, download and build the tip of its `main` branch (or any other
git ref) instead:

```sh
magemin-install latest              # main branch (HEAD)
magemin-install some-ref            # any other branch/tag/commit SHA
```

This needs `make`, a C compiler, LAPACKE and NLopt (`sudo apt install liblapacke-dev
libnlopt-dev` on Debian/Ubuntu). See the [installation guide](https://github.com/ondrolexa/MAGEMin_py/blob/main/docs/installation.md#building-from-source-developers) for details.

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

This package wraps MAGEMin's C API (`MAGEMin_api.h`), which covers buffer/activity fixing,
phase suppression and the `sb` databases. It does **not** support:

- Predefined bulk-rock compositions beyond the small hand-curated set in `bulk_rocks` (no lookup of
  MAGEMin's full internal `--test` composition tables)
- Fractional crystallization / PT-path drivers (build one yourself with repeated `compute()`
  calls)
- Trace-element partitioning, melt-viscosity, or volatile-saturation post-processing models
- MPI-based multi-node parallelism (this package parallelizes with a thread pool instead, see
  `multi_point_minimization`)

## Credits

All thermodynamic modeling is done by [`MAGEMin`](https://github.com/ComputationalThermodynamics/MAGEMin)
itself; this package only adds a Python interface around it. `MAGEMin` is developed by Nicolas
Riel and Boris Kaus (Johannes Gutenberg University Mainz), with Erik C. R. Green and Nathan
Berlie. If you use `magemin` in published work, please cite the original `MAGEMin` paper:

> Riel N., Kaus B.J.P., Green E.C.R., Berlie N. (2022). MAGEMin, an Efficient Gibbs Energy
> Minimizer: Application to Igneous Systems. *Geochemistry, Geophysics, Geosystems* 23,
> e2022GC010427. [doi:10.1029/2022GC010427](https://doi.org/10.1029/2022GC010427)

## License

GPLv3, matching the `MAGEMin` C library this package wraps. See `LICENSE`.
