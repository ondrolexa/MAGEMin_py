"""Public API: the `MAGEMin` handle class and multi-point parallel helper."""

from __future__ import annotations

import ctypes
import os
import warnings
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
from magemin.results import EquilibriumResult, FinalNewtonSystem

_VALID_SYS_IN = ("mol", "wt")

# "mpf" is deliberately absent: upstream's SetupDatabase maps it to EM_database = -1, but no
# database-init branch handles -1 (gv.ox is never populated), so global_variable_TC_init
# segfaults on it. Rejected here as an unknown acronym (a clean MAGEMinInitError) instead of
# killing the interpreter.
_TC_DATABASES = frozenset(
    {"mp", "mb", "mbe", "ig", "igd", "igad", "um", "ume", "mtl", "mpe", "all"}
)
_SB_DATABASES = frozenset({"sb11", "sb21", "sb24"})
# "gh" (MELTS) family: implemented upstream but not yet released -- upstream author
# (Nicolas Riel) asked that these stay unlisted/deactivated here until he's benchmarked
# them against Mark Ghiorso's own MELTS implementation and given the go-ahead. Kept
# defined (not deleted) so re-enabling is a one-line change: fold back into
# _VALID_DATABASES below.
_GH_DATABASES = frozenset({"xMELTS", "rMELTS", "pMELTS"})
_VALID_DATABASES = _TC_DATABASES | _SB_DATABASES


_REDOX_BUFFERS = frozenset({"O2", "qfm", "mw", "qif", "nno", "hm", "iw", "cco"})
_ACTIVITY_BUFFERS = frozenset({"aH2O", "aO2", "aMgO", "aFeO", "aAl2O3", "aTiO2"})
_VALID_BUFFERS = _REDOX_BUFFERS | _ACTIVITY_BUFFERS

_VALID_SOLVERS = frozenset({0, 1, 2, 3})
_VALID_OPTIMIZERS = frozenset({0, 1, 2})
_SEISMIC_SCHEMES = {"VRH": 0, "HS": 1}
# MAGEMin's mu_fix_idx/mu_fix_val arrays hold maxlen_ox = 16 entries; MAGEMin_InitMuFix writes
# past them for more names before validating anything, so the count is capped here first.
_MAX_MU_FIX = 16


