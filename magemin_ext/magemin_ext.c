/*@ ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
 **
 **   Project      : magemin (Python interface to MAGEMin)
 **   License      : GNU GENERAL PUBLIC LICENSE Version 3, 29 June 2007
 **
 ** ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ @*/
/*@
 **   See magemin_ext.h. This file never modifies anything under MAGEMin/ --
 **   it only #includes MAGEMin's unmodified headers and calls its existing,
 **   already-exported internal functions (the same ones MAGEMin_api.c itself
 **   calls). Where a function here duplicates a MAGEMin_api.c sequence
 **   (MAGEMin_InitEx vs MAGEMin_Init, MAGEMin_ComputeEquilibriumEx vs
 **   MAGEMin_ComputeEquilibrium), that duplication is unavoidable: the extra
 **   work (setting research_group before SetupDatabase runs; splicing phase
 **   suppression in between ComputeG0_point and ComputeEquilibrium_Point)
 **   has to happen *inside* the sequence, and MAGEMin_api.c cannot be edited
 **   to expose a hook for it. Keep these in sync with MAGEMin_api.c's own
 **   MAGEMin_Init/MAGEMin_ComputeEquilibrium if that file's sequence changes.
 **
 **   g_hash_lock (below) exists because MAGEMin/src/hash_init.h declares its
 **   EM/DEW/PP endmember-lookup tables as plain process-wide globals, rebuilt
 **   with no lock in InitializeDatabases and read with no lock throughout the
 **   compute path -- not per-handle state, and not something a fix inside
 **   MAGEMin/ itself would be allowed to touch. This lock serializes the
 **   write side (MAGEMin_InitEx) against the read side (the entirety of
 **   MAGEMin_ComputeEquilibriumEx, since the lookups are reached at multiple
 **   points throughout it) so that multi_point_minimization's thread pool --
 **   many concurrent handles for one database -- is actually safe.
 @*/

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <pthread.h>

#include "toolkit.h"
#include "initialize.h"
#include "dump_function.h"
#include "MAGEMin.h"
#include "MAGEMin_api.h"

#include "magemin_ext.h"

static pthread_rwlock_t g_hash_lock = PTHREAD_RWLOCK_INITIALIZER;

MAGEMin_Handle *MAGEMin_InitEx(	const char *database,
									const char *research_group,
									int         verbose,
									int         solver				){

	if (research_group == NULL){
		research_group = "tc";
	}
	if (	strcmp(research_group,"tc") != 0 &&
			strcmp(research_group,"sb") != 0 &&
			strcmp(research_group,"gh") != 0		){
		printf(" MAGEMin_InitEx error: research_group must be \"tc\", \"sb\", or \"gh\", got '%s'\n",research_group);
		return NULL;
	}
	if (database == NULL){
		printf(" MAGEMin_InitEx error: database must not be NULL\n");
		return NULL;
	}
	if (strlen(database) > 63){
		printf(" MAGEMin_InitEx error: database acronym '%s' is too long\n",database);
		return NULL;
	}

	MAGEMin_Handle *h = malloc(sizeof(MAGEMin_Handle));

	h->gv = global_variable_alloc(		&h->z_b					);

	h->gv.verbose = verbose;

	/* overrides global_variable_alloc's own default (2) -- must happen
	   before SetupDatabase below, which forces this back to 0 for "sb"/"gh"
	   regardless of what's requested here (see magemin_ext.h) */
	h->gv.solver = solver;

	/* gv.research_group is malloc'd 5 bytes ("tc"/"sb"/"gh" + NUL fit as-is) */
	strcpy(h->gv.research_group,research_group);

	/* gv.db is malloc'd only 5 bytes (4 chars + NUL) by global_variable_alloc,
	   sized for the "tc"-family acronyms MAGEMin_Init alone ever has to hold.
	   "xMELTS"/"rMELTS"/"pMELTS" are 6 chars and would overflow it -- resize
	   here rather than touching MAGEMin/src/initialize.c's allocation. */
	if (strlen(database) >= 5){
		free(h->gv.db);
		h->gv.db = malloc(strlen(database) + 1);
	}
	strcpy(h->gv.db,database);

	/* write-side of the EM/DEW/PP global tables (see g_hash_lock comment
	   above) -- exclusive against every other InitEx call and every
	   ComputeEquilibriumEx read */
	pthread_rwlock_wrlock(&g_hash_lock);

	h->gv = SetupDatabase(				h->gv,
									   &h->z_b					);

	h->gv = global_variable_init(		h->gv,
									   &h->z_b					);

	h->DB = InitializeDatabases(		h->gv,
										h->gv.EM_database		);

	init_simplex_A(					&h->splx_data,
										 h->gv					);
	init_simplex_B_em(					&h->splx_data,
										 h->gv					);

	pthread_rwlock_unlock(&g_hash_lock);

	return h;
}

