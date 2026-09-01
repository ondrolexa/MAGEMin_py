/*@ ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
 **
 **   Project      : magemin (Python interface to MAGEMin)
 **   License      : GNU GENERAL PUBLIC LICENSE Version 3, 29 June 2007
 **
 ** ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ @*/
/*@
 **   Companion extension to MAGEMin's own MAGEMin_api.h, adding oxygen-buffer/
 **   fixed-activity constraints, phase suppression, sb/gh database support,
 **   and phase-name discovery. Lives outside the vendored MAGEMin/ tree and
 **   only calls MAGEMin's existing internal functions through its unmodified
 **   headers -- MAGEMin/ is never edited, so a future re-vendoring/upgrade of
 **   MAGEMin just drops in a fresh copy and rebuilds, no patch to reapply.
 **   Operates on the same MAGEMin_Handle that MAGEMin_api.h's own 5 functions
 **   use, so handles created via MAGEMin_InitEx work with MAGEMin_NOxides/
 **   MAGEMin_OxideNames/MAGEMin_Free unchanged.
 @*/

#ifndef __MAGEMIN_EXT_H_
#define __MAGEMIN_EXT_H_

#include "MAGEMin_api.h"

#include <pthread.h>

#ifdef __cplusplus
extern "C" {
#endif

/**
 * Allocate and initialize a MAGEMin instance for the given thermodynamic
 * database and research group ("tc", "sb", or "gh"). Supersedes MAGEMin_Init:
 * that function always uses research_group "tc", so "sb11"/"sb21"/"sb24" and
 * "xMELTS"/"rMELTS"/"pMELTS" are unreachable through it (SetupDatabase treats
 * research_group as an already-resolved precondition, never inferring it
 * from the database acronym). verbose follows MAGEMin_Init's semantics.
 *
 * solver selects gv.solver: 0 = legacy, 1 = PGE + legacy hybrid, 2 = hybrid
 * PGE/LP (MAGEMin's own library default), 3 = a fourth solver variant not
 * otherwise documented upstream beyond its existence as a branch in
 * MAGEMin.c. Set once here (global_variable_alloc's own default is
 * overridden before SetupDatabase runs) and never touched again by
 * reset_gv, so it's stable for the handle's whole lifetime. SetupDatabase
 * itself forces this back to 0 for "sb"/"gh" research groups regardless of
 * what's requested here -- those only support the legacy solver upstream.
 * Different solvers can converge to different local minima for near-
 * degenerate phase pairs (e.g. the "mp" database's "ilm"/"ilmm" ilmenite-
 * group models) -- pass MAGEMin's own default (2) unless reproducing a
 * specific reference case that used a different one.
 *
 * Returns NULL on failure (unknown research_group, or NULL database).
 */
MAGEMin_Handle *MAGEMin_InitEx(	const char *database,
									const char *research_group,
									int         verbose,
									int         solver				);

/**
 * Set (or clear) the active oxygen buffer / fixed-activity constraint on an
 * already-initialized handle. Takes effect on the next MAGEMin_ComputeEquilibrium
 * / MAGEMin_ComputeEquilibriumEx call and persists across calls until changed
 * again -- pass buffer="none" (or NULL) to explicitly clear it.
 *
 * buffer   : one of the redox buffers "O2","qfm","mw","qif","nno","hm","iw",
 *            "cco" (buffer_n is an additive log-unit offset, e.g. dQFM-style,
 *            unclamped), or one of the fixed-activity constraints "aH2O",
 *            "aO2","aMgO","aFeO","aAl2O3","aTiO2" (buffer_n is the activity
 *            value itself, internally clamped to (1e-8, 1-1e-8)), or "none"/
 *            NULL to clear. Must already be registered in this handle's
 *            database (checked against its PP_list) -- not every name is
 *            available for every database/research_group.
 * buffer_n : offset or activity value, per buffer's kind above.
 *
 * Returns 0 on success, -1 on an unrecognized/unavailable buffer name.
 */
int MAGEMin_SetBuffer(				MAGEMin_Handle *h,
									const char     *buffer,
									double          buffer_n		);

/**
 * Compute the stable equilibrium phase assemblage at one (P,T,bulk) point,
 * like MAGEMin_ComputeEquilibrium, with optional phase suppression.
 *
 * suppress_phases : array of n_suppress phase names (solution-phase model
 *                   names or pure-phase names, as returned by
 *                   MAGEMin_SolutionPhaseNames/MAGEMin_PurePhaseNames) to
 *                   exclude from this point's minimization. Pass NULL/0 for
 *                   no suppression -- behaviorally identical to
 *                   MAGEMin_ComputeEquilibrium in that case.
 *
 * Returns NULL on failure, including when a name in suppress_phases matches
 * neither this handle's solution-phase nor pure-phase list.
 */
stb_system *MAGEMin_ComputeEquilibriumEx(	MAGEMin_Handle  *h,
											double           P,
											double           T,
											const double    *bulk,
											const char      *sys_in,
											const char     **suppress_phases,
											int              n_suppress	);

/** number of solution-phase models registered for this handle's database */
int MAGEMin_NSolutionPhases(		MAGEMin_Handle *h				);

/** solution-phase model names, valid for MAGEMin_ComputeEquilibriumEx's
 *  suppress_phases. Owned by the handle, do not free. */
char **MAGEMin_SolutionPhaseNames(	MAGEMin_Handle *h				);

/** number of pure phases registered for this handle's database */
int MAGEMin_NPurePhases(			MAGEMin_Handle *h				);

/** pure-phase names, valid for MAGEMin_ComputeEquilibriumEx's
 *  suppress_phases. Owned by the handle, do not free. */
char **MAGEMin_PurePhaseNames(		MAGEMin_Handle *h				);

#ifdef __cplusplus
}
#endif

#endif
