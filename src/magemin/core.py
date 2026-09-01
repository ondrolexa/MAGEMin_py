"""Public API: the `MAGEMin` handle class and multi-point parallel helper."""

from __future__ import annotations

import ctypes
import os
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import Literal, NamedTuple

from magemin import _lib
from magemin.bulk_rocks import BulkRock
from magemin.errors import (
    BulkCompositionError,
    MAGEMinClosedHandleError,
    MAGEMinComputeError,
    MAGEMinInitError,
)
from magemin.results import EquilibriumResult

_VALID_SYS_IN = ("mol", "wt")

_TC_DATABASES = frozenset(
    {"mpf", "mp", "mb", "mbe", "ig", "igd", "igad", "um", "ume", "mtl", "mpe", "all"}
)
_SB_DATABASES = frozenset({"sb11", "sb21", "sb24"})
_GH_DATABASES = frozenset({"xMELTS", "rMELTS", "pMELTS"})
_VALID_DATABASES = _TC_DATABASES | _SB_DATABASES | _GH_DATABASES


def _research_group_for(database: str) -> str:
    """Return the research_group ("tc"/"sb"/"gh") a database acronym belongs to."""
    if database in _SB_DATABASES:
        return "sb"
    if database in _GH_DATABASES:
        return "gh"
    return "tc"


_REDOX_BUFFERS = frozenset({"O2", "qfm", "mw", "qif", "nno", "hm", "iw", "cco"})
_ACTIVITY_BUFFERS = frozenset({"aH2O", "aO2", "aMgO", "aFeO", "aAl2O3", "aTiO2"})
_VALID_BUFFERS = _REDOX_BUFFERS | _ACTIVITY_BUFFERS

_VALID_SOLVERS = frozenset({0, 1, 2, 3})


