"""T3.3-prep: config loader (Pydantic v2, extra=forbid) + config_hash determinism."""

import pytest
from pydantic import ValidationError

from src.config.models import (
    Parameters,
    RulesV1,
    config_hash,
    load_parameters,
    load_rules_v1,
    load_run_config,
)


def test_real_config_files_load_cleanly():
    rules = load_rules_v1()
    params = load_parameters()
    run_cfg = load_run_config()
    assert rules.instrument == "XAUUSD"
    assert params.warmup_days == 90
    assert run_cfg.arms.entry_models == ("M1", "M2", "M4")


def test_unknown_field_is_a_hard_error_not_silent_ignore():
    rules = load_rules_v1()
    payload = rules.model_dump(mode="json")
    payload["unexpected_field"] = "typo"
    with pytest.raises(ValidationError):
        RulesV1.model_validate(payload)


def test_missing_required_field_is_a_hard_error():
    params = load_parameters()
    payload = params.model_dump(mode="json")
    del payload["warmup_days"]
    with pytest.raises(ValidationError):
        Parameters.model_validate(payload)


def test_config_hash_deterministic_and_sensitive_to_input():
    rules = load_rules_v1()
    params = load_parameters()
    run_cfg = load_run_config()
    h1 = config_hash(rules, params, run_cfg, data_version="v1", code_version="abc")
    h2 = config_hash(rules, params, run_cfg, data_version="v1", code_version="abc")
    assert h1 == h2
    h3 = config_hash(rules, params, run_cfg, data_version="v2", code_version="abc")
    assert h1 != h3
