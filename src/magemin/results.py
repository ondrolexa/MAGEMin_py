"""Python-side result objects copied out of MAGEMin's C output structs.

Every ``_from_c`` classmethod here is the only place a live C pointer
(``stb_system*`` and its nested arrays, owned by a :class:`~magemin.core.MAGEMin`
handle) is ever dereferenced -- everything is copied into plain Python
objects before the handle can be reused or freed.
"""

from __future__ import annotations

import ctypes
import dataclasses
import math
from dataclasses import dataclass, field

from magemin import _lib, _solvus


def _decode(b: bytes) -> str:
    """Decode C bytes into a string, tolerating non-UTF-8 garbage.

    Some solution-phase name/label fields (e.g. `compVariablesNames` for
    certain sb/gh research-group phases) are non-NULL but point at
    uninitialized memory rather than a real C string, for phases that don't
    use that concept -- an upstream data quirk, not a decoding edge case
    worth failing loudly over for what is purely descriptive metadata.
    """
    try:
        return b.decode()
    except UnicodeDecodeError:
        return ""


def _c_str(p: ctypes.c_char_p) -> str:
    """Decode a possibly-NULL ``char*`` into a string (empty if NULL)."""
    return _decode(p) if p else ""


def _c_str_array(p, n: int) -> tuple[str, ...]:
    """Decode a possibly-NULL ``char**`` of length ``n`` into a tuple of strings."""
    if not p or n <= 0:
        return ()
    return tuple(_decode(p[i]) if p[i] else "" for i in range(n))


def _c_array(p, n: int) -> tuple:
    """Copy a possibly-NULL C array pointer of length ``n`` into a tuple."""
    if not p or n <= 0:
        return ()
    return tuple(p[i] for i in range(n))


def _c_double_array(p, n: int) -> tuple[float, ...]:
    """Copy a possibly-NULL ``double*`` of length ``n`` into a tuple of floats."""
    return _c_array(p, n)


def _c_int_array(p, n: int) -> tuple[int, ...]:
    """Copy a possibly-NULL ``int*`` of length ``n`` into a tuple of ints."""
    return _c_array(p, n)


def _c_double_matrix(p, n_rows: int, n_cols: int) -> tuple[tuple[float, ...], ...]:
    """Copy a possibly-NULL ``double**`` of shape ``(n_rows, n_cols)``."""
    if not p or n_rows <= 0:
        return ()
    return tuple(_c_double_array(p[i], n_cols) for i in range(n_rows))