class MAGEMin:
    """Persistent interface to one initialized MAGEMin thermodynamic database.

    Wraps a single MAGEMin C handle, reusable across many `compute()` calls.
    Not safe to share a single instance across threads -- create one instance
    per thread for concurrent work (see `multi_point_minimization`). Concurrent
    instances for the *same* database are safe (an internal lock in
    `magemin_ext.c` guards the underlying C library's shared endmember-lookup
    tables); concurrent instances for genuinely different databases across
    threads are memory-safe but not guaranteed to return correct results, since
    that lookup state is shared per-process, not per-handle -- stick to one
    database per concurrent batch, as `multi_point_minimization` already does.

    Example:
        with MAGEMin("ig") as mg:
            result = mg.compute(P=8, T=800, bulk=bulk_rocks.KLB1_IG)
    """

    def __init__(self, database: str, *, verbose: bool = False, solver: int = 2) -> None:
        """Initialize a MAGEMin database handle.

        Args:
            database: Database acronym. "tc"-family: "ig", "igd", "igad",
                "mp", "mpe", "mpf", "mb", "mbe", "um", "ume", "mtl", "all".
                "sb"-family (Stixrude & Lithgow-Bertelloni): "sb11", "sb21",
                "sb24". "gh"-family (MELTS): "xMELTS", "rMELTS", "pMELTS". The
                research group is inferred automatically.
            verbose: Whether the underlying C library should print progress
                information to stdout during minimization.
            solver: Which local-minimizer algorithm the underlying C library
                uses: `0` = legacy, `1` = PGE + legacy hybrid, `2` = hybrid
                PGE/LP (MAGEMin's own library default -- unchanged from this
                package's behavior before `solver` existed). `3` is a
                "metastable calculation, no minimization" diagnostic mode
                (the underlying library's own description), not a normal
                alternate equilibrium solver -- it can return duplicate
                phase-name entries in a result's `ph` (multiple raw
                pseudocompounds for one phase, not deduplicated into a
                single equilibrium answer); avoid it unless you specifically
                want that raw pseudocompound dump. Set once here; stable for
                this instance's whole lifetime (never reset by `compute()`,
                unlike `buffer`/`suppress_phases`). Forced to `0` by the
                underlying library for `"sb"`/`"gh"`-family databases
                regardless of what's requested here -- those only support
                the legacy solver upstream. Different solvers (0/1/2) can
                converge to different local minima for near-degenerate phase
                pairs -- e.g. at `P=10, T=790` for a typical `"mp"`-database
                metapelite bulk, `solver=0` finds the feldspar solvus splits
                into both `"afs"` and `"pl"`, while the default `solver=2`
                finds only `"pl"` stable. Pass `2` (the default) unless
                you're specifically exploring this kind of sensitivity.

        Raises:
            MAGEMinLibraryNotFoundError: If libMAGEMin cannot be located.
            MAGEMinInitError: If `database` is unrecognized, `solver` is not
                `0`/`1`/`2`/`3`, or the underlying init call fails.
        """
        self._closed = True  # set before anything that can raise, for __del__ safety
        if database not in _VALID_DATABASES:
            raise MAGEMinInitError(
                f"unknown database acronym {database!r}; expected one of {sorted(_VALID_DATABASES)}"
            )
        if solver not in _VALID_SOLVERS:
            raise MAGEMinInitError(
                f"solver must be one of {sorted(_VALID_SOLVERS)}, got {solver!r}"
            )
        research_group = _research_group_for(database)
        self._lib = _lib.get_library()
        handle = self._lib.MAGEMin_InitEx(
            database.encode(), research_group.encode(), 1 if verbose else 0, solver
        )
        if not handle:
            raise MAGEMinInitError(f"MAGEMin_InitEx failed for database {database!r}")
        self._handle = handle
        self._closed = False
        self._database = database
        self._solver = solver
        self._n_oxides = self._lib.MAGEMin_NOxides(self._handle)
        names_ptr = self._lib.MAGEMin_OxideNames(self._handle)
        self._oxide_names = tuple(names_ptr[i].decode() for i in range(self._n_oxides))
        n_ss = self._lib.MAGEMin_NSolutionPhases(self._handle)
        ss_ptr = self._lib.MAGEMin_SolutionPhaseNames(self._handle)
        self._solution_phase_names = tuple(ss_ptr[i].decode() for i in range(n_ss))
        n_pp = self._lib.MAGEMin_NPurePhases(self._handle)
        pp_ptr = self._lib.MAGEMin_PurePhaseNames(self._handle)
        self._pure_phase_names = tuple(pp_ptr[i].decode() for i in range(n_pp))

    @property
    def database(self) -> str:
        """The database acronym this instance was initialized with."""
        return self._database

    @property
    def solver(self) -> int:
        """The solver value this instance was initialized with (see `__init__`)."""
        return self._solver

    @property
    def n_oxides(self) -> int:
        """Number of oxide/system components expected in a bulk composition."""
        return self._n_oxides

    @property
    def oxide_names(self) -> tuple[str, ...]:
        """Oxide names, in the order expected by `compute`'s `bulk` argument."""
        return self._oxide_names

    @property
    def solution_phase_names(self) -> tuple[str, ...]:
        """Solution-phase model names, valid for `compute`'s `suppress_phases`."""
        return self._solution_phase_names

    @property
    def pure_phase_names(self) -> tuple[str, ...]:
        """Pure-phase names, valid for `compute`'s `suppress_phases`."""
        return self._pure_phase_names

    def compute(
        self,
        P: float,
        T: float,
        bulk: Sequence[float] | BulkRock,
        sys_in: Literal["mol", "wt"] | None = None,
        *,
        buffer: str | None = None,
        buffer_value: float | None = None,
        suppress_phases: Sequence[str] | None = None,
        light: bool = False,
        name_solvus: bool = True,
    ) -> EquilibriumResult:
        """Compute the stable equilibrium phase assemblage at one (P, T) point.

        Args:
            P: Pressure in kbar.
            T: Temperature in Celsius.
            bulk: Bulk composition, either a plain sequence of `n_oxides`
                values in `oxide_names` order, or a `BulkRock` predefined
                composition.
            sys_in: Composition unit, "mol" or "wt". Required when `bulk` is a
                plain sequence; defaults to `bulk.sys_in` when `bulk` is a
                `BulkRock` and this is left as `None`.
            buffer: Oxygen buffer ("O2", "qfm", "mw", "qif", "nno", "hm",
                "iw", "cco") or fixed-activity constraint ("aH2O", "aO2",
                "aMgO", "aFeO", "aAl2O3", "aTiO2") to apply, or `None` for
                none. Must be given together with `buffer_value`. This is
                re-applied (or explicitly cleared) on every `compute()` call
                -- it never silently carries over from a previous call on
                this same instance.
            buffer_value: For a redox `buffer`, an additive log-unit offset
                (e.g. dQFM-style, can be negative, unclamped). For a
                fixed-activity `buffer`, the activity value itself, in
                `(0, 1)`. Required together with `buffer`.
            suppress_phases: Solution-phase or pure-phase names (see
                `solution_phase_names`/`pure_phase_names`) to exclude from
                this point's minimization.
            light: If True, skip building `solution_phases`/
                `metastable_phases`/`pure_phases` on the result (left as
                empty tuples) -- faster/lighter when only the phase-summary
                arrays (`ph`, `ph_frac`, ...) are needed, e.g. for large
                `multi_point_minimization` sweeps.
            name_solvus: If True (the default), disambiguate solution-phase
                entries in the result's `ph` (e.g. `"fsp"` into `"pl"`/`"afs"`)
                using each phase's compositional variables -- see
                `magemin.solvus_name`. Pass False to get the raw
                solution-model names instead (needed e.g. to match
                `suppress_phases`, which expects raw names -- see
                `magemin.base_phase_name` to convert back). Works
                independently of `light`.

        Returns:
            The computed equilibrium result.

        Raises:
            MAGEMinClosedHandleError: If this instance has been closed.
            BulkCompositionError: If `bulk`'s length or oxide set doesn't
                match this database's oxides.
            MAGEMinComputeError: If `sys_in`/`buffer`/`buffer_value` is
                invalid, or the underlying computation fails (including an
                unrecognized `suppress_phases` name).
        """
        if self._closed:
            raise MAGEMinClosedHandleError("MAGEMin instance is closed")

        if isinstance(bulk, BulkRock):
            if bulk.database != self._database or bulk.oxides != self._oxide_names:
                raise BulkCompositionError(
                    f"BulkRock {bulk.name!r} is defined for database "
                    f"{bulk.database!r} with oxides {bulk.oxides}, which does not "
                    f"match this instance's database {self._database!r} with "
                    f"oxides {self._oxide_names}"
                )
            values = bulk.values
            if sys_in is None:
                sys_in = bulk.sys_in
        else:
            values = tuple(bulk)
            if len(values) != self._n_oxides:
                raise BulkCompositionError(
                    f"bulk has {len(values)} values, expected {self._n_oxides} "
                    f"({', '.join(self._oxide_names)})"
                )
            if sys_in is None:
                raise MAGEMinComputeError(
                    "sys_in is required ('mol' or 'wt') when bulk is a plain sequence"
                )

        if sys_in not in _VALID_SYS_IN:
            raise MAGEMinComputeError(f"sys_in must be 'mol' or 'wt', got {sys_in!r}")

        if (buffer is None) != (buffer_value is None):
            raise MAGEMinComputeError("buffer and buffer_value must be given together")
        if buffer is not None:
            if buffer not in _VALID_BUFFERS:
                raise MAGEMinComputeError(
                    f"unrecognized buffer {buffer!r}; expected one of {sorted(_VALID_BUFFERS)}"
                )
            if buffer in _ACTIVITY_BUFFERS and not (0.0 < buffer_value < 1.0):
                raise MAGEMinComputeError(
                    f"buffer_value for activity buffer {buffer!r} must be in "
                    f"(0, 1), got {buffer_value}"
                )

        # Re-applied on every call: gv.buffer/gv.buffer_n persist on the C
        # handle across calls, so a previous call's buffer must be explicitly
        # cleared here rather than relying on it resetting itself.
        rc = self._lib.MAGEMin_SetBuffer(
            self._handle,
            (buffer or "none").encode(),
            float(buffer_value) if buffer_value is not None else 0.0,
        )
        if rc != 0:
            raise MAGEMinComputeError(
                f"buffer {buffer!r} is not available for database {self._database!r}"
            )

        if suppress_phases:
            encoded = [name.encode() for name in suppress_phases]
            suppress_array = (ctypes.c_char_p * len(encoded))(*encoded)
            n_suppress = len(encoded)
        else:
            suppress_array = None
            n_suppress = 0

        bulk_array = (ctypes.c_double * self._n_oxides)(*values)
        result_ptr = self._lib.MAGEMin_ComputeEquilibriumEx(
            self._handle,
            float(P),
            float(T),
            bulk_array,
            sys_in.encode(),
            suppress_array,
            n_suppress,
        )
        if not result_ptr:
            raise MAGEMinComputeError(
                f"MAGEMin_ComputeEquilibriumEx failed for P={P}, T={T} "
                "(check suppress_phases against solution_phase_names/pure_phase_names)"
            )
        return EquilibriumResult._from_c(result_ptr.contents, light=light, name_solvus=name_solvus)

    def close(self) -> None:
        """Free the underlying MAGEMin handle. Safe to call more than once."""
        if not self._closed:
            self._lib.MAGEMin_Free(self._handle)
            self._closed = True

    def __enter__(self) -> MAGEMin:
        """Return self for use as a context manager."""
        return self

    def __exit__(self, *exc_info: object) -> None:
        """Close the handle on context-manager exit."""
        self.close()

    def __del__(self) -> None:
        """Best-effort cleanup if `close()` was never called explicitly."""
        if not getattr(self, "_closed", True):
            self.close()


