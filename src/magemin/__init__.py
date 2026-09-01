"""Python interface to MAGEMin.

MAGEMin is a C package that performs Gibbs energy minimization for
thermodynamic equilibrium calculations.
"""

from magemin import bulk_rocks
from magemin._download import default_cache_dir, install
from magemin._solvus import base_phase_name, solvus_name
from magemin.core import MAGEMin, Point, multi_point_minimization
from magemin.diagrams import DiagramCell, DiagramPoint, PhaseDiagram
from magemin.errors import (
    BulkCompositionError,
    MAGEMinClosedHandleError,
    MAGEMinComputeError,
    MAGEMinDownloadError,
    MAGEMinError,
    MAGEMinInitError,
    MAGEMinLibraryNotFoundError,
    MAGEMinMeshError,
    MAGEMinPlottingError,
)
from magemin.pseudosection import MeshPoint, Pseudosection
from magemin.results import EquilibriumResult, MetastableSolutionPhase, PurePhase, SolutionPhase

__all__ = [
    "MAGEMin",
    "Point",
    "multi_point_minimization",
    "PhaseDiagram",
    "DiagramPoint",
    "DiagramCell",
    "Pseudosection",
    "MeshPoint",
    "bulk_rocks",
    "solvus_name",
    "base_phase_name",
    "install",
    "default_cache_dir",
    "EquilibriumResult",
    "SolutionPhase",
    "MetastableSolutionPhase",
    "PurePhase",
    "MAGEMinError",
    "MAGEMinLibraryNotFoundError",
    "MAGEMinInitError",
    "MAGEMinComputeError",
    "BulkCompositionError",
    "MAGEMinClosedHandleError",
    "MAGEMinDownloadError",
    "MAGEMinPlottingError",
    "MAGEMinMeshError",
]
