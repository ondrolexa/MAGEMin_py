# Results API

The output of [`MAGEMin.compute()`][magemin.core.MAGEMin.compute]: an
[`EquilibriumResult`][magemin.results.EquilibriumResult] holding system-level properties plus three
tuples of nested per-phase dataclasses.

Every field here is a plain Python value (str/int/float/tuple), fully copied out of MAGEMin's C
output struct at the moment `compute()` returns -- none of it depends on the underlying `MAGEMin`
handle staying open or unreused.

::: magemin.results.EquilibriumResult

::: magemin.results.SolutionPhase

::: magemin.results.MetastableSolutionPhase

::: magemin.results.PurePhase
