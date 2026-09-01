"""Predefined bulk-rock compositions.

Values are transcribed directly from the ``get_bulk_*`` functions in the
vendored ``MAGEMin/src/TC_database/TC_init_database.c`` (the same tables the
MAGEMin CLI's built-in ``--test`` compositions use). This module has no C
dependency and can be imported without a built ``libMAGEMin`` library.
"""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class BulkRock:
    """A named, predefined bulk-rock composition for a specific database.

    Attributes:
        name: Short human-readable name.
        database: The MAGEMin database acronym this composition is valid for
            (e.g. ``"ig"``). Must match the oxide set/order of that database.
        reference: Short citation for the composition's origin.
        oxides: Oxide names, in the order ``values`` are given.
        values: Bulk composition values, in ``oxides`` order.
        sys_in: Whether ``values`` are in mol or wt units.
    """

    name: str
    database: str
    reference: str
    oxides: tuple[str, ...]
    values: tuple[float, ...]
    sys_in: Literal["mol", "wt"] = "mol"


_IG_OXIDES = ("SiO2", "Al2O3", "CaO", "MgO", "FeO", "K2O", "Na2O", "TiO2", "O", "Cr2O3", "H2O")

KLB1_IG = BulkRock(
    name="KLB1",
    database="ig",
    reference="Peridotite, Holland et al. (2018), given by E. Green",
    oxides=_IG_OXIDES,
    values=(38.494, 1.776, 2.824, 50.566, 5.886, 0.01, 0.250, 0.10, 0.096, 0.109, 0.0),
)

RE46_IG = BulkRock(
    name="RE46",
    database="ig",
    reference="Icelandic basalt, Yang et al. (1996), given by E. Green",
    oxides=_IG_OXIDES,
    values=(50.72, 9.16, 15.21, 16.25, 7.06, 0.01, 1.47, 0.39, 0.35, 0.01, 0.0),
)

NMORB_IG = BulkRock(
    name="N-MORB",
    database="ig",
    reference="Gale et al. (2013), given by E. Green",
    oxides=_IG_OXIDES,
    values=(53.21, 9.41, 12.21, 12.21, 8.65, 0.09, 2.90, 1.21, 0.69, 0.02, 0.0),
)

FPWM_PELITE_MP = BulkRock(
    name="FPWorldMedian pelite",
    database="mp",
    reference="Forshaw & Pattison (2023)",
    oxides=("SiO2", "Al2O3", "CaO", "MgO", "FeO", "K2O", "Na2O", "TiO2", "O", "MnO", "H2O"),
    values=(70.999, 12.8065, 0.771, 3.978, 6.342, 2.7895, 1.481, 0.758, 0.72933, 0.075, 30.0),
)

SM89_MORB_MB = BulkRock(
    name="SM89 oxidised average MORB",
    database="mb",
    reference="Sun & McDonough (1989)",
    oxides=("SiO2", "Al2O3", "CaO", "MgO", "FeO", "K2O", "Na2O", "TiO2", "O", "H2O"),
    values=(52.47, 9.10, 12.21, 12.71, 8.15, 0.23, 2.61, 1.05, 1.47, 20.0),
)

SERPENTINE_UM = BulkRock(
    name="Serpentine (oxidized)",
    database="um",
    reference="Evans & Frost (2021)",
    oxides=("SiO2", "Al2O3", "MgO", "FeO", "O", "H2O", "S"),
    values=(20.044, 0.6256, 29.24, 3.149, 0.7324, 46.755, 0.3),
)

KLB1_MTL = BulkRock(
    name="KLB1",
    database="mtl",
    reference="Peridotite, Holland et al. (2018), given by E. Green",
    oxides=("SiO2", "Al2O3", "CaO", "MgO", "FeO", "Na2O"),
    values=(38.494, 1.776, 2.824, 50.566, 5.886, 0.250),
)

KLB1_SB = BulkRock(
    name="KLB1",
    database="sb11",
    reference="Peridotite, Holland et al. (2018), given by E. Green",
    oxides=("SiO2", "CaO", "Al2O3", "FeO", "MgO", "Na2O"),
    values=(38.41, 3.18, 1.8, 5.85, 50.49, 0.250),
)

BASALT_GH = BulkRock(
    name="Rough basalt",
    database="xMELTS",
    reference="MAGEMin GH_database/GH_init_database.c get_bulk_gh test=0",
    oxides=(
        "SiO2",
        "Al2O3",
        "CaO",
        "MgO",
        "FeO",
        "K2O",
        "Na2O",
        "TiO2",
        "O",
        "MnO",
        "Cr2O3",
        "H2O",
        "CO2",
    ),
    values=(49.90, 8.82, 10.69, 11.90, 7.51, 0.32, 2.42, 1.13, 0.37, 0.13, 0.02, 6.66, 0.14),
)

BULK_ROCKS_BY_DATABASE: dict[str, tuple[BulkRock, ...]] = {
    "ig": (KLB1_IG, RE46_IG, NMORB_IG),
    "mp": (FPWM_PELITE_MP,),
    "mb": (SM89_MORB_MB,),
    "um": (SERPENTINE_UM,),
    "mtl": (KLB1_MTL,),
    "sb11": (KLB1_SB,),
    "xMELTS": (BASALT_GH,),
}
