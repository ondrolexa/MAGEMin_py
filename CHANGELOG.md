# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.1] - 2026-10-13

### Added

- Fixed chemical potentials: `MAGEMin(mu_fix=[...])` + `compute(..., mu_fix_values=[...])`.
- Seismic averaging scheme: `MAGEMin(seismic_scheme="VRH"|"HS", seismic_weight=...)`.
- `compute()` warns when a buffer or fixed chemical potential is not actually reached.
- All functions exported by the MAGEMin 2.0.8 C API are now wrapped.

### Fixed

- `PhaseDiagram` no longer turns failed points (`status != 0`) into fields.
- Docs: phase `f` is a normalization factor, not a proportion; compositions are fractions.
- Docs: status codes, repeated phase names, and the excess-component requirement for buffers.

## [0.1.0] - 2026-10-12

First public release.

### Added

- `MAGEMin`/`Point`/`multi_point_minimization`: `ctypes` wrapper of MAGEMin's C API.
- Oxygen buffers, fixed activities, phase suppression (`suppress_phases`/`use_phases`).
- `solver`, `optimizer` and `final_newton_step` options; `store_kkt` final Newton system.
- Solvus-disambiguated phase names (`name_solvus`), `light` output mode.
- `PhaseDiagram` (adaptive quadtree) and `Pseudosection` (adaptive Delaunay mesh).
- Optional `plot` and `mesh` extras.
- `magemin-install`: prebuilt MAGEMin binaries, or source builds of unreleased versions.
- Requires MAGEMin 2.0.8 or newer.

[Unreleased]: https://github.com/ondrolexa/MAGEMin_py/compare/v0.1.1...HEAD
[0.1.1]: https://github.com/ondrolexa/MAGEMin_py/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/ondrolexa/MAGEMin_py/releases/tag/v0.1.0
