# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

Nothing released yet -- development to date is summarized below.

### Added

- `MAGEMin`/`Point`/`multi_point_minimization`: a `ctypes` wrapper around MAGEMin's official
  minimal C API.
- `magemin_ext/`, a companion C extension adding oxygen-buffer/fixed-activity constraints, phase
  suppression, `sb`/`gh` (Stixrude & Lithgow-Bertelloni / MELTS) database support, and a
  reduced-memory `light` output mode.
- `solvus_name`/`base_phase_name` (`_solvus.py`): solvus-disambiguated mineral naming, ported from
  `MAGEMin_C.jl`, on by default via `compute(..., name_solvus=True)`.
- `magemin-install` console script (`_download.py`): downloads and builds a MAGEMin source
  release from GitHub.
- `solver` kwarg on `MAGEMin`/`multi_point_minimization`/`PhaseDiagram.{pt,px,tx}` for selecting
  among MAGEMin's alternate equilibrium solvers.
- `PhaseDiagram`: adaptively refined PT/PX/TX phase diagrams on a quadtree grid, with
  `.refine()`, `.validate()`, `.plot()`/`.show()`, and `.plot_grid()`/`.show_grid()`.
- `Pseudosection`: an adaptive Delaunay-mesh alternative to `PhaseDiagram`, with
  `.refine()`/`.validate()`/`.plot()`/`.show()`.
- Optional `plot` (`matplotlib`) and `mesh` (`numpy`+`scipy`) extras, lazily imported so neither is
  required just to `import magemin`.
- A thread-safe `multi_point_minimization`, relying on MAGEMin's thread-safe endmember-lookup
  registry; concurrent handles for the same or different databases give correct results.
- `use_phases` kwarg on `MAGEMin.compute`: an allowlist of solution phases to keep active,
  implemented as the complement of `suppress_phases` (mutually exclusive with it).
- Solvus naming for the `"all"` database's new Mn-bearing ilmenite model `ilmmn_W14`.
- Requires MAGEMin **2.0.7 or newer** (`magemin-install` and `scripts/build_lib.sh` refuse older
  source trees).
