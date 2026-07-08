"""Integrity guard for the frozen strategy-rules config.

``config/rules_v1.yaml`` encodes SPEC_V1_FROZEN.md and must never be edited
in place. Any drift is a hard stop, not a warning.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RULES_PATH = REPO_ROOT / "config" / "rules_v1.yaml"
RULES_HASH_PATH = REPO_ROOT / "config" / "rules_v1.yaml.sha256"


class FrozenConfigTampered(RuntimeError):
    """Raised when rules_v1.yaml no longer matches its recorded hash."""


def compute_hash(path: Path = RULES_PATH) -> str:
    """Return the SHA-256 hex digest of the frozen rules file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_frozen_rules(
    rules_path: Path = RULES_PATH, hash_path: Path = RULES_HASH_PATH
) -> str:
    """Verify rules_v1.yaml matches its recorded hash; return the digest.

    Raises:
        FrozenConfigTampered: if the file was edited after being frozen.
    """
    recorded = hash_path.read_text().strip()
    actual = compute_hash(rules_path)
    if actual != recorded:
        raise FrozenConfigTampered(
            f"config/rules_v1.yaml hash mismatch: recorded={recorded} actual={actual}. "
            "This file is FROZEN (SPEC_V1_FROZEN.md). Do not edit it; a real "
            "rules change requires a new spec version via explicit user decision."
        )
    return actual
