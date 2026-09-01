"""Low-level ctypes bindings to MAGEMin's minimal C API (``MAGEMin_api.h``).

This module is private: it only defines the raw struct layouts, function
prototypes, and library-discovery logic. Nothing here is meant to be imported
directly by users of the package -- see :mod:`magemin.core` for the public API.
"""

import ctypes
import ctypes.util
import os
from pathlib import Path

from magemin.errors import MAGEMinLibraryNotFoundError

_BUILD_INSTRUCTIONS = (
    "libMAGEMin could not be found. Build it with `./scripts/build_lib.sh` "
    "(requires the `liblapacke-dev` and `libnlopt-dev` system packages and a C "
    "compiler), or run `magemin-install` to download and build MAGEMin "
    "automatically, or point the MAGEMIN_LIB_PATH environment variable at an "
    "already-built libMAGEMin.so/.dylib/.dll."
)


class MAGEMin_Handle(ctypes.Structure):  # noqa: N801
    """Opaque handle to an initialized MAGEMin database.

    Deliberately left without ``_fields_``: Python code only ever passes this
    struct's pointer between the C functions below and never reads its
    internals directly.
    """


class StbSSPhase(ctypes.Structure):
    """Mirrors C ``stb_SS_phase`` (solution-phase equilibrium information)."""

    _fields_ = [
        ("nOx", ctypes.c_int),
        ("f", ctypes.c_double),
        ("G", ctypes.c_double),
        ("deltaG", ctypes.c_double),
        ("V", ctypes.c_double),
        ("alpha", ctypes.c_double),
        ("beta", ctypes.c_double),
        ("cp", ctypes.c_double),
        ("entropy", ctypes.c_double),
        ("enthalpy", ctypes.c_double),
        ("rho", ctypes.c_double),
        ("bulkMod", ctypes.c_double),
        ("shearMod", ctypes.c_double),
        ("Vp", ctypes.c_double),
        ("Vs", ctypes.c_double),
        ("pH", ctypes.c_double),
        ("chargeResidual", ctypes.c_double),
        ("sumMolality", ctypes.c_double),
        ("G_water", ctypes.c_double),
        ("n_xeos", ctypes.c_int),
        ("n_em", ctypes.c_int),
        ("n_sf", ctypes.c_int),
        ("Comp", ctypes.POINTER(ctypes.c_double)),
        ("compVariables", ctypes.POINTER(ctypes.c_double)),
        ("compVariablesNames", ctypes.POINTER(ctypes.c_char_p)),
        ("siteFractions", ctypes.POINTER(ctypes.c_double)),
        ("siteFractionsNames", ctypes.POINTER(ctypes.c_char_p)),
        ("emNames", ctypes.POINTER(ctypes.c_char_p)),
        ("molality", ctypes.POINTER(ctypes.c_double)),
        ("activity", ctypes.POINTER(ctypes.c_double)),
        ("emFrac", ctypes.POINTER(ctypes.c_double)),
        ("emFrac_wt", ctypes.POINTER(ctypes.c_double)),
        ("emChemPot", ctypes.POINTER(ctypes.c_double)),
        ("emComp", ctypes.POINTER(ctypes.POINTER(ctypes.c_double))),
        ("Comp_wt", ctypes.POINTER(ctypes.c_double)),
        ("emComp_wt", ctypes.POINTER(ctypes.POINTER(ctypes.c_double))),
        ("Comp_apfu", ctypes.POINTER(ctypes.c_double)),
        ("emComp_apfu", ctypes.POINTER(ctypes.POINTER(ctypes.c_double))),
    ]