class Point(NamedTuple):
    """One (P, T, bulk) minimization point for `multi_point_minimization`.

    Attributes:
        P: Pressure in kbar.
        T: Temperature in Celsius.
        bulk: Bulk composition, either a plain sequence of values in the
            target database's oxide order, or a `BulkRock` predefined
            composition.
        sys_in: Composition unit, `"mol"` or `"wt"`. Required when `bulk` is
            a plain sequence; defaults to `bulk.sys_in` when `bulk` is a
            `BulkRock` and this is left as `None`.
        buffer: Passed through to `MAGEMin.compute`'s `buffer` argument.
        buffer_value: Passed through to `MAGEMin.compute`'s `buffer_value`.
        suppress_phases: Passed through to `MAGEMin.compute`'s
            `suppress_phases`.
        light: Passed through to `MAGEMin.compute`'s `light`.
        name_solvus: Passed through to `MAGEMin.compute`'s `name_solvus`.
    """

    P: float
    T: float
    bulk: Sequence[float] | BulkRock
    sys_in: Literal["mol", "wt"] | None = None
    buffer: str | None = None
    buffer_value: float | None = None
    suppress_phases: Sequence[str] | None = None
    light: bool = False
    name_solvus: bool = True


def multi_point_minimization(
    database: str,
    points: Sequence[Point],
    *,
    verbose: bool = False,
    solver: int = 2,
    max_workers: int | None = None,
) -> list[EquilibriumResult]:
    """Compute equilibrium at many (P, T, bulk) points in parallel.

    Spreads `points` across a thread pool, each worker thread using its own
    `MAGEMin` handle for `database`. ctypes releases the GIL during the
    underlying C call, so this achieves real parallelism without MPI or
    multiprocessing.

    Args:
        database: Database acronym, passed to `MAGEMin(database)` per worker.
        points: The points to compute.
        verbose: Passed through to each worker's `MAGEMin` instance.
        solver: Passed through to each worker's `MAGEMin` instance; see
            `MAGEMin.__init__`.
        max_workers: Number of worker threads; defaults to
            `min(len(points), os.cpu_count())`.

    Returns:
        Results in the same order as `points`.
    """
    if not points:
        return []

    n_workers = max(1, min(max_workers or (os.cpu_count() or 1), len(points)))
    indexed = list(enumerate(points))
    chunks = [indexed[i::n_workers] for i in range(n_workers)]

    def _run_chunk(chunk: list[tuple[int, Point]]) -> list[tuple[int, EquilibriumResult]]:
        with MAGEMin(database, verbose=verbose, solver=solver) as mg:
            return [
                (
                    idx,
                    mg.compute(
                        point.P,
                        point.T,
                        point.bulk,
                        point.sys_in,
                        buffer=point.buffer,
                        buffer_value=point.buffer_value,
                        suppress_phases=point.suppress_phases,
                        light=point.light,
                        name_solvus=point.name_solvus,
                    ),
                )
                for idx, point in chunk
            ]

    with ThreadPoolExecutor(max_workers=n_workers) as executor:
        futures = [executor.submit(_run_chunk, chunk) for chunk in chunks]
        pairs = [pair for future in futures for pair in future.result()]

    pairs.sort(key=lambda pair: pair[0])
    return [result for _, result in pairs]
