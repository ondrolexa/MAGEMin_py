"""Tests for sb/"all" database support, and gh/MELTS's deliberate deactivation."""

import os
import subprocess
import sys

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


_DEW_CHILD = """
from magemin import MAGEMin, bulk_rocks
with MAGEMin("all") as mg:
    assert mg.compute(P=10, T=800, bulk=bulk_rocks.FPWM_PELITE_ALL).status == 0
"""


def _limit_address_space() -> None:
    import resource

    cap = 4 * 1024**3
    resource.setrlimit(resource.RLIMIT_AS, (cap, cap))


@pytest.mark.skipif(sys.platform != "linux", reason="MALLOC_PERTURB_ is glibc-specific")
@pytest.mark.skipif(
    "asan" in os.environ.get("LD_PRELOAD", ""),
    reason="ASan's shadow memory can't fit under RLIMIT_AS; its malloc_fill_byte covers this",
)
def test_all_database_survives_uninitialized_heap(require_library: None) -> None:
    """The "all" database initializes cleanly even when fresh heap memory isn't zeroed.

    Every solution model must fully initialize its size fields (e.g. DEW's n_w/n_v) --
    otherwise arrays get allocated from whatever the heap holds, which is usually zero by
    luck. MALLOC_PERTURB_ makes glibc fill every allocation with a non-zero pattern so such a
    bug fires every time; the child runs under an address-space cap so a garbage-sized
    allocation fails fast instead of exhausting the machine's memory.
    """
    proc = subprocess.run(
        [sys.executable, "-c", _DEW_CHILD],
        env={**os.environ, "MALLOC_PERTURB_": "190"},
        preexec_fn=_limit_address_space,
        capture_output=True,
        timeout=300,
    )
    assert proc.returncode == 0, proc.stderr.decode(errors="replace")[-2000:]


def test_gh_database_disabled(require_library: None) -> None:
    """The 'gh' (MELTS) family is implemented upstream but deliberately unlisted/deactivated."""
    for acronym in ("xMELTS", "rMELTS", "pMELTS"):
        with pytest.raises(MAGEMinInitError):
            MAGEMin(acronym)


def test_unknown_database_acronym_raises(require_library: None) -> None:
    """An unrecognized database acronym is rejected before reaching the C library."""
    with pytest.raises(MAGEMinInitError):
        MAGEMin("bogus")


def test_mpf_and_br_acronyms_rejected(require_library: None) -> None:
    """Upstream acronyms this package deliberately doesn't expose raise instead of crashing.

    "mpf" segfaults inside MAGEMin's global_variable_TC_init (EM_database = -1 has no init
    branch), and "po" is the unwrapped "br" (Berman) research group's only database.
    """
    for acronym in ("mpf", "po"):
        with pytest.raises(MAGEMinInitError):
            MAGEMin(acronym)
