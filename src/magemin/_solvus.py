"""Solvus disambiguation for solution-phase names.

Ported from ``MAGEMin_C.jl/julia/name_solvus.jl``'s ``get_mineral_name``/``get_ss_from_mineral``.
Julia's ``compVariables`` is 1-indexed; the equivalent ``comp_variables`` sequences here are
0-indexed, so every index in this file is one less than the corresponding Julia source line.
"""

from collections.abc import Sequence

_IG_DATABASES = {"ig", "igad", "igd"}
_MP_MB_DATABASES = {"mp", "mpe", "mb", "ume", "mbe"}


def solvus_name(database: str, phase_name: str, comp_variables: Sequence[float]) -> str:
    """Disambiguate a solution-phase name using its converged compositional variables.

    Some solution-phase models split into mineralogically distinct end-members across a
    solvus (e.g. `"fsp"` into plagioclase `"pl"` / alkali feldspar `"afs"`, `"spl"` into
    spinel/chromite/magnetite/ulvospinel). This returns the mineralogically specific name for
    such phases, or `phase_name` unchanged if no disambiguation rule applies for `database`
    (including for databases with no rules at all, e.g. `"mtl"`, `"um"`, `"mpf"`, and the
    `sb`/`gh` families).

    Args:
        database: Database acronym (e.g. `"ig"`, `"mp"`, `"mb"`, `"all"`), as returned by
            `EquilibriumResult.database`.
        phase_name: Solution-phase model name, as it appears in `EquilibriumResult.ph`.
        comp_variables: The phase's compositional (order) variables, e.g.
            `SolutionPhase.comp_variables` or the corresponding raw C array.

    Returns:
        The disambiguated mineral name, or `phase_name` unchanged.
    """
    x = comp_variables
    name = phase_name

    if database in _IG_DATABASES:
        if phase_name == "spl":
            if x[2] - 0.5 > 0.0:
                name = "cm"
            elif x[3] - 0.5 > 0.0:
                name = "usp"
            elif x[1] - 0.5 > 0.0:
                name = "mgt"
            else:
                name = "spl"
        elif phase_name == "fsp":
            name = "afs" if x[1] - 0.5 > 0.0 else "pl"
        elif phase_name == "mu":
            name = "pat" if x[3] - 0.5 > 0.0 else "mu"
        elif phase_name == "amp":
            if x[2] - 0.5 > 0.0:
                name = "gl"
            elif -x[2] - x[3] + 0.2 > 0.0:
                name = "act"
            elif x[5] < 0.1:
                name = "cumm"
            elif -1 / 2 * x[3] + x[5] - x[6] - x[7] - x[1] + x[2] > 0.5:
                name = "tr"
            else:
                name = "amp"
        elif phase_name == "ilm":
            name = "hem" if -x[0] + 0.5 > 0.0 else "ilm"
        elif phase_name == "nph":
            name = "K-nph" if x[1] - 0.5 > 0.0 else "nph"
        elif phase_name == "cpx":
            if x[2] - 0.6 > 0.0:
                name = "pig"
            elif x[3] - 0.5 > 0.0:
                name = "Na-cpx"
            else:
                name = "cpx"

    elif database in _MP_MB_DATABASES:
        if phase_name == "sp":
            name = "sp" if x[1] - 0.5 > 0.0 else "smt"
        elif phase_name == "spl" and database == "ume":
            if x[2] - 0.5 > 0.0:
                name = "cm"
            elif x[1] - 0.5 > 0.0:
                name = "mgt"
            else:
                name = "spl"
        elif phase_name == "fsp":
            name = "afs" if x[1] - 0.5 > 0.0 else "pl"
        elif phase_name == "mu":
            name = "pat" if x[3] - 0.5 > 0.0 else "mu"
        elif phase_name == "amp":
            if x[2] - 0.5 > 0.0:
                name = "gl"
            elif -x[2] - x[3] + 0.2 > 0.0:
                name = "act"
            elif x[5] < 0.1:
                name = "cumm"
            elif -1 / 2 * x[3] + x[5] - x[6] - x[7] - x[1] + x[2] > 0.5:
                name = "tr"
            else:
                name = "amp"
        elif phase_name == "ilmm":
            name = "ilmm" if x[0] - 0.5 > 0.0 else "hemm"
        elif phase_name == "ilm":
            name = "hem" if 1.0 - x[0] > 0.5 else "ilm"
        elif phase_name == "dio":
            if 0.0 < x[1] <= 0.3:
                name = "dio"
            elif 0.3 < x[1] <= 0.7:
                name = "omph"
            else:
                name = "jd"
        elif phase_name == "occm":
            if x[1] > 0.5:
                name = "sid"
            elif x[2] > 0.5:
                name = "ank"
            elif x[0] > 0.25 and x[2] < 0.01:
                name = "mag"
            else:
                name = "cc"
        elif phase_name == "oamp":
            name = "anth" if x[1] < 0.3 else "ged"

    elif database == "all":
        if phase_name in ("fsp_H22", "fsp_H22op"):
            name = "afs" if x[1] - 0.5 > 0.0 else "pl"
        elif phase_name == "spl_T21":
            if x[2] - 0.5 > 0.0:
                name = "cm"
            elif x[1] - 0.5 > 0.0:
                name = "mgt"
            else:
                name = "spl"
        elif phase_name == "sp_W02":
            name = "sp" if x[1] - 0.5 > 0.0 else "smt"
        elif phase_name == "ilm_W24":
            name = "hem" if -x[0] + 0.5 > 0.0 else "ilm"
        elif phase_name == "ilm_W00":
            name = "hem" if 1.0 - x[0] > 0.5 else "ilm"
        elif phase_name == "ilmm_W14":
            name = "ilmm" if x[0] - 0.5 > 0.0 else "hemm"
        elif phase_name == "amp_G16":
            if x[2] - 0.5 > 0.0:
                name = "gl"
            elif -x[2] - x[3] + 0.2 > 0.0:
                name = "act"
            elif x[5] < 0.1:
                name = "cumm"
            elif -1 / 2 * x[3] + x[5] - x[6] - x[7] - x[1] + x[2] > 0.5:
                name = "tr"
            else:
                name = "amp"
        elif phase_name == "mu_W14":
            name = "pat" if x[3] - 0.5 > 0.0 else "mu"
        elif phase_name == "cpx_W24":
            if x[2] - 0.6 > 0.0:
                name = "pig"
            elif x[3] - 0.5 > 0.0:
                name = "Na-cpx"
            else:
                name = "cpx"
        elif phase_name == "nph_W24":
            name = "K-nph" if x[1] - 0.5 > 0.0 else "nph"
        elif phase_name == "dio_G16":
            if 0.0 < x[1] <= 0.3:
                name = "dio"
            elif 0.3 < x[1] <= 0.7:
                name = "omph"
            else:
                name = "jd"
        elif phase_name == "occm_F11":
            if x[1] > 0.5:
                name = "sid"
            elif x[2] > 0.5:
                name = "ank"
            elif x[0] > 0.25 and x[2] < 0.01:
                name = "mag"
            else:
                name = "cc"
        elif phase_name == "oamp_D07":
            name = "anth" if x[1] < 0.3 else "ged"
        elif "_" in phase_name:
            name = phase_name.split("_")[0]

    return name