@dataclass(frozen=True, slots=True)
class SolutionPhase:
    """A stable solution phase, mirroring C ``stb_SS_phase``.

    ``ph``, ``charge_residual``, ``sum_molality``, ``g_water``, ``molality``,
    and ``activity`` are only meaningful for DEW aqueous-fluid phases and are
    ``NaN``/empty otherwise.

    Attributes:
        n_ox: Number of oxide/system components in this phase's composition
            arrays.
        f: Normalization factor of the phase's formula (MAGEMin's internal
            `factor`), **not** its proportion -- use the parent
            `EquilibriumResult.ph_frac`/`ph_frac_wt`/`ph_frac_vol` instead.
        g: Gibbs energy of the phase.
        delta_g: Gibbs energy relative to the stable assemblage (driving
            force / undersaturation).
        v: Molar volume.
        alpha: Thermal expansivity.
        beta: Compressibility.
        cp: Heat capacity.
        entropy: Entropy.
        enthalpy: Enthalpy.
        rho: Density, in kg/m3.
        bulk_mod: Bulk modulus.
        shear_mod: Shear modulus.
        vp: P-wave seismic velocity.
        vs: S-wave seismic velocity.
        ph: -log10(activity of H+) ("pH"). DEW-only; ``NaN`` otherwise.
        charge_residual: ``abs(sum(z_i * m_i))`` at the converged aqueous
            speciation. DEW-only; ``NaN`` otherwise.
        sum_molality: Sum of solute molalities, in mol/kg H2O. DEW-only;
            ``NaN`` otherwise.
        g_water: Standard-state Gibbs energy of the solvent (H2O), in
            kJ/mol. DEW-only; ``NaN`` otherwise.
        n_xeos: Number of independent compositional (order) variables for
            this solution model.
        n_em: Number of endmembers.
        n_sf: Number of site fractions.
        comp: Oxide composition of the phase as mol fractions (summing to 1),
            length `n_ox`, in the parent `EquilibriumResult.oxides` order.
        comp_wt: Same as `comp`, as wt fractions (summing to 1; x100 for wt%).
        comp_apfu: Same as `comp`, in atoms per formula unit.
        comp_variables: Values of the compositional (order) variables,
            length `n_xeos`.
        comp_variable_names: Names of `comp_variables`, length `n_xeos`.
        site_fractions: Site-fraction values, length `n_sf`.
        site_fraction_names: Names of `site_fractions`, length `n_sf`.
        em_names: Endmember names, length `n_em`.
        em_frac: Endmember mol fractions, length `n_em`.
        em_frac_wt: Endmember wt fractions, length `n_em`.
        em_chem_pot: Endmember chemical potentials, length `n_em`.
        em_comp: Oxide composition of each endmember (mol fractions), shape
            `(n_em, n_ox)`.
        em_comp_wt: Same as `em_comp`, as wt fractions.
        em_comp_apfu: Same as `em_comp`, in atoms per formula unit.
        molality: Per-endmember molality, in mol/kg H2O, length `n_em`.
            DEW-only; empty otherwise.
        activity: Per-endmember activity (the solvent's slot holds water's
            activity coefficient), length `n_em`. DEW-only; empty otherwise.
    """

    n_ox: int
    f: float
    g: float
    delta_g: float
    v: float
    alpha: float
    beta: float
    cp: float
    entropy: float
    enthalpy: float
    rho: float
    bulk_mod: float
    shear_mod: float
    vp: float
    vs: float
    ph: float
    charge_residual: float
    sum_molality: float
    g_water: float
    n_xeos: int
    n_em: int
    n_sf: int
    comp: tuple[float, ...]
    comp_wt: tuple[float, ...]
    comp_apfu: tuple[float, ...]
    comp_variables: tuple[float, ...]
    comp_variable_names: tuple[str, ...]
    site_fractions: tuple[float, ...]
    site_fraction_names: tuple[str, ...]
    em_names: tuple[str, ...]
    em_frac: tuple[float, ...]
    em_frac_wt: tuple[float, ...]
    em_chem_pot: tuple[float, ...]
    em_comp: tuple[tuple[float, ...], ...]
    em_comp_wt: tuple[tuple[float, ...], ...]
    em_comp_apfu: tuple[tuple[float, ...], ...]
    molality: tuple[float, ...]
    activity: tuple[float, ...]

    @classmethod
    def _from_c(cls, c: _lib.StbSSPhase) -> SolutionPhase:
        """Deep-copy a ``stb_SS_phase`` struct into a :class:`SolutionPhase`."""
        n_ox, n_em, n_xeos, n_sf = c.nOx, c.n_em, c.n_xeos, c.n_sf
        return cls(
            n_ox=n_ox,
            f=c.f,
            g=c.G,
            delta_g=c.deltaG,
            v=c.V,
            alpha=c.alpha,
            beta=c.beta,
            cp=c.cp,
            entropy=c.entropy,
            enthalpy=c.enthalpy,
            rho=c.rho,
            bulk_mod=c.bulkMod,
            shear_mod=c.shearMod,
            vp=c.Vp,
            vs=c.Vs,
            ph=c.pH,
            charge_residual=c.chargeResidual,
            sum_molality=c.sumMolality,
            g_water=c.G_water,
            n_xeos=n_xeos,
            n_em=n_em,
            n_sf=n_sf,
            comp=_c_double_array(c.Comp, n_ox),
            comp_wt=_c_double_array(c.Comp_wt, n_ox),
            comp_apfu=_c_double_array(c.Comp_apfu, n_ox),
            comp_variables=_c_double_array(c.compVariables, n_xeos),
            comp_variable_names=_c_str_array(c.compVariablesNames, n_xeos),
            site_fractions=_c_double_array(c.siteFractions, n_sf),
            site_fraction_names=_c_str_array(c.siteFractionsNames, n_sf),
            em_names=_c_str_array(c.emNames, n_em),
            em_frac=_c_double_array(c.emFrac, n_em),
            em_frac_wt=_c_double_array(c.emFrac_wt, n_em),
            em_chem_pot=_c_double_array(c.emChemPot, n_em),
            em_comp=_c_double_matrix(c.emComp, n_em, n_ox),
            em_comp_wt=_c_double_matrix(c.emComp_wt, n_em, n_ox),
            em_comp_apfu=_c_double_matrix(c.emComp_apfu, n_em, n_ox),
            molality=_c_double_array(c.molality, n_em),
            activity=_c_double_array(c.activity, n_em),
        )