int MAGEMin_SetBuffer(				MAGEMin_Handle *h,
									const char     *buffer,
									double          buffer_n		){

	if (h == NULL) return -1;

	if (buffer == NULL || strcmp(buffer,"none") == 0){
		strcpy(h->gv.buffer,"none");
		h->gv.buffer_n = 0.0;
		return 0;
	}

	if (strlen(buffer) > 9){
		printf(" MAGEMin_SetBuffer error: buffer name '%s' is too long\n",buffer);
		return -1;
	}

	int found = 0;
	for (int i = 0; i < h->gv.len_pp; i++){
		if (strcmp(buffer,h->gv.PP_list[i]) == 0){ found = 1; break; }
	}
	if (!found){
		printf(" MAGEMin_SetBuffer error: unknown buffer/activity name '%s' for database '%s'\n",buffer,h->gv.db);
		return -1;
	}

	/* write into gv.buffer's existing malloc'd allocation -- never repoint it
	   (repointing gv.buffer at externally-owned memory instead of copying
	   bytes into it is the documented root cause of a real SIGABRT in this
	   codebase's history: an invalid free() on memory C never allocated,
	   see the fix comment in MAGEMin/src/MAGEMin.c's FreeDatabases). */
	strcpy(h->gv.buffer,buffer);
	h->gv.buffer_n = buffer_n;
	return 0;
}