def base_phase_name(database: str, mineral_name: str, mb_cpx: int = 0) -> str:
    """Return the raw solution-phase model name for a disambiguated mineral name.

    Inverse of `solvus_name`: converts a mineralogically specific name (e.g. `"pl"`) back to
    the solution-phase model name (e.g. `"fsp"`) that `MAGEMin.solution_phase_names` and
    `MAGEMin.compute`'s `suppress_phases` expect, since those match raw model names, not
    disambiguated mineral names.

    Args:
        database: Database acronym, as returned by `EquilibriumResult.database`.
        mineral_name: A disambiguated mineral name, e.g. as returned by `solvus_name`.
        mb_cpx: Metabasite clinopyroxene model selector: `omph`/`dio`/`jd` map to `"dio"`
            (default, `mb_cpx=0`) or `"aug"` (`mb_cpx` nonzero) for the `mp`/`mb`-family
            databases. This package doesn't expose MAGEMin's internal `gv.mbCpx` setting, so
            the round trip `base_phase_name(solvus_name(...))` is exact only for the default
            `mb_cpx=0` case; pass `mb_cpx=1` explicitly if you need the `"aug"` mapping.

    Returns:
        The raw solution-phase model name, or `mineral_name` unchanged if no rule applies.
    """
    name = mineral_name

    if database in _IG_DATABASES:
        if mineral_name in ("cm", "mgt", "usp", "spl"):
            name = "spl"
        elif mineral_name in ("pat", "mu"):
            name = "mu"
        elif mineral_name in ("afs", "pl"):
            name = "fsp"
        elif mineral_name in ("gl", "act", "amp", "cumm", "tr"):
            name = "amp"
        elif mineral_name in ("hem", "ilm"):
            name = "ilm"
        elif mineral_name in ("pig", "Na-cpx"):
            name = "cpx"
        elif mineral_name == "K-nph":
            name = "nph"

    elif database in _MP_MB_DATABASES:
        if mineral_name in ("smt", "sp"):
            name = "sp"
        elif mineral_name in ("cm", "mgt", "usp"):
            name = "spl"
        elif mineral_name in ("afs", "pl"):
            name = "fsp"
        elif mineral_name in ("pat", "mu"):
            name = "mu"
        elif mineral_name in ("gl", "act", "amp", "cumm", "tr"):
            name = "amp"
        elif mineral_name in ("hem", "ilm"):
            name = "ilm"
        elif mineral_name in ("hemm", "ilmm"):
            name = "ilmm"
        elif mineral_name in ("omph", "dio", "jd"):
            name = "dio" if mb_cpx == 0 else "aug"
        elif mineral_name in ("sid", "mag", "ank", "cc"):
            name = "occm"
        elif mineral_name in ("anth", "ged"):
            name = "oamp"

    elif database == "all":
        if mineral_name in ("afs", "pl"):
            name = "fsp_H22"
        elif mineral_name in ("cm", "mgt", "spl"):
            name = "spl_T21"
        elif mineral_name in ("sp", "smt"):
            name = "sp_W02"
        elif mineral_name in ("hem", "ilm"):
            name = "ilm_W24"
        elif mineral_name in ("hemm", "ilmm"):
            name = "ilmm_W14"
        elif mineral_name in ("gl", "act", "amp", "cumm", "tr"):
            name = "amp_G16"
        elif mineral_name in ("pat", "mu"):
            name = "mu_W14"
        elif mineral_name in ("pig", "Na-cpx", "cpx"):
            name = "cpx_W24"
        elif mineral_name in ("K-nph", "nph"):
            name = "nph_W24"
        elif mineral_name in ("omph", "dio", "jd"):
            name = "dio_G16"
        elif mineral_name in ("sid", "mag", "ank", "cc"):
            name = "occm_F11"
        elif mineral_name in ("anth", "ged"):
            name = "oamp_D07"

    elif "_" in mineral_name:
        name = mineral_name.split("_")[0]

    return name
