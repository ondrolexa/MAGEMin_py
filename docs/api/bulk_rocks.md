# Predefined bulk rocks

Values are transcribed directly from the `get_bulk_*` functions in the vendored
`MAGEMin/src/TC_database/TC_init_database.c` (the same tables the MAGEMin CLI's built-in `--test`
compositions use). This module has no C dependency and can be imported without a built
`libMAGEMin` library.

::: magemin.bulk_rocks.BulkRock

## Available constants

| Constant | `database` | Reference |
|---|---|---|
| `KLB1_IG` | `ig` | Peridotite, Holland et al. (2018), given by E. Green |
| `RE46_IG` | `ig` | Icelandic basalt, Yang et al. (1996), given by E. Green |
| `NMORB_IG` | `ig` | Gale et al. (2013), given by E. Green |
| `FPWM_PELITE_MP` | `mp` | Forshaw & Pattison (2023) |
| `SM89_MORB_MB` | `mb` | Sun & McDonough (1989) |
| `SERPENTINE_UM` | `um` | Evans & Frost (2021) |
| `KLB1_MTL` | `mtl` | Peridotite, Holland et al. (2018), given by E. Green |

`BULK_ROCKS_BY_DATABASE` indexes these by their `database` acronym:

```python
from magemin import bulk_rocks

for rock in bulk_rocks.BULK_ROCKS_BY_DATABASE["ig"]:
    print(rock.name, rock.oxides, rock.values)
```
