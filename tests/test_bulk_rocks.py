"""Tests for magemin.bulk_rocks -- pure Python, no compiled library needed."""

from magemin import bulk_rocks


def test_importable_without_library() -> None:
    """The module and its constants must be usable without libMAGEMin built."""
    assert bulk_rocks.KLB1_IG.name == "KLB1"
    assert bulk_rocks.KLB1_IG.database == "ig"
    assert len(bulk_rocks.KLB1_IG.oxides) == len(bulk_rocks.KLB1_IG.values)


def test_bulk_rocks_by_database_lookup() -> None:
    """BULK_ROCKS_BY_DATABASE indexes every constant under its own database."""
    for database, rocks in bulk_rocks.BULK_ROCKS_BY_DATABASE.items():
        for rock in rocks:
            assert rock.database == database
            assert len(rock.oxides) == len(rock.values)