class MstbSSPhase(ctypes.Structure):
    """Mirrors C ``mstb_SS_phase`` (metastable solution-phase information)."""

    _fields_ = [
        ("ph_name", ctypes.c_char_p),
        ("ph_type", ctypes.c_char_p),
        ("info", ctypes.c_char_p),
        ("ph_id", ctypes.c_int),
        ("em_id", ctypes.c_int),
        ("nOx", ctypes.c_int),
        ("n_xeos", ctypes.c_int),
        ("n_em", ctypes.c_int),
        ("G_Ppc", ctypes.c_double),
        ("DF_Ppc", ctypes.c_double),
        ("comp_Ppc", ctypes.POINTER(ctypes.c_double)),
        ("p_Ppc", ctypes.POINTER(ctypes.c_double)),
        ("mu_Ppc", ctypes.POINTER(ctypes.c_double)),
        ("xeos_Ppc", ctypes.POINTER(ctypes.c_double)),
    ]


class StbPPPhase(ctypes.Structure):
    """Mirrors C ``stb_PP_phase`` (pure-phase equilibrium information)."""

    _fields_ = [
        ("nOx", ctypes.c_int),
        ("f", ctypes.c_double),
        ("G", ctypes.c_double),
        ("deltaG", ctypes.c_double),
        ("V", ctypes.c_double),
        ("alpha", ctypes.c_double),
        ("beta", ctypes.c_double),
        ("cp", ctypes.c_double),
        ("entropy", ctypes.c_double),
        ("enthalpy", ctypes.c_double),
        ("rho", ctypes.c_double),
        ("bulkMod", ctypes.c_double),
        ("shearMod", ctypes.c_double),
        ("Vp", ctypes.c_double),
        ("Vs", ctypes.c_double),
        ("Comp", ctypes.POINTER(ctypes.c_double)),
        ("Comp_wt", ctypes.POINTER(ctypes.c_double)),
        ("Comp_apfu", ctypes.POINTER(ctypes.c_double)),
    ]