@dataclass(frozen=True, slots=True)
class MetastableSolutionPhase:
    """A metastable pseudocompound, mirroring C ``mstb_SS_phase``.

    Attributes:
        ph_name: Phase (solution model) name.
        ph_type: Phase type string.
        info: Free-form description string.
        ph_id: Index of the parent solution-phase model.
        em_id: Endmember/pseudocompound index within that model.
        n_ox: Number of oxide components.
        n_xeos: Number of compositional (order) variables.
        n_em: Number of endmembers.
        g_ppc: Gibbs energy of the pseudocompound.
        df_ppc: Driving force (Gibbs energy distance from the stable
            equilibrium hyperplane).
        comp_ppc: Oxide composition of the pseudocompound (mol), length
            `n_ox`.
        p_ppc: Endmember proportions, length `n_em`.
        mu_ppc: Endmember chemical potentials, length `n_em`.
        xeos_ppc: Compositional (order) variable values, length `n_xeos`.
    """

    ph_name: str
    ph_type: str
    info: str
    ph_id: int
    em_id: int
    n_ox: int
    n_xeos: int
    n_em: int
    g_ppc: float
    df_ppc: float
    comp_ppc: tuple[float, ...]
    p_ppc: tuple[float, ...]
    mu_ppc: tuple[float, ...]
    xeos_ppc: tuple[float, ...]

    @classmethod
    def _from_c(cls, c: _lib.MstbSSPhase) -> MetastableSolutionPhase:
        """Deep-copy an ``mstb_SS_phase`` struct into a :class:`MetastableSolutionPhase`."""
        n_ox, n_em, n_xeos = c.nOx, c.n_em, c.n_xeos
        return cls(
            ph_name=_c_str(c.ph_name),
            ph_type=_c_str(c.ph_type),
            info=_c_str(c.info),
            ph_id=c.ph_id,
            em_id=c.em_id,
            n_ox=n_ox,
            n_xeos=n_xeos,
            n_em=n_em,
            g_ppc=c.G_Ppc,
            df_ppc=c.DF_Ppc,
            comp_ppc=_c_double_array(c.comp_Ppc, n_ox),
            p_ppc=_c_double_array(c.p_Ppc, n_em),
            mu_ppc=_c_double_array(c.mu_Ppc, n_em),
            xeos_ppc=_c_double_array(c.xeos_Ppc, n_xeos),
        )


@dataclass(frozen=True, slots=True)
class PurePhase:
    """A stable pure phase, mirroring C ``stb_PP_phase``.

    For the fictive `"m<oxide>"` phase of a fixed chemical potential (`MAGEMin(mu_fix=...)`),
    `comp`/`comp_wt`/`comp_apfu` are that oxide alone (1.0 at its index) and every other float
    field is NaN -- MAGEMin reports no physical properties for it.

    Attributes:
        n_ox: Number of oxide components.
        f: Normalization factor of the phase's formula (MAGEMin's internal
            `factor`), **not** its proportion -- use the parent
            `EquilibriumResult.ph_frac`/`ph_frac_wt`/`ph_frac_vol` instead.
        g: Gibbs energy of the phase.
        delta_g: Gibbs energy relative to the stable assemblage.
        v: Molar volume.
        alpha: Thermal expansivity.
        beta: Compressibility.
        cp: Heat capacity.
        entropy: Entropy.
        enthalpy: Enthalpy.
        rho: Density, in kg/m3.
        bulk_mod: Bulk modulus.
        shear_mod: Shear modulus.
        vp: P-wave seismic velocity.
        vs: S-wave seismic velocity.
        comp: Oxide composition as mol fractions (summing to 1), length `n_ox`.
        comp_wt: Same as `comp`, as wt fractions (summing to 1; x100 for wt%).
        comp_apfu: Same as `comp`, in atoms per formula unit.
    """

    n_ox: int
    f: float
    g: float
    delta_g: float
    v: float
    alpha: float
    beta: float
    cp: float
    entropy: float
    enthalpy: float
    rho: float
    bulk_mod: float
    shear_mod: float
    vp: float
    vs: float
    comp: tuple[float, ...]
    comp_wt: tuple[float, ...]
    comp_apfu: tuple[float, ...]

    @classmethod
    def _from_c(cls, c: _lib.StbPPPhase) -> PurePhase:
        """Deep-copy a ``stb_PP_phase`` struct into a :class:`PurePhase`."""
        n_ox = c.nOx
        return cls(
            n_ox=n_ox,
            f=c.f,
            g=c.G,
            delta_g=c.deltaG,
            v=c.V,
            alpha=c.alpha,
            beta=c.beta,
            cp=c.cp,
            entropy=c.entropy,
            enthalpy=c.enthalpy,
            rho=c.rho,
            bulk_mod=c.bulkMod,
            shear_mod=c.shearMod,
            vp=c.Vp,
            vs=c.Vs,
            comp=_c_double_array(c.Comp, n_ox),
            comp_wt=_c_double_array(c.Comp_wt, n_ox),
            comp_apfu=_c_double_array(c.Comp_apfu, n_ox),
        )


