from __future__ import annotations

from types import SimpleNamespace

import pytest

from strawberry_alchemy import SliceMetadata


def _info(max_results: int = 100) -> SimpleNamespace:
    return SimpleNamespace(schema=SimpleNamespace(config=SimpleNamespace(relay_max_results=max_results)))


def test_slice_metadata_first_after() -> None:
    meta = SliceMetadata.from_arguments(info=_info(), after="YXJyYXljb25uZWN0aW9uOjQ=", first=10)
    # after cursor index 4 → start 5, end 15
    assert meta.start == 5
    assert meta.end == 15
    assert meta.fetch_limit == 11


def test_slice_metadata_before_last() -> None:
    # before index 20, last 5 → window ending at 20
    meta = SliceMetadata.from_arguments(info=_info(), before="YXJyYXljb25uZWN0aW9uOjIw", last=5)
    assert meta.end == 20
    assert meta.start == 15
    assert meta.fetch_limit == 6


def test_slice_metadata_defaults_to_max_results() -> None:
    meta = SliceMetadata.from_arguments(info=_info(max_results=25))
    assert meta.start == 0
    assert meta.end == 25
    assert meta.fetch_limit is None


def test_slice_metadata_rejects_negative_first() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        SliceMetadata.from_arguments(info=_info(), first=-1)


def test_slice_metadata_rejects_first_above_max() -> None:
    with pytest.raises(ValueError, match="cannot be higher"):
        SliceMetadata.from_arguments(info=_info(max_results=10), first=11)


def test_slice_metadata_rejects_negative_last() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        SliceMetadata.from_arguments(info=_info(), last=-1)