class StbSystem(ctypes.Structure):
    """Mirrors C ``stb_system`` (the full stable-equilibrium result).

    Note: ``frac_S``/``rho_S``/``entropy_S`` and their M/F and wt/vol
    counterparts are plain scalar ``double`` fields, not arrays -- only
    ``bulk_S``/``bulk_M``/``bulk_F`` (and their ``_wt`` variants) are pointers.
    """

    _fields_ = [
        ("MAGEMin_ver", ctypes.c_char_p),
        ("dataset", ctypes.c_char_p),
        ("database", ctypes.c_char_p),
        ("bulk_res_norm", ctypes.c_double),
        ("n_iterations", ctypes.c_int),
        ("status", ctypes.c_int),
        ("nOx", ctypes.c_int),
        ("oxides", ctypes.POINTER(ctypes.c_char_p)),
        ("elements", ctypes.POINTER(ctypes.c_char_p)),
        ("P", ctypes.c_double),
        ("T", ctypes.c_double),
        ("X", ctypes.c_double),
        ("bulk", ctypes.POINTER(ctypes.c_double)),
        ("bulk_wt", ctypes.POINTER(ctypes.c_double)),
        ("buffer", ctypes.c_char_p),
        ("buffer_n", ctypes.c_double),
        ("gamma", ctypes.POINTER(ctypes.c_double)),
        ("G", ctypes.c_double),
        ("M_sys", ctypes.c_double),
        ("rho", ctypes.c_double),
        ("fO2", ctypes.c_double),
        ("dQFM", ctypes.c_double),
        ("aH2O", ctypes.c_double),
        ("aSiO2", ctypes.c_double),
        ("aTiO2", ctypes.c_double),
        ("aAl2O3", ctypes.c_double),
        ("aMgO", ctypes.c_double),
        ("aFeO", ctypes.c_double),
        ("alpha", ctypes.c_double),
        ("beta", ctypes.c_double),
        ("cp", ctypes.c_double),
        ("s_cp", ctypes.c_double),
        ("cp_wt", ctypes.c_double),
        ("V", ctypes.c_double),
        ("V_cm3", ctypes.c_double),
        ("entropy", ctypes.c_double),
        ("enthalpy", ctypes.c_double),
        ("system_oxygen", ctypes.c_double),
        ("Fe3_Fe2_ratio", ctypes.c_double),
        ("bulkMod", ctypes.c_double),
        ("shearMod", ctypes.c_double),
        ("bulkModulus_M", ctypes.c_double),
        ("bulkModulus_S", ctypes.c_double),
        ("shearModulus_S", ctypes.c_double),
        ("Vp_S", ctypes.c_double),
        ("Vs_S", ctypes.c_double),
        ("Vp", ctypes.c_double),
        ("Vs", ctypes.c_double),
        ("bulk_S", ctypes.POINTER(ctypes.c_double)),
        ("frac_S", ctypes.c_double),
        ("rho_S", ctypes.c_double),
        ("bulk_M", ctypes.POINTER(ctypes.c_double)),
        ("frac_M", ctypes.c_double),
        ("rho_M", ctypes.c_double),
        ("bulk_F", ctypes.POINTER(ctypes.c_double)),
        ("frac_F", ctypes.c_double),
        ("rho_F", ctypes.c_double),
        ("entropy_S", ctypes.c_double),
        ("entropy_M", ctypes.c_double),
        ("entropy_F", ctypes.c_double),
        ("bulk_S_wt", ctypes.POINTER(ctypes.c_double)),
        ("frac_S_wt", ctypes.c_double),
        ("frac_S_vol", ctypes.c_double),
        ("bulk_M_wt", ctypes.POINTER(ctypes.c_double)),
        ("frac_M_wt", ctypes.c_double),
        ("frac_M_vol", ctypes.c_double),
        ("bulk_F_wt", ctypes.POINTER(ctypes.c_double)),
        ("frac_F_wt", ctypes.c_double),
        ("frac_F_vol", ctypes.c_double),
        ("n_ph", ctypes.c_int),
        ("n_PP", ctypes.c_int),
        ("n_SS", ctypes.c_int),
        ("n_mSS", ctypes.c_int),
        ("ph", ctypes.POINTER(ctypes.c_char_p)),
        ("sol_name", ctypes.POINTER(ctypes.c_char_p)),
        ("ph_frac", ctypes.POINTER(ctypes.c_double)),
        ("ph_frac_wt", ctypes.POINTER(ctypes.c_double)),
        ("ph_frac_1at", ctypes.POINTER(ctypes.c_double)),
        ("ph_frac_vol", ctypes.POINTER(ctypes.c_double)),
        ("ph_type", ctypes.POINTER(ctypes.c_int)),
        ("ph_id", ctypes.POINTER(ctypes.c_int)),
        ("ph_id_db", ctypes.POINTER(ctypes.c_int)),
        ("SS", ctypes.POINTER(StbSSPhase)),
        ("mSS", ctypes.POINTER(MstbSSPhase)),
        ("PP", ctypes.POINTER(StbPPPhase)),
    ]


def _candidate_paths() -> list[Path]:
    """List conventional locations to search for the compiled library."""
    repo_root = Path(__file__).resolve().parents[2]
    vendored = repo_root / "MAGEMin"
    return [vendored / "libMAGEMin.so", vendored / "libMAGEMin.dylib"]


def _cache_candidate_paths() -> list[Path]:
    """List library locations under the `magemin-install` cache directory, via its marker."""
    from magemin._download import default_cache_dir

    marker = default_cache_dir() / "current.txt"
    if not marker.exists():
        return []
    src_dir = Path(marker.read_text().strip())
    return [
        src_dir / "libMAGEMin.so",
        src_dir / "libMAGEMin.dylib",
        src_dir / "libMAGEMin.dll",
    ]