class MAGEMin:
    """Persistent interface to one initialized MAGEMin thermodynamic database.

    Wraps a single MAGEMin C handle, reusable across many `compute()` calls.
    Not safe to share a single instance across threads -- create one instance
    per thread for concurrent work (see `multi_point_minimization`). Concurrent
    instances, for the same or different databases, are safe.

    Example:
        with MAGEMin("ig") as mg:
            result = mg.compute(P=8, T=800, bulk=bulk_rocks.KLB1_IG)
    """

    def __init__(
        self,
        database: str,
        *,
        verbose: bool = False,
        solver: int = 2,
        optimizer: int = 0,
        final_newton_step: bool = True,
        mu_fix: Sequence[str] = (),
        seismic_scheme: Literal["VRH", "HS"] = "VRH",
        seismic_weight: float = 0.5,
    ) -> None:
        """Initialize a MAGEMin database handle.

        Args:
            database: Database acronym. "tc"-family: "ig", "igd", "igad",
                "mp", "mpe", "mb", "mbe", "um", "ume", "mtl", "all".
                "sb"-family (Stixrude & Lithgow-Bertelloni): "sb11", "sb21",
                "sb24". The research group is inferred automatically.
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
                the legacy solver upstream. Solvers 0 and 2 normally
                converge to the same equilibrium; pass `2` (the default)
                unless you're specifically comparing solvers.
            optimizer: Local minimizer of the solution phases used by the
                legacy solver (`solver=0`) for the `"tc"`- and `"sb"`-family
                databases: `0` = NLopt (the default), `1` = nullspace
                minimizer with NLopt fallback, `2` = both, keeping the lower
                Gibbs energy. With `1`/`2`, oxides set exactly to zero in the
                bulk are removed from the system, so systems below FMAS (e.g.
                MS, MAS, CMAS) can be computed directly; NLopt instead raises
                the core oxides (`SiO2`, `Al2O3`, `MgO`, `FeO`) to at least
                1e-4. No effect with any other `solver`. Set once here, like
                `solver`.
            final_newton_step: Whether to polish the converged assemblage with
                a final Newton step (`"tc"`- and `"sb"`-family databases), which
                solves its equilibrium conditions to machine precision so that
                chemical potentials, phase fractions and compositions are
                mutually consistent; the solver result is kept whenever the
                step does not converge. Set once here, like `solver`. It is
                skipped while any chemical potential is fixed (`mu_fix`).
            mu_fix: Oxide names (from this database's `oxide_names`, e.g.
                `("MgO", "K2O")`) whose chemical potential is fixed directly
                instead of solved for from the bulk composition. The target
                values are passed to every `compute()` call as
                `mu_fix_values`. Each fixed oxide adds a fictive pure phase
                `"m<oxide>"` (e.g. `"mMgO"`) at the end of `pure_phase_names`,
                which appears in a result's `ph` while its target holds. Fixed
                for this instance's whole lifetime. Empty (the default) fixes
                nothing.
            seismic_scheme: How the phases' elastic moduli are averaged into
                the system's seismic properties (`vp`, `vs`, `bulk_mod`,
                `shear_mod`, ...): `"VRH"` (Voigt-Reuss-Hill, the default) or
                `"HS"` (Hashin-Shtrikman). Set once here, like `solver`.
            seismic_weight: Position between the soft and the stiff bound of
                `seismic_scheme`, in `[0, 1]`: for `"VRH"`, `0` = Reuss,
                `0.5` = classic VRH (the default), `1` = Voigt; for `"HS"`,
                `0` = HS-, `0.5` = HS average, `1` = HS+.

        Raises:
            MAGEMinLibraryNotFoundError: If libMAGEMin cannot be located.
            MAGEMinInitError: If `database` is unrecognized, `solver` is not
                `0`/`1`/`2`/`3`, `optimizer` is not `0`/`1`/`2`, `mu_fix` names
                an oxide twice, more than 16 oxides, or an oxide this database
                lacks, `seismic_scheme`/`seismic_weight` is invalid, or the
                underlying init call fails.
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
        if optimizer not in _VALID_OPTIMIZERS:
            raise MAGEMinInitError(
                f"optimizer must be one of {sorted(_VALID_OPTIMIZERS)}, got {optimizer!r}"
            )
        mu_fix = tuple(mu_fix)
        if not all(isinstance(name, str) for name in mu_fix):
            raise MAGEMinInitError(f"mu_fix must contain oxide names, got {mu_fix!r}")
        if len(set(mu_fix)) != len(mu_fix):
            raise MAGEMinInitError(f"mu_fix names an oxide more than once: {mu_fix!r}")
        if len(mu_fix) > _MAX_MU_FIX:
            raise MAGEMinInitError(
                f"mu_fix can fix at most {_MAX_MU_FIX} oxides, got {len(mu_fix)}"
            )
        if seismic_scheme not in _SEISMIC_SCHEMES:
            raise MAGEMinInitError(
                f"seismic_scheme must be one of {sorted(_SEISMIC_SCHEMES)}, got {seismic_scheme!r}"
            )
        if not 0.0 <= seismic_weight <= 1.0:
            raise MAGEMinInitError(f"seismic_weight must be in [0, 1], got {seismic_weight!r}")
        self._lib = _lib.get_library()
        if mu_fix:
            names = (ctypes.c_char_p * len(mu_fix))(*(name.encode() for name in mu_fix))
            handle = self._lib.MAGEMin_InitMuFix(
                database.encode(), 1 if verbose else 0, names, len(mu_fix)
            )
            if not handle:
                raise MAGEMinInitError(
                    f"MAGEMin_InitMuFix failed for database {database!r} with "
                    f"mu_fix={mu_fix!r}; every name must be one of the database's oxide_names"
                )
        else:
            handle = self._lib.MAGEMin_Init(database.encode(), 1 if verbose else 0)
            if not handle:
                raise MAGEMinInitError(f"MAGEMin_Init failed for database {database!r}")
        self._handle = handle
        self._closed = False
        # 1 = ignored: "sb" databases only support the legacy solver (0).
        if self._lib.MAGEMin_SetSolver(self._handle, solver) < 0:
            self.close()
            raise MAGEMinInitError(f"MAGEMin_SetSolver rejected solver={solver!r}")
        # Like SetSolver, 1 = no effect for this research group, which is not an error.
        if self._lib.MAGEMin_SetSSSolver(self._handle, optimizer) < 0:
            self.close()
            raise MAGEMinInitError(f"MAGEMin_SetSSSolver rejected optimizer={optimizer!r}")
        if self._lib.MAGEMin_SetFinalNewtonStep(self._handle, int(final_newton_step)) < 0:
            self.close()
            raise MAGEMinInitError(
                f"MAGEMin_SetFinalNewtonStep rejected final_newton_step={final_newton_step!r}"
            )
        scheme = _SEISMIC_SCHEMES[seismic_scheme]
        if self._lib.MAGEMin_SetSeismicScheme(self._handle, scheme, float(seismic_weight)) < 0:
            self.close()
            raise MAGEMinInitError(
                f"MAGEMin_SetSeismicScheme rejected seismic_scheme={seismic_scheme!r}, "
                f"seismic_weight={seismic_weight!r}"
            )
        self._database = database
        self._solver = solver
        self._optimizer = optimizer
        self._final_newton_step = bool(final_newton_step)
        self._mu_fix = mu_fix
        self._seismic_scheme = seismic_scheme
        self._seismic_weight = float(seismic_weight)
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
    def optimizer(self) -> int:
        """The optimizer value this instance was initialized with (see `__init__`)."""
        return self._optimizer

    @property
    def final_newton_step(self) -> bool:
        """Whether the final Newton polish is active (see `__init__`)."""
        return self._final_newton_step

    @property
    def mu_fix(self) -> tuple[str, ...]:
        """Oxides whose chemical potential is fixed (see `__init__`); empty if none."""
        return self._mu_fix

    @property
    def seismic_scheme(self) -> str:
        """The seismic averaging scheme, `"VRH"` or `"HS"` (see `__init__`)."""
        return self._seismic_scheme

    @property
    def seismic_weight(self) -> float:
        """The soft-to-stiff bound weight of `seismic_scheme` (see `__init__`)."""
        return self._seismic_weight

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
        """Pure-phase names, valid for `compute`'s `suppress_phases`.

        With `mu_fix`, ends with one fictive `"m<oxide>"` phase per fixed oxide; those cannot
        be suppressed.
        """
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
        use_phases: Sequence[str] | None = None,
        light: bool = False,
        name_solvus: bool = True,
        store_kkt: bool = False,
        mu_fix_values: Sequence[float] | None = None,
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
                this same instance. The buffer acts as an extra pure phase
                that exchanges the buffered component (O for redox buffers,
                e.g. H2O for "aH2O") with the system, so `bulk` must contain
                an excess of that component: when the buffer holds, its name
                appears in the result's `ph` with a near-zero fraction;
                otherwise the result is not buffered and a `UserWarning` is
                issued. "O2" is pure O2 at 1 bar (`buffer_value` is ignored).
            buffer_value: For a redox `buffer`, an additive log-unit offset
                (e.g. dQFM-style, can be negative, unclamped). For a
                fixed-activity `buffer`, the activity value itself, in
                `(0, 1)`. Required together with `buffer`.
            suppress_phases: Solution-phase or pure-phase names (see
                `solution_phase_names`/`pure_phase_names`) to exclude from
                this point's minimization. Mutually exclusive with
                `use_phases`.
            use_phases: Solution-phase names (see `solution_phase_names`) to
                keep active; every other solution phase is suppressed.
                Derived as `solution_phase_names` minus `use_phases` and
                passed through exactly like `suppress_phases` -- pure
                phases are never affected. Mutually exclusive with
                `suppress_phases`.
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
            store_kkt: If True, attach the final Newton (KKT) system at the
                converged state as the result's `final_newton_system` (a
                `FinalNewtonSystem`) -- left `None` if the final Newton polish
                was not accepted or is disabled (`final_newton_step=False`).
            mu_fix_values: Target chemical potentials of the oxides fixed by
                this instance's `mu_fix`, in the same order and units as the
                result's `gamma`. Required when `mu_fix` is set, and must be
                left `None` otherwise. Re-applied on every call, like
                `buffer`. Each fixed oxide's bulk content must be set
                generously in excess of what its target implies: when the
                target holds, its fictive `"m<oxide>"` phase appears in the
                result's `ph`; otherwise the oxide's chemical potential misses
                the target and a `UserWarning` is issued.

        Returns:
            The computed equilibrium result.

        Raises:
            MAGEMinClosedHandleError: If this instance has been closed.
            BulkCompositionError: If `bulk`'s length or oxide set doesn't
                match this database's oxides.
            MAGEMinComputeError: If `sys_in`/`buffer`/`buffer_value` is
                invalid, `mu_fix_values` doesn't match `mu_fix`, or the
                underlying computation fails (including an unrecognized
                `suppress_phases` name).
            ValueError: If both `suppress_phases` and `use_phases` are given.
        """
        if self._closed:
            raise MAGEMinClosedHandleError("MAGEMin instance is closed")

        if use_phases is not None:
            if suppress_phases is not None:
                raise ValueError("Cannot pass both suppress_phases and use_phases.")
            use_set = set(use_phases)
            suppress_phases = tuple(
                name for name in self._solution_phase_names if name not in use_set
            )

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

        # Like the buffer, the suppressed set persists on the C handle, so it is
        # re-applied (or cleared) on every call.
        encoded = [name.encode() for name in suppress_phases or ()]
        suppress_array = (ctypes.c_char_p * len(encoded))(*encoded) if encoded else None
        if self._lib.MAGEMin_SetSuppressedPhases(self._handle, suppress_array, len(encoded)) != 0:
            raise MAGEMinComputeError(
                f"unknown phase in suppress_phases={list(suppress_phases or ())!r}; expected "
                "names from solution_phase_names/pure_phase_names"
            )

        # Also persists on the C handle, so it is re-applied (or cleared) on every call.
        self._lib.MAGEMin_SetStoreKKT(self._handle, int(store_kkt))

        if self._mu_fix:
            if mu_fix_values is None or len(mu_fix_values) != len(self._mu_fix):
                raise MAGEMinComputeError(
                    f"mu_fix_values must give {len(self._mu_fix)} value(s), one per mu_fix "
                    f"oxide {self._mu_fix}, got {mu_fix_values!r}"
                )
            # Persists on the C handle like the buffer, so it is re-applied on every call.
            targets = (ctypes.c_double * len(self._mu_fix))(*map(float, mu_fix_values))
            if self._lib.MAGEMin_SetMuFix(self._handle, targets, len(self._mu_fix)) != 0:
                raise MAGEMinComputeError(f"MAGEMin_SetMuFix rejected {mu_fix_values!r}")
        elif mu_fix_values is not None:
            raise MAGEMinComputeError(
                "mu_fix_values given, but this MAGEMin instance was created without mu_fix"
            )

        bulk_array = (ctypes.c_double * self._n_oxides)(*values)
        result_ptr = self._lib.MAGEMin_ComputeEquilibrium(
            self._handle,
            float(P),
            float(T),
            bulk_array,
            sys_in.encode(),
        )
        if not result_ptr:
            raise MAGEMinComputeError(f"MAGEMin_ComputeEquilibrium failed for P={P}, T={T}")
        final_newton_system = None
        if store_kkt:
            kkt_ptr = self._lib.MAGEMin_GetFinalNewtonSystem(self._handle)
            if kkt_ptr:
                final_newton_system = FinalNewtonSystem._from_c(kkt_ptr.contents, self._n_oxides)
        mu_fix_phases = tuple(f"m{oxide}" for oxide in self._mu_fix)
        result = EquilibriumResult._from_c(
            result_ptr.contents,
            light=light,
            name_solvus=name_solvus,
            final_newton_system=final_newton_system,
            mu_fix_phases=mu_fix_phases,
        )
        # A buffer only constrains the system while its pure phase is part of the stable
        # assemblage, which needs an excess of the buffered component in the bulk. "O2" is
        # excluded: it is pure O2 at 1 bar, only stable at extreme oxidation.
        if buffer is not None and buffer != "O2" and buffer not in result.ph:
            warnings.warn(
                f"buffer {buffer!r} is not part of the stable assemblage at P={P}, T={T}, so "
                "the result is not buffered; increase the buffered component (O for redox "
                "buffers, e.g. H2O for 'aH2O') in the bulk composition",
                UserWarning,
                stacklevel=2,
            )
        # Same mechanism for a fixed chemical potential: its fictive phase must be stable.
        for oxide, phase in zip(self._mu_fix, mu_fix_phases, strict=True):
            if phase not in result.ph:
                warnings.warn(
                    f"fixed chemical potential of {oxide} was not reached at P={P}, T={T} "
                    f"({phase!r} is not part of the stable assemblage); increase {oxide} in "
                    "the bulk composition, or the target is beyond what any phase supports",
                    UserWarning,
                    stacklevel=2,
                )
        return result

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
        store_kkt: Passed through to `MAGEMin.compute`'s `store_kkt`.
        mu_fix_values: Passed through to `MAGEMin.compute`'s `mu_fix_values`;
            required when `multi_point_minimization` is given `mu_fix`.
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
    store_kkt: bool = False
    mu_fix_values: Sequence[float] | None = None


