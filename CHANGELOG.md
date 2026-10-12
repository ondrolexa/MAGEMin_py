# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.0] - 2026-10-12

First public release.

### Added

- `MAGEMin`/`Point`/`multi_point_minimization`: a `ctypes` wrapper around MAGEMin's official
  C API (`MAGEMin_api.h`), including oxygen-buffer/fixed-activity constraints, phase suppression,
  solver choice and the `sb` (Stixrude & Lithgow-Bertelloni) databases, plus a reduced-memory
  `light` output mode. The package contains no C code of its own.
- `solvus_name`/`base_phase_name` (`_solvus.py`): solvus-disambiguated mineral naming, ported from
  `MAGEMin_C.jl`, on by default via `compute(..., name_solvus=True)`.
- `magemin-install` console script (`_download.py`): installs the official prebuilt MAGEMin
  binaries (`MAGEMin_jll`) with their runtime libraries -- no compiler needed -- or builds an
  unreleased source tree (`latest`, any git ref, `--from-source`).
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
- `optimizer` and `final_newton_step` kwargs on `MAGEMin`/`multi_point_minimization`/
  `PhaseDiagram.{pt,px,tx}`/`Pseudosection.{pt,px,tx}` (MAGEMin 2.0.8's `MAGEMin_SetSSSolver`/
  `MAGEMin_SetFinalNewtonStep`): the nullspace solution-phase minimizer of the legacy solver
  (which also handles systems below FMAS) and the final Newton polish of the converged assemblage.
- `compute(..., store_kkt=True)`/`Point.store_kkt`: the final Newton (KKT) system at the converged
  state -- Jacobian, residual, chemical potentials and phase amounts -- as
  `EquilibriumResult.final_newton_system` (`FinalNewtonSystem`).
- Requires MAGEMin **2.0.8 or newer**, the first release with the C API above; `magemin-install`
  installs its prebuilt binaries by default and refuses older releases. `magemin-install latest`
  builds MAGEMin's `main` branch instead, for unreleased changes.
- `magemin-install` retries transient download failures (HTTP 5xx, connection errors).

[Unreleased]: https://github.com/ondrolexa/MAGEMin_py/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/ondrolexa/MAGEMin_py/releases/tag/v0.1.0
