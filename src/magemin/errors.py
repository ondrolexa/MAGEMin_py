"""Exception hierarchy for the ``magemin`` package."""


class MAGEMinError(Exception):
    """Base class for all errors raised by this package."""


class MAGEMinLibraryNotFoundError(MAGEMinError):
    """Raised when the compiled ``libMAGEMin`` shared library cannot be located.

    See the package README for how to build the library (``scripts/build_lib.sh``)
    and how to point the loader at a non-default location via the
    ``MAGEMIN_LIB_PATH`` environment variable.
    """


class MAGEMinDownloadError(MAGEMinError):
    """Raised when downloading or building the MAGEMin C library from source fails.

    Covers an HTTP 404 (the requested version/branch/commit doesn't exist
    upstream), other network failures, ``make``/``cc`` missing from ``PATH``,
    and a non-zero exit from any build step (with its captured output
    included in the message).
    """


class MAGEMinInitError(MAGEMinError):
    """Raised when a database handle cannot be created.

    Covers an unrecognized database acronym (rejected before reaching the C
    library) and a ``NULL`` return from ``MAGEMin_InitEx``.
    """


class MAGEMinComputeError(MAGEMinError):
    """Raised when an equilibrium computation fails or is given invalid input.

    Covers an invalid ``sys_in`` value, an unrecognized ``buffer`` name,
    ``buffer``/``buffer_value`` given without its pair, an out-of-range
    fixed-activity ``buffer_value``, a ``buffer`` rejected by
    ``MAGEMin_SetBuffer`` (valid name, but not registered for this
    database/research group), and a ``NULL`` return from
    ``MAGEMin_ComputeEquilibriumEx`` (including an unrecognized
    ``suppress_phases`` name) -- all rejected before or by the C library.
    """


class BulkCompositionError(MAGEMinError, ValueError):
    """Raised when a bulk composition does not match the expected oxide set.

    This includes a plain sequence whose length does not match the number of
    oxides for the initialized database, and a :class:`~magemin.bulk_rocks.BulkRock`
    whose ``oxides`` do not match the database's oxide names/order.
    """


class MAGEMinClosedHandleError(MAGEMinError):
    """Raised when a :class:`~magemin.core.MAGEMin` instance is used after ``close()``."""


class MAGEMinPlottingError(MAGEMinError):
    """Raised by :meth:`~magemin.diagrams.PhaseDiagram.plot` when matplotlib is unavailable.

    Install the optional ``plot`` extra (``pip install magemin[plot]``) to fix this.
    """


class MAGEMinMeshError(MAGEMinError):
    """Raised by :class:`~magemin.pseudosection.Pseudosection` when numpy/scipy are unavailable.

    Covers :meth:`~magemin.pseudosection.Pseudosection.pt`,
    :meth:`~magemin.pseudosection.Pseudosection.px`,
    :meth:`~magemin.pseudosection.Pseudosection.tx`, and
    :meth:`~magemin.pseudosection.Pseudosection.refine`. Install the optional ``mesh`` extra
    (``pip install magemin[mesh]``) to fix this.
    """
