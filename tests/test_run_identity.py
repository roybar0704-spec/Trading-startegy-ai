"""B-1 Commit 1: RunIdentity frozen dataclass (src/core/types.py, D-038/D-067)."""

import dataclasses

import pytest

from src.core.types import RunIdentity


def test_valid_creation_with_defaults():
    identity = RunIdentity(data_version="abc123", split_type="fixture")
    assert identity.data_version == "abc123"
    assert identity.split_type == "fixture"
    assert identity.seed is None
    assert identity.code_version is None
    assert identity.config_hash is None


def test_valid_creation_all_fields_supplied():
    identity = RunIdentity(
        data_version="abc123", split_type="holdout", seed=42,
        code_version="deadbeef", config_hash=None,
    )
    assert identity.seed == 42
    assert identity.code_version == "deadbeef"


def test_frozen_dataclass_is_immutable():
    identity = RunIdentity(data_version="abc123", split_type="fixture")
    with pytest.raises(dataclasses.FrozenInstanceError):
        identity.data_version = "other"  # type: ignore[misc]


def test_split_type_accepts_all_declared_values():
    for split_type in (
        "in_sample", "walk_forward_train", "walk_forward_test",
        "holdout", "baseline", "fixture",
    ):
        identity = RunIdentity(data_version="v1", split_type=split_type)
        assert identity.split_type == split_type
