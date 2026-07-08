"""Unit coverage: config/rules_v1.yaml hash integrity guard."""

import pytest

from src.config.frozen_guard import FrozenConfigTampered, verify_frozen_rules


def test_verify_frozen_rules_passes_on_checked_in_files():
    digest = verify_frozen_rules()
    assert len(digest) == 64


def test_verify_frozen_rules_detects_tampering(tmp_path):
    rules_path = tmp_path / "rules_v1.yaml"
    hash_path = tmp_path / "rules_v1.yaml.sha256"
    rules_path.write_text("spec_version: '1.0'\n")
    hash_path.write_text("0" * 64)

    with pytest.raises(FrozenConfigTampered):
        verify_frozen_rules(rules_path, hash_path)