@dataclass(frozen=True, slots=True)
class FinalNewtonSystem:
    """The final Newton (KKT) system at the converged equilibrium.

    Only produced by `MAGEMin.compute(..., store_kkt=True)`, and only when the
    final Newton polish (`MAGEMin(final_newton_step=True)`, the default) was
    accepted -- see `EquilibriumResult.final_newton_system`.

    The system has `nz = m + n_y + n_cc + n_ph + n_pp` unknowns, ordered as the
    chemical potentials of the `m` oxides present in the bulk (`ox_id`), the
    `n_y` reduced (nullspace) compositional coordinates of the stable solution
    phases (phase `q` owns `off_y[q]:off_y[q + 1]`), the `n_cc` Lagrange
    multipliers of compositional variables held at a bound (`off_c`), the
    `n_ph` solution-phase amounts, and the `n_pp` pure-phase amounts. Its
    `nz` equations (`residual`/`jacobian` rows) are ordered as the `n_y`
    stationarity conditions, the `n_cc` active bound constraints, the `n_ph`
    solution-phase and `n_pp` pure-phase driving forces (`n = 0` instead for a
    `drop`ped phase), and the `m` mass-balance conditions.

    Attributes:
        nz: Size of the system (number of unknowns and of equations).
        m: Number of oxides present in the bulk composition.
        n_y: Number of reduced compositional coordinates, over all stable
            solution phases.
        n_cc: Number of compositional variables held at a bound.
        n_ph: Number of stable solution phases.
        n_pp: Number of stable pure phases.
        ox_id: Index (into `EquilibriumResult.oxides`) of each of the `m`
            oxides, length `m`.
        ss_id: Database index (into `MAGEMin.solution_phase_names`) of each
            stable solution phase, length `n_ph`.
        cp_id: Internal considered-phase index of each stable solution phase,
            length `n_ph`.
        pp_id: Database index (into `MAGEMin.pure_phase_names`) of each stable
            pure phase, length `n_pp`.
        off_y: Per-solution-phase offsets into the reduced coordinates,
            length `n_ph + 1`.
        off_s: Per-solution-phase offsets into `s`, length `n_ph + 1`.
        off_n: Per-solution-phase offsets into `nb`, length `n_ph + 1`.
        off_c: Per-solution-phase offsets into the bound constraints
            (`c_x`/`c_b`/`mu`), length `n_ph + 1`.
        c_x: Index of the compositional variable held at a bound, per bound
            constraint, length `n_cc`.
        c_b: Bound value of that compositional variable, length `n_cc`.
        mu: Lagrange multiplier of each bound constraint, length `n_cc`.
        drop: Per phase (solution phases, then pure phases), `1` if its
            amount is held at zero, length `n_ph + n_pp`.
        n: Phase amounts (solution phases, then pure phases), length
            `n_ph + n_pp`.
        s: Converged compositional state of each solution phase,
            concatenated (see `off_s`).
        nb: Nullspace basis of each solution phase, concatenated and
            row-major per phase (see `off_n`).
        gamma: Chemical potentials of all oxide components, length
            `EquilibriumResult.n_ox` (equal to `EquilibriumResult.gamma`).
        residual: Residual of each equation, length `nz`.
        jacobian: Jacobian of the system, `nz` rows (equations) of `nz`
            columns (unknowns).
        g: Gibbs energy of the system at the converged state.
    """

    nz: int
    m: int
    n_y: int
    n_cc: int
    n_ph: int
    n_pp: int
    ox_id: tuple[int, ...]
    ss_id: tuple[int, ...]
    cp_id: tuple[int, ...]
    pp_id: tuple[int, ...]
    off_y: tuple[int, ...]
    off_s: tuple[int, ...]
    off_n: tuple[int, ...]
    off_c: tuple[int, ...]
    c_x: tuple[int, ...]
    c_b: tuple[float, ...]
    mu: tuple[float, ...]
    drop: tuple[int, ...]
    n: tuple[float, ...]
    s: tuple[float, ...]
    nb: tuple[float, ...]
    gamma: tuple[float, ...]
    residual: tuple[float, ...]
    jacobian: tuple[tuple[float, ...], ...]
    g: float

    @classmethod
    def _from_c(cls, c: _lib.FnKKT, n_ox: int) -> FinalNewtonSystem:
        """Deep-copy an ``fn_kkt`` struct; `n_ox` is the length of its ``gam`` array."""
        nz, n_ph, n_pp = c.nz, c.n_ph, c.n_pp
        flat = _c_double_array(c.J, nz * nz)  # column-major: J[col * nz + row]
        return cls(
            nz=nz,
            m=c.m,
            n_y=c.n_y,
            n_cc=c.n_cc,
            n_ph=n_ph,
            n_pp=n_pp,
            ox_id=_c_int_array(c.ox_id, c.m),
            ss_id=_c_int_array(c.ss_id, n_ph),
            cp_id=_c_int_array(c.cp_id, n_ph),
            pp_id=_c_int_array(c.pp_id, n_pp),
            off_y=_c_int_array(c.off_y, n_ph + 1),
            off_s=_c_int_array(c.off_s, n_ph + 1),
            off_n=_c_int_array(c.off_N, n_ph + 1),
            off_c=_c_int_array(c.off_c, n_ph + 1),
            c_x=_c_int_array(c.c_x, c.n_cc),
            c_b=_c_double_array(c.c_b, c.n_cc),
            mu=_c_double_array(c.mu, c.n_cc),
            drop=_c_int_array(c.drop, n_ph + n_pp),
            n=_c_double_array(c.n, n_ph + n_pp),
            s=_c_double_array(c.s, c.n_s),
            nb=_c_double_array(c.Nb, c.n_Nb),
            gamma=_c_double_array(c.gam, n_ox),
            residual=_c_double_array(c.R, nz),
            jacobian=tuple(flat[row::nz] for row in range(nz)) if flat else (),
            g=c.G,
        )


