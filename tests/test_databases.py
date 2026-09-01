"""Tests for sb/"all" database support, and gh/MELTS's deliberate deactivation."""

import pytest

from magemin import MAGEMin, bulk_rocks
from magemin.errors import MAGEMinInitError


def test_sb11_database_computes(require_library: None) -> None:
    """The 'sb' (Stixrude & Lithgow-Bertelloni) database family is reachable."""
    with MAGEMin("sb11") as mg:
        result = mg.compute(P=10, T=800, bulk=bulk_rocks.KLB1_SB)
        assert result.status == 0


def test_all_database_computes(require_library: None) -> None:
    """The 'all' database (union of mp/mb/mbe/ig/igd/igad/um/ume/mpe, incl. DEW) is reachable."""
    with MAGEMin("all") as mg:
        result = mg.compute(P=10, T=800, bulk=bulk_rocks.FPWM_PELITE_ALL)
        assert result.status == 0


def test_gh_database_disabled(require_library: None) -> None:
    """The 'gh' (MELTS) family is implemented upstream but deliberately unlisted/deactivated."""
    for acronym in ("xMELTS", "rMELTS", "pMELTS"):
        with pytest.raises(MAGEMinInitError):
            MAGEMin(acronym)


def test_unknown_database_acronym_raises(require_library: None) -> None:
    """An unrecognized database acronym is rejected before reaching the C library."""
    with pytest.raises(MAGEMinInitError):
        MAGEMin("bogus")