def multi_point_minimization(
    database: str,
    points: Sequence[Point],
    *,
    verbose: bool = False,
    solver: int = 2,
    optimizer: int = 0,
    final_newton_step: bool = True,
    mu_fix: Sequence[str] = (),
    seismic_scheme: Literal["VRH", "HS"] = "VRH",
    seismic_weight: float = 0.5,
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
        optimizer: Passed through to each worker's `MAGEMin` instance; see
            `MAGEMin.__init__`.
        final_newton_step: Passed through to each worker's `MAGEMin`
            instance; see `MAGEMin.__init__`.
        mu_fix: Passed through to each worker's `MAGEMin` instance; see
            `MAGEMin.__init__`. Each point then needs `mu_fix_values`.
        seismic_scheme: Passed through to each worker's `MAGEMin` instance;
            see `MAGEMin.__init__`.
        seismic_weight: Passed through to each worker's `MAGEMin` instance;
            see `MAGEMin.__init__`.
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
        with MAGEMin(
            database,
            verbose=verbose,
            solver=solver,
            optimizer=optimizer,
            final_newton_step=final_newton_step,
            mu_fix=mu_fix,
            seismic_scheme=seismic_scheme,
            seismic_weight=seismic_weight,
        ) as mg:
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
                        store_kkt=point.store_kkt,
                        mu_fix_values=point.mu_fix_values,
                    ),
                )
                for idx, point in chunk
            ]

    with ThreadPoolExecutor(max_workers=n_workers) as executor:
        futures = [executor.submit(_run_chunk, chunk) for chunk in chunks]
        pairs = [pair for future in futures for pair in future.result()]

    pairs.sort(key=lambda pair: pair[0])
    return [result for _, result in pairs]