_PURE_PHASE_PROPERTIES = (
    "f",
    "g",
    "delta_g",
    "v",
    "alpha",
    "beta",
    "cp",
    "entropy",
    "enthalpy",
    "rho",
    "bulk_mod",
    "shear_mod",
    "vp",
    "vs",
)


def _clean_mu_fix_phases(
    pure_phases: tuple[PurePhase, ...],
    ph: tuple[str, ...],
    ph_type: tuple[int, ...],
    ph_id: tuple[int, ...],
    oxides: tuple[str, ...],
    mu_fix_phases: tuple[str, ...],
) -> tuple[PurePhase, ...]:
    """Replace the uninitialized fields of fictive `"m<oxide>"` mu-fix phases.

    MAGEMin skips its pure-phase post-processing for these phases, so everything it reports for
    them (composition, Gibbs energy, volume, elastic properties, ...) is uninitialized memory.
    Each fictive phase is exactly one oxide component, so its composition is set to that oxide
    alone; it has no physical properties, so every other float field is set to NaN.
    """
    cleaned = list(pure_phases)
    for name, kind, idx in zip(ph, ph_type, ph_id, strict=True):
        if kind != 0 or name not in mu_fix_phases:
            continue
        one_hot = tuple(1.0 if oxide == name[1:] else 0.0 for oxide in oxides)
        cleaned[idx] = dataclasses.replace(
            cleaned[idx],
            comp=one_hot,
            comp_wt=one_hot,
            comp_apfu=one_hot,
            **dict.fromkeys(_PURE_PHASE_PROPERTIES, math.nan),
        )
    return tuple(cleaned)