stb_system *MAGEMin_ComputeEquilibriumEx(	MAGEMin_Handle  *h,
											double           P,
											double           T,
											const double    *bulk,
											const char      *sys_in,
											const char     **suppress_phases,
											int              n_suppress	){

	/* identical to MAGEMin_ComputeEquilibrium (MAGEMin_api.c) up to and
	   including the ComputeG0_point call */
	if (strcmp(sys_in,"mol") != 0 && strcmp(sys_in,"wt") != 0){
		printf(" MAGEMin_ComputeEquilibriumEx error: sys_in must be \"mol\" or \"wt\"\n");
		return NULL;
	}
	strcpy(h->gv.sys_in,sys_in);

	/* read-side of the EM/DEW/PP global tables (see g_hash_lock comment at
	   the top of this file) -- reached not just by ComputeG0_point below but
	   also by ComputePostProcessing and fill_output_struct's DEW path, so
	   this covers the rest of the function rather than just its start; any
	   number of threads can hold this concurrently, only InitEx is exclusive
	   against it */
	pthread_rwlock_rdlock(&g_hash_lock);

	h->z_b.P = P;
	h->z_b.T = T + 273.15;

	for (int i = 0; i < h->gv.len_ox; i++){
		h->gv.arg_bulk[i] = bulk[i];
	}

	io_data dummy_input_data[1];
	memset(dummy_input_data,0,sizeof(dummy_input_data));

	h->z_b = retrieve_bulk_PT(			h->gv,
										dummy_input_data,
										0,
										h->z_b					);

	h->gv = reset_gv(					h->gv,
										h->z_b,
										h->DB.PP_ref_db,
										h->DB.SS_ref_db			);

	h->z_b = reset_z_b_bulk(			h->gv,
										h->z_b					);

	reset_simplex_A(				   &h->splx_data,
										h->z_b,
										h->gv					);
	reset_simplex_B_em(				   &h->splx_data,
										h->gv					);

	reset_cp(							h->gv,
										h->z_b,
										h->DB.cp				);

	reset_SS(							h->gv,
										h->z_b,
										h->DB.SS_ref_db			);

	reset_sp(							h->gv,
										h->DB.sp				);

	/* Some vendored databases hard-code a single default variant for a
	   near-degenerate phase-model pair -- see MAGEMin.h's gv.mbCpx/mbIlm/
	   mpSp/mpIlm (initialize.c defaults them all to 0) and
	   tc_gss_function.c's *_id==0/1 guards around each pair's pseudocompound
	   generation. Left at 0, only ONE variant of each pair (e.g. "mp"'s
	   "ilm", never "ilmm") ever gets pseudocompounds generated at all -- so
	   suppress_phases zeroing that variant's ss_flags below still leaves the
	   OTHER variant unreachable, since it was never generated in the first
	   place. Setting these to 2 (checked directly against MAGEMin.c's own
	   CLI help text: not 0 or 1) activates both variants' generation before
	   suppression runs, matching MAGEMin_C.jl's own point_wise_minimization
	   (MAGEMin_wrappers.jl). Unlike that Julia code -- which only sets this
	   when a phase is being removed, and never resets it back -- this always
	   assigns explicitly every call, 2 or 0, so it can never silently leak
	   from a previous suppressing call into a later non-suppressing one on
	   the same reused handle (same rationale as MAGEMin_SetBuffer's own
	   always-clear-to-"none" behavior above). */
	h->gv.mbCpx = n_suppress > 0 ? 2 : 0;
	h->gv.mbIlm = n_suppress > 0 ? 2 : 0;
	h->gv.mpSp  = n_suppress > 0 ? 2 : 0;
	h->gv.mpIlm = n_suppress > 0 ? 2 : 0;

	h->gv = ComputeG0_point(			h->gv.EM_database,
										h->z_b,
										h->gv,
										h->DB.PP_ref_db,
										h->DB.SS_ref_db			);

	/* NEW: phase suppression. This is the only point in the sequence where
	   it can take effect -- reset_gv (above) zeroed every phase's flags, and
	   ComputeG0_point's own pure-phase loop just re-defaulted them back to
	   active, so anything set before this point would already be overwritten;
	   ComputeEquilibrium_Point (below) is the first thing that reads flags
	   for real. */
	for (int k = 0; k < n_suppress; k++){
		const char *name = suppress_phases[k];
		int found = 0;

		for (int i = 0; i < h->gv.len_ss; i++){
			if (strcmp(name,h->gv.SS_list[i]) == 0){
				for (int f = 0; f < h->gv.n_flags; f++){
					h->DB.SS_ref_db[i].ss_flags[f] = 0;
				}
				found = 1;
				break;
			}
		}
		if (!found){
			for (int i = 0; i < h->gv.len_pp; i++){
				if (strcmp(name,h->gv.PP_list[i]) == 0){
					for (int f = 0; f < h->gv.n_flags; f++){
						h->gv.pp_flags[i][f] = 0;
					}
					found = 1;
					break;
				}
			}
		}
		if (!found){
			printf(" MAGEMin_ComputeEquilibriumEx error: unknown phase name '%s' to suppress\n",name);
			pthread_rwlock_unlock(&g_hash_lock);
			return NULL;
		}
	}

	/* identical to MAGEMin_ComputeEquilibrium (MAGEMin_api.c) from here on */
	io_data dummy_point;
	memset(&dummy_point,0,sizeof(dummy_point));

	h->gv = ComputeEquilibrium_Point(	h->gv.EM_database,
										dummy_point,
										h->z_b,
										h->gv,

									   &h->splx_data,
										h->DB.PP_ref_db,
										h->DB.SS_ref_db,
										h->DB.cp				);

	h->gv = ComputePostProcessing(		h->z_b,
										h->gv,
										h->DB.PP_ref_db,
										h->DB.SS_ref_db,
										h->DB.cp				);

	fill_output_struct(					h->gv,
									   &h->splx_data,
										h->z_b,

										h->DB.PP_ref_db,
										h->DB.SS_ref_db,
										h->DB.cp,
										h->DB.sp				);

	pthread_rwlock_unlock(&g_hash_lock);

	return &h->DB.sp[0];
}

int MAGEMin_NSolutionPhases(		MAGEMin_Handle *h				){
	return h->gv.len_ss;
}

char **MAGEMin_SolutionPhaseNames(	MAGEMin_Handle *h				){
	return h->gv.SS_list;
}

int MAGEMin_NPurePhases(			MAGEMin_Handle *h				){
	return h->gv.len_pp;
}

char **MAGEMin_PurePhaseNames(		MAGEMin_Handle *h				){
	return h->gv.PP_list;
}