def _load(path: str | Path) -> ctypes.CDLL:
    lib = ctypes.CDLL(str(path))
    lib.MAGEMin_Init.argtypes = [ctypes.c_char_p, ctypes.c_int]
    lib.MAGEMin_Init.restype = ctypes.POINTER(MAGEMin_Handle)
    lib.MAGEMin_NOxides.argtypes = [ctypes.POINTER(MAGEMin_Handle)]
    lib.MAGEMin_NOxides.restype = ctypes.c_int
    lib.MAGEMin_OxideNames.argtypes = [ctypes.POINTER(MAGEMin_Handle)]
    lib.MAGEMin_OxideNames.restype = ctypes.POINTER(ctypes.c_char_p)
    lib.MAGEMin_ComputeEquilibrium.argtypes = [
        ctypes.POINTER(MAGEMin_Handle),
        ctypes.c_double,
        ctypes.c_double,
        ctypes.POINTER(ctypes.c_double),
        ctypes.c_char_p,
    ]
    lib.MAGEMin_ComputeEquilibrium.restype = ctypes.POINTER(StbSystem)
    lib.MAGEMin_Free.argtypes = [ctypes.POINTER(MAGEMin_Handle)]
    lib.MAGEMin_Free.restype = None

    # magemin_ext/ additions: buffer/activity fixing, phase suppression,
    # sb/gh database support, and phase-name discovery. See magemin_ext.h.
    lib.MAGEMin_InitEx.argtypes = [
        ctypes.c_char_p,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_int,
    ]
    lib.MAGEMin_InitEx.restype = ctypes.POINTER(MAGEMin_Handle)
    lib.MAGEMin_SetBuffer.argtypes = [
        ctypes.POINTER(MAGEMin_Handle),
        ctypes.c_char_p,
        ctypes.c_double,
    ]
    lib.MAGEMin_SetBuffer.restype = ctypes.c_int
    lib.MAGEMin_ComputeEquilibriumEx.argtypes = [
        ctypes.POINTER(MAGEMin_Handle),
        ctypes.c_double,
        ctypes.c_double,
        ctypes.POINTER(ctypes.c_double),
        ctypes.c_char_p,
        ctypes.POINTER(ctypes.c_char_p),
        ctypes.c_int,
    ]
    lib.MAGEMin_ComputeEquilibriumEx.restype = ctypes.POINTER(StbSystem)
    lib.MAGEMin_NSolutionPhases.argtypes = [ctypes.POINTER(MAGEMin_Handle)]
    lib.MAGEMin_NSolutionPhases.restype = ctypes.c_int
    lib.MAGEMin_SolutionPhaseNames.argtypes = [ctypes.POINTER(MAGEMin_Handle)]
    lib.MAGEMin_SolutionPhaseNames.restype = ctypes.POINTER(ctypes.c_char_p)
    lib.MAGEMin_NPurePhases.argtypes = [ctypes.POINTER(MAGEMin_Handle)]
    lib.MAGEMin_NPurePhases.restype = ctypes.c_int
    lib.MAGEMin_PurePhaseNames.argtypes = [ctypes.POINTER(MAGEMin_Handle)]
    lib.MAGEMin_PurePhaseNames.restype = ctypes.POINTER(ctypes.c_char_p)

    return lib


_library: ctypes.CDLL | None = None


def get_library() -> ctypes.CDLL:
    """Return the loaded ``libMAGEMin`` library, loading it on first use.

    Returns:
        The loaded library with the 5 ``MAGEMin_api.h`` functions and the 7
        ``magemin_ext.h`` functions wired up.

    Raises:
        MAGEMinLibraryNotFoundError: If the library cannot be located, or
            ``MAGEMIN_LIB_PATH`` is set but does not point at a loadable library.
    """
    global _library
    if _library is not None:
        return _library

    env_path = os.environ.get("MAGEMIN_LIB_PATH")
    if env_path:
        try:
            _library = _load(env_path)
        except OSError as exc:
            raise MAGEMinLibraryNotFoundError(
                f"MAGEMIN_LIB_PATH={env_path!r} could not be loaded: {exc}"
            ) from exc
        return _library

    for candidate in _candidate_paths() + _cache_candidate_paths():
        if candidate.exists():
            _library = _load(candidate)
            return _library

    found = ctypes.util.find_library("MAGEMin")
    if found:
        _library = _load(found)
        return _library

    raise MAGEMinLibraryNotFoundError(_BUILD_INSTRUCTIONS)