@dataclass(frozen=True, slots=True)
class EquilibriumResult:
    """The stable equilibrium phase assemblage at one (P, T, bulk) point.

    Mirrors C ``stb_system`` field-for-field (in snake_case), plus the nested
    per-phase arrays copied into :class:`SolutionPhase`/:class:`MetastableSolutionPhase`/
    :class:`PurePhase` tuples.

    Note:
        ``p`` is in kbar, matching the pressure passed to ``compute()``. ``t``
        is in **Kelvin**, not Celsius: ``compute()`` takes a Celsius
        temperature, but MAGEMin converts it internally (``+ 273.15``) and
        reports it back in Kelvin here.

        When ``compute()``'s ``light=True`` was used, ``solution_phases``,
        ``metastable_phases``, and ``pure_phases`` are empty tuples -- every
        other field, including the phase-summary arrays (``ph``, ``ph_frac``,
        ``ph_frac_wt``, ...) and phase counts (``n_ss``, ``n_pp``, ``n_mss``),
        is still populated normally. Light mode skips deep-copying each
        phase's endmember/composition arrays, which is the expensive part of
        building a result.

    Attributes:
        magemin_version: MAGEMin library version string.
        dataset: Thermodynamic dataset/calibration identifier.
        database: Database acronym used for this computation (e.g. `"ig"`).
        bulk_res_norm: Mass-balance residual norm at convergence.
        n_iterations: Number of minimization (PGE/LP) iterations used.
        status: Convergence status code. `0`: converged. `1`-`4`: stopped at
            the iteration limit with an increasingly large residual (chemical
            potential norm < 1e-2, < 0.1, < 1, < 10) -- usable with caution. `-1`:
            failed (mass-balance residual above 1e-3, or a non-negative chemical
            potential), typically from an infeasible bulk composition (e.g. more
            `O` than its Fe can take up as Fe2O3 with no buffer); every phase
            field (`ph`, fractions, compositions) is then meaningless.
        n_ox: Number of oxide/system components.
        oxides: Oxide component names, in `bulk`/`bulk_wt` order.
        elements: Element names corresponding to `oxides`.
        p: Pressure, in kbar (matches the `P` passed to `compute()`).
        t: Temperature, in **Kelvin** (`compute()` takes Celsius; MAGEMin
            reports back in Kelvin here, i.e. `t == T_celsius + 273.15`).
        x: Reserved/generic composition variable, not used by this minimal
            API.
        bulk: Input bulk composition, normalized to mol fractions (summing to
            1), length `n_ox`.
        bulk_wt: Same as `bulk`, as wt fractions.
        buffer: Active oxygen-buffer/fixed-activity constraint name (as passed
            to `compute()`'s `buffer` argument), or `"none"` if unset.
        buffer_n: Buffer offset / fixed-activity value associated with
            `buffer`.
        gamma: Chemical potentials of the oxide components, length `n_ox`.
        g: System Gibbs energy.
        m_sys: Total system mass.
        rho: System (bulk) density, in kg/m3.
        f_o2: Oxygen fugacity.
        d_qfm: Delta-QFM: log10 units relative to the quartz-fayalite-magnetite
            buffer.
        a_h2o: Activity of H2O.
        a_sio2: Activity of SiO2.
        a_tio2: Activity of TiO2.
        a_al2o3: Activity of Al2O3.
        a_mgo: Activity of MgO.
        a_feo: Activity of FeO.
        alpha: System thermal expansivity.
        beta: System compressibility.
        cp: System heat capacity.
        s_cp: Specific heat capacity.
        cp_wt: Heat capacity per unit mass.
        v: System molar volume.
        v_cm3: System volume, in cm3.
        entropy: System entropy.
        enthalpy: System enthalpy.
        system_oxygen: Bulk oxygen content of the system.
        fe3_fe2_ratio: Fe3+/Fe2+ ratio of the system.
        bulk_mod: Whole-system bulk modulus.
        shear_mod: Whole-system shear modulus.
        bulk_modulus_m: Melt-only bulk modulus.
        bulk_modulus_s: Solid-only bulk modulus.
        shear_modulus_s: Solid-only shear modulus.
        vp_s: Solid-only P-wave seismic velocity.
        vs_s: Solid-only S-wave seismic velocity.
        vp: Whole-system P-wave seismic velocity.
        vs: Whole-system S-wave seismic velocity.
        bulk_s: Solid sub-system composition as mol fractions, length `n_ox`
            (`oxides` order -- usable directly as a new `bulk` with `sys_in="mol"`).
        frac_s: Solid sub-system fraction, mol basis.
        rho_s: Solid sub-system density.
        bulk_m: Melt sub-system composition as mol fractions, length `n_ox`
            (`oxides` order -- usable directly as a new `bulk` with `sys_in="mol"`).
        frac_m: Melt sub-system fraction, mol basis.
        rho_m: Melt sub-system density.
        bulk_f: Fluid sub-system composition as mol fractions, length `n_ox`
            (`oxides` order -- usable directly as a new `bulk` with `sys_in="mol"`).
        frac_f: Fluid sub-system fraction, mol basis.
        rho_f: Fluid sub-system density.
        entropy_s: Solid sub-system entropy.
        entropy_m: Melt sub-system entropy.
        entropy_f: Fluid sub-system entropy.
        bulk_s_wt: Same as `bulk_s`, as wt fractions.
        frac_s_wt: Solid sub-system mass fraction, wt basis.
        frac_s_vol: Solid sub-system volume fraction.
        bulk_m_wt: Same as `bulk_m`, as wt fractions.
        frac_m_wt: Melt sub-system mass fraction, wt basis.
        frac_m_vol: Melt sub-system volume fraction.
        bulk_f_wt: Same as `bulk_f`, as wt fractions.
        frac_f_wt: Fluid sub-system mass fraction, wt basis.
        frac_f_vol: Fluid sub-system volume fraction.
        n_ph: Total number of stable phases.
        n_pp: Number of stable pure phases.
        n_ss: Number of stable solution phases.
        n_mss: Number of metastable solution (pseudocompound) entries.
        ph: Stable phase names, length `n_ph`. With an active `buffer`, includes
            the buffer itself (e.g. `"qfm"`, `"aH2O"`) as a near-zero-fraction
            pure phase. A name can legitimately repeat: two coexisting
            compositions of one solution model (immiscibility) that solvus naming
            does not tell apart, e.g. ordered and disordered `"ilm"` in `"mp"`. In
            a failed result (`status == -1`), repeats are artifacts. With
            `MAGEMin(mu_fix=...)`, includes the fictive `"m<oxide>"` phase of
            each fixed oxide whose target holds, with zero fraction.
        sol_name: Underlying solution-model name for each phase in `ph`,
            length `n_ph`.
        ph_frac: Phase fractions (summing to 1), mol basis, length `n_ph`.
        ph_frac_wt: Phase fractions, wt basis, length `n_ph`.
        ph_frac_1at: Phase fractions, normalized per atom, length `n_ph`.
        ph_frac_vol: Phase fractions, volume basis, length `n_ph`.
        ph_type: Per-phase type, length `n_ph`: `1` = solution phase (detail at
            `solution_phases[ph_id[i]]`), `0` = pure phase (detail at
            `pure_phases[ph_id[i]]`).
        ph_id: Index of each phase into `solution_phases`/`pure_phases`,
            length `n_ph`.
        ph_id_db: Index of each phase into the underlying thermodynamic
            database, length `n_ph`.
        solution_phases: Detailed per-solution-phase results, length `n_ss`.
            Empty when `compute()`'s `light=True` was used.
        metastable_phases: Detailed metastable-pseudocompound results,
            length `n_mss`. Empty when `compute()`'s `light=True` was used.
        pure_phases: Detailed per-pure-phase results, length `n_pp`. Empty
            when `compute()`'s `light=True` was used.
        final_newton_system: The final Newton (KKT) system at the converged
            state, only when `compute()`'s `store_kkt=True` was used and the
            final Newton polish was accepted; `None` otherwise.
    """

    magemin_version: str
    dataset: str
    database: str
    bulk_res_norm: float
    n_iterations: int
    status: int
    n_ox: int
    oxides: tuple[str, ...]
    elements: tuple[str, ...]
    p: float
    t: float
    x: float
    bulk: tuple[float, ...]
    bulk_wt: tuple[float, ...]
    buffer: str
    buffer_n: float
    gamma: tuple[float, ...]
    g: float
    m_sys: float
    rho: float
    f_o2: float
    d_qfm: float
    a_h2o: float
    a_sio2: float
    a_tio2: float
    a_al2o3: float
    a_mgo: float
    a_feo: float
    alpha: float
    beta: float
    cp: float
    s_cp: float
    cp_wt: float
    v: float
    v_cm3: float
    entropy: float
    enthalpy: float
    system_oxygen: float
    fe3_fe2_ratio: float
    bulk_mod: float
    shear_mod: float
    bulk_modulus_m: float
    bulk_modulus_s: float
    shear_modulus_s: float
    vp_s: float
    vs_s: float
    vp: float
    vs: float
    bulk_s: tuple[float, ...]
    frac_s: float
    rho_s: float
    bulk_m: tuple[float, ...]
    frac_m: float
    rho_m: float
    bulk_f: tuple[float, ...]
    frac_f: float
    rho_f: float
    entropy_s: float
    entropy_m: float
    entropy_f: float
    bulk_s_wt: tuple[float, ...]
    frac_s_wt: float
    frac_s_vol: float
    bulk_m_wt: tuple[float, ...]
    frac_m_wt: float
    frac_m_vol: float
    bulk_f_wt: tuple[float, ...]
    frac_f_wt: float
    frac_f_vol: float
    n_ph: int
    n_pp: int
    n_ss: int
    n_mss: int
    ph: tuple[str, ...]
    sol_name: tuple[str, ...]
    ph_frac: tuple[float, ...]
    ph_frac_wt: tuple[float, ...]
    ph_frac_1at: tuple[float, ...]
    ph_frac_vol: tuple[float, ...]
    ph_type: tuple[int, ...]
    ph_id: tuple[int, ...]
    ph_id_db: tuple[int, ...]
    solution_phases: tuple[SolutionPhase, ...] = field(default_factory=tuple)
    metastable_phases: tuple[MetastableSolutionPhase, ...] = field(default_factory=tuple)
    pure_phases: tuple[PurePhase, ...] = field(default_factory=tuple)
    final_newton_system: FinalNewtonSystem | None = None

    @classmethod
    def _from_c(
        cls,
        c: _lib.StbSystem,
        *,
        light: bool = False,
        name_solvus: bool = True,
        final_newton_system: FinalNewtonSystem | None = None,
        mu_fix_phases: tuple[str, ...] = (),
    ) -> EquilibriumResult:
        """Deep-copy a ``stb_system`` struct (and its nested phase arrays).

        Args:
            c: The C struct to copy from.
            light: If True, skip copying `solution_phases`/`metastable_phases`/
                `pure_phases` (leaving them as empty tuples) -- this nested
                per-phase-array copying is the expensive part of this method.
                All other fields, including the phase-summary arrays (`ph`,
                `ph_frac`, `ph_frac_wt`, ...) and phase counts (`n_ss`, `n_pp`,
                `n_mss`), are still populated normally.
            name_solvus: If True, disambiguate solution-phase entries in `ph`
                (e.g. `"fsp"` into `"pl"`/`"afs"`) via `magemin.solvus_name`,
                using each phase's compositional variables read directly from
                `c` -- independent of `light`, since it never depends on
                `solution_phases` being populated.
            final_newton_system: Already-copied final Newton system to attach,
                if any.
            mu_fix_phases: Names of the fictive `"m<oxide>"` pure phases of a
                `MAGEMin(mu_fix=...)` handle. MAGEMin leaves their reported
                compositions uninitialized, so they are replaced here.
        """
        n_ox, n_ph = c.nOx, c.n_ph
        n_pp, n_ss, n_mss = c.n_PP, c.n_SS, c.n_mSS
        if light:
            solution_phases: tuple[SolutionPhase, ...] = ()
            metastable_phases: tuple[MetastableSolutionPhase, ...] = ()
            pure_phases: tuple[PurePhase, ...] = ()
        else:
            solution_phases = tuple(SolutionPhase._from_c(c.SS[i]) for i in range(n_ss))
            metastable_phases = tuple(
                MetastableSolutionPhase._from_c(c.mSS[i]) for i in range(n_mss)
            )
            pure_phases = tuple(PurePhase._from_c(c.PP[i]) for i in range(n_pp))

        database = _c_str(c.database)
        ph = _c_str_array(c.ph, n_ph)
        if pure_phases and mu_fix_phases:
            pure_phases = _clean_mu_fix_phases(
                pure_phases,
                ph,
                _c_int_array(c.ph_type, n_ph),
                _c_int_array(c.ph_id, n_ph),
                _c_str_array(c.oxides, n_ox),
                mu_fix_phases,
            )
        if name_solvus:
            ph_type_raw = _c_int_array(c.ph_type, n_ph)
            ph_id_raw = _c_int_array(c.ph_id, n_ph)
            renamed = []
            for i in range(n_ph):
                if ph_type_raw[i] == 1:
                    ss = c.SS[ph_id_raw[i]]
                    comp_vars = _c_double_array(ss.compVariables, ss.n_xeos)
                    renamed.append(_solvus.solvus_name(database, ph[i], comp_vars))
                else:
                    renamed.append(ph[i])
            ph = tuple(renamed)

        return cls(
            magemin_version=_c_str(c.MAGEMin_ver),
            dataset=_c_str(c.dataset),
            database=database,
            bulk_res_norm=c.bulk_res_norm,
            n_iterations=c.n_iterations,
            status=c.status,
            n_ox=n_ox,
            oxides=_c_str_array(c.oxides, n_ox),
            elements=_c_str_array(c.elements, n_ox),
            p=c.P,
            t=c.T,
            x=c.X,
            bulk=_c_double_array(c.bulk, n_ox),
            bulk_wt=_c_double_array(c.bulk_wt, n_ox),
            buffer=_c_str(c.buffer),
            buffer_n=c.buffer_n,
            gamma=_c_double_array(c.gamma, n_ox),
            g=c.G,
            m_sys=c.M_sys,
            rho=c.rho,
            f_o2=c.fO2,
            d_qfm=c.dQFM,
            a_h2o=c.aH2O,
            a_sio2=c.aSiO2,
            a_tio2=c.aTiO2,
            a_al2o3=c.aAl2O3,
            a_mgo=c.aMgO,
            a_feo=c.aFeO,
            alpha=c.alpha,
            beta=c.beta,
            cp=c.cp,
            s_cp=c.s_cp,
            cp_wt=c.cp_wt,
            v=c.V,
            v_cm3=c.V_cm3,
            entropy=c.entropy,
            enthalpy=c.enthalpy,
            system_oxygen=c.system_oxygen,
            fe3_fe2_ratio=c.Fe3_Fe2_ratio,
            bulk_mod=c.bulkMod,
            shear_mod=c.shearMod,
            bulk_modulus_m=c.bulkModulus_M,
            bulk_modulus_s=c.bulkModulus_S,
            shear_modulus_s=c.shearModulus_S,
            vp_s=c.Vp_S,
            vs_s=c.Vs_S,
            vp=c.Vp,
            vs=c.Vs,
            bulk_s=_c_double_array(c.bulk_S, n_ox),
            frac_s=c.frac_S,
            rho_s=c.rho_S,
            bulk_m=_c_double_array(c.bulk_M, n_ox),
            frac_m=c.frac_M,
            rho_m=c.rho_M,
            bulk_f=_c_double_array(c.bulk_F, n_ox),
            frac_f=c.frac_F,
            rho_f=c.rho_F,
            entropy_s=c.entropy_S,
            entropy_m=c.entropy_M,
            entropy_f=c.entropy_F,
            bulk_s_wt=_c_double_array(c.bulk_S_wt, n_ox),
            frac_s_wt=c.frac_S_wt,
            frac_s_vol=c.frac_S_vol,
            bulk_m_wt=_c_double_array(c.bulk_M_wt, n_ox),
            frac_m_wt=c.frac_M_wt,
            frac_m_vol=c.frac_M_vol,
            bulk_f_wt=_c_double_array(c.bulk_F_wt, n_ox),
            frac_f_wt=c.frac_F_wt,
            frac_f_vol=c.frac_F_vol,
            n_ph=n_ph,
            n_pp=n_pp,
            n_ss=n_ss,
            n_mss=n_mss,
            ph=ph,
            sol_name=_c_str_array(c.sol_name, n_ph),
            ph_frac=_c_double_array(c.ph_frac, n_ph),
            ph_frac_wt=_c_double_array(c.ph_frac_wt, n_ph),
            ph_frac_1at=_c_double_array(c.ph_frac_1at, n_ph),
            ph_frac_vol=_c_double_array(c.ph_frac_vol, n_ph),
            ph_type=_c_int_array(c.ph_type, n_ph),
            ph_id=_c_int_array(c.ph_id, n_ph),
            ph_id_db=_c_int_array(c.ph_id_db, n_ph),
            solution_phases=solution_phases,
            metastable_phases=metastable_phases,
            pure_phases=pure_phases,
            final_newton_system=final_newton_system,
        )

    def __str__(self) -> str:
        """Return a human-readable summary of the equilibrium result."""
        lines = [
            f"Pressure          : {self.p:g} [kbar]",
            f"Temperature       : {self.t - 273.15:g} [Celsius]",
            "Stable phase | Fraction (mol)  | Fraction (wt)",
        ]
        for name, mol_frac, wt_frac in zip(self.ph, self.ph_frac, self.ph_frac_wt, strict=True):
            lines.append(f"  {name:<12} {mol_frac:.5f}          {wt_frac:.5f}")
        lines.append(f"Gibbs free energy : {self.g:.6f}")
        lines.append(f"Density           : {self.rho:.4f} [kg/m3]")
        lines.append(f"Oxygen fugacity   : {self.f_o2:g}")
        return "\n".join(lines)
