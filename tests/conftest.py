"""Shared pytest fixtures for the magemin test suite."""

from collections.abc import Iterator

import pytest

from magemin import MAGEMin, _lib
from magemin.errors import MAGEMinLibraryNotFoundError


@pytest.fixture(scope="session")
def library_available() -> bool:
    """Whether libMAGEMin could be located/loaded in this environment."""
    try:
        _lib.get_library()
    except MAGEMinLibraryNotFoundError:
        return False
    return True


@pytest.fixture
def require_library(library_available: bool) -> None:
    """Skip a test if libMAGEMin isn't built."""
    if not library_available:
        pytest.skip("libMAGEMin not built; run ./scripts/build_lib.sh")


@pytest.fixture
def ig(require_library: None) -> Iterator[MAGEMin]:
    """A MAGEMin instance initialized with the 'ig' (igneous) database."""
    with MAGEMin("ig") as mg:
        yield mg


@pytest.fixture(scope="session")
def matplotlib_available() -> bool:
    """Whether the optional `matplotlib` dependency is installed."""
    try:
        import matplotlib
    except ImportError:
        return False
    matplotlib.use("Agg")  # headless backend, before any pyplot import
    return True


@pytest.fixture
def require_matplotlib(matplotlib_available: bool) -> None:
    """Skip a test if matplotlib isn't installed."""
    if not matplotlib_available:
        pytest.skip(
            "matplotlib not installed; run `uv sync --group dev` or `pip install magemin[plot]`"
        )


@pytest.fixture(scope="session")
def mesh_available() -> bool:
    """Whether the optional `numpy`/`scipy` dependencies are installed."""
    try:
        import numpy  # noqa: F401
        import scipy  # noqa: F401
    except ImportError:
        return False
    return True


@pytest.fixture
def require_mesh(mesh_available: bool) -> None:
    """Skip a test if numpy/scipy aren't installed."""
    if not mesh_available:
        pytest.skip(
            "numpy/scipy not installed; run `uv sync --group dev` or `pip install magemin[mesh]`"
        )
