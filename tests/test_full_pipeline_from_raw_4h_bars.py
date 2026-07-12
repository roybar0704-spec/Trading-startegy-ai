"""KI-020 (Critical Review): the real production pipeline, driven from raw 4H bars
all the way to a Journal-recorded trade -- with NO seeding anywhere.

Raw 4H bars -> StructureEngine (real BOS -> Bias) -> FVGEngine (real 3-candle FVG
detection) -> SetupStream (Engagement -> R -> S -> iFVG -> Armed) -> M2 Entry
Model -> RiskEngine -> FillSimulator -> Journal.

Every other Orchestrator test in this project (including the ones added earlier
in this same review) seeds FVG/Bias directly via `store.put(...)`, bypassing
`_apply_4h`/StructureEngine/FVGEngine entirely. This is the one exception: the
4H bars below are fed to `build_orchestrator` exactly as raw market data would
be, and every downstream fact (the Bias flip, the FVG's top/bottom, the Setup,
the fill, the trade) is a genuine consequence of the engines processing them --
never asserted into existence.
"""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from src.backtest.run_builder import build_orchestrator
from src.config.models import load_parameters, load_rules_v1, load_run_config
from src.core.types import TF, Bar, Tick
from src.journal.duckdb_writer import DuckDBJournal
from tests.fixtures.orchestrator import make_identity, warmup_ticks
from tests.fixtures.setup_stream import m1, m5

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "db" / "schema.sql"

START = datetime(2024, 1, 1, tzinfo=UTC)
INTERVAL = timedelta(hours=4)


def _m4h(open_ts, o, h, low, c) -> Bar:
    return Bar(
        tf=TF.H4, open_ts=open_ts, close_ts=open_ts + INTERVAL,
        o=o, h=h, l=low, c=c, tick_volume=1,
    )


def _raw_4h_bars() -> list[Bar]:
    """A real BOS-up sequence (bars 0-3, same shape proven in AT-1.3) continued by
    a real 3-candle bull FVG (bars 4-6, same shape proven in AT-1.4) -- both
    processed by the actual StructureEngine/FVGEngine, not hand-placed.
    """
    return [
        _m4h(START + 0 * INTERVAL, 100, 105, 99, 102),
        _m4h(START + 1 * INTERVAL, 102, 110, 101, 108),   # candidate H=110
        _m4h(START + 2 * INTERVAL, 108, 106, 100, 103),   # confirms H=110
        _m4h(START + 3 * INTERVAL, 103, 115, 102, 112),   # BOS up (112>110) -> bullish
        _m4h(START + 4 * INTERVAL, 112, 116, 108, 113),   # FVG c1, h=116
        _m4h(START + 5 * INTERVAL, 113, 150, 110, 140),   # FVG c2, displacement candle
        _m4h(START + 6 * INTERVAL, 140, 145, 128, 135),   # FVG c3, l=128 -> bull FVG [116,128]
    ]


def _scenario(journal=None, registry_path=None):
    rules, params, run_cfg = load_rules_v1(), load_parameters(), load_run_config()
    # Tiny geometry threshold -- real geometry is covered elsewhere (test_at2_6);
    # the point of this test is the wiring from raw bars to a Journal-recorded trade.
    params = params.model_copy(
        update={
            "min_stop_k_spread": params.min_stop_k_spread.model_copy(update={"default": 0.01}),
            "sl_buffer_usd": params.sl_buffer_usd.model_copy(update={"default": 0.05}),
        }
    )
    bars_4h = _raw_4h_bars()

    in_window = datetime(2024, 1, 2, 14, 0, tzinfo=UTC)  # 09:00 ET, the day after the FVG forms
    r_ts = in_window + timedelta(minutes=5)
    s_ts = in_window + timedelta(minutes=10)
    base = in_window + timedelta(minutes=20)
    bars_1m = [
        m1(in_window, 120.5, 120.6, 119.5, 120.2),          # engages FVG [116,128] (low<=128)
        m1(base, 117.5, 117.6, 117.0, 117.3),
        m1(base + timedelta(minutes=1), 117.2, 117.3, 116.8, 117.0),
        m1(base + timedelta(minutes=2), 116.4, 116.5, 116.2, 116.3),
        m1(base + timedelta(minutes=3), 116.8, 117.3, 116.7, 117.2),  # inversion, closes 117.2
    ]
    bars_5m = [
        m5(r_ts, 119.0, 119.8, 117.0, 119.5),   # R: pool (low) = 117.0
        m5(s_ts, 118.0, 118.5, 116.0, 117.5),   # S: low 116.0 < pool, close 117.5 > pool
    ]
    inversion_ts = bars_1m[-1].close_ts
    ticks = [
        Tick(ts=inversion_ts + timedelta(seconds=1), bid=117.15, ask=117.25),  # entry fill
        Tick(ts=inversion_ts + timedelta(minutes=5), bid=121.0, ask=121.1),  # TP exit
    ]

    orch = build_orchestrator(
        rules, params, run_cfg, identity=make_identity(ticks), bars_1m=bars_1m, bars_5m=bars_5m,
        bars_4h=bars_4h, ticks=ticks,
        spread_warmup_ticks=warmup_ticks({h: 0.01 for h in range(24)}), journal=journal,
        registry_path=registry_path,
    )
    # Deliberately no orch.store.put(...) anywhere -- this is the entire point.
    return orch


def test_bias_and_fvg_are_genuinely_detected_not_seeded():
    orch = _scenario()
    orch.run()
    last_4h_ts = orch.bars_4h[-1].close_ts

    assert orch.store.as_of(last_4h_ts).bias() == "bullish"
    fvgs = orch.store.all_fvgs()
    assert any(f.direction == "bull" and f.top == 128 and f.bottom == 116 for f in fvgs)


def test_full_pipeline_from_raw_4h_bars_reaches_a_real_fill():
    orch = _scenario()
    result = orch.run()

    assert result.engaged == 1
    assert result.reaction_seen == 1
    assert result.sweep_confirmed == 1
    assert result.armed == 1
    assert result.fills == 2  # entry + TP exit

    [filled_arm] = [a for a in orch.arms if a.portfolio.realized_equity != 10_000.0]
    assert filled_arm.arm_id.entry == "M2"
    assert filled_arm.arm_id.sl_anchor == "S_wick"
    assert filled_arm.portfolio.realized_equity > 10_000.0  # TP hit, not SL


def test_full_pipeline_writes_a_consistent_journal(tmp_path):
    db_path = tmp_path / "test.duckdb"
    registry_path = tmp_path / "runs.jsonl"
    journal = DuckDBJournal(db_path, SCHEMA_PATH)
    orch = _scenario(journal=journal, registry_path=registry_path)
    orch.run()  # closes `journal`

    reader = DuckDBJournal(db_path, SCHEMA_PATH)
    [(setup_id, fvg_id, outcome)] = reader.query("SELECT setup_id, fvg_id, outcome FROM setups")
    assert outcome == "armed"

    # B-1/D-067: runs row carries real identity, not the pre-B-1 "unknown"/0 placeholders.
    [(config_hash, code_version, data_version, split_type, seed)] = reader.query(
        "SELECT config_hash, code_version, data_version, split_type, seed FROM runs"
    )
    assert "unknown" not in (config_hash, code_version, data_version, split_type)
    assert seed is None
    assert registry_path.exists()
    registry_lines = registry_path.read_text().strip().splitlines()
    assert len(registry_lines) == 1
    record = json.loads(registry_lines[0])
    assert record["config_hash"] == config_hash
    assert record["seed"] is None

    [(trade_id,)] = reader.query("SELECT trade_id FROM trades")
    [(exit_kind, result_r)] = reader.query(
        "SELECT exit_kind, result_r FROM trades WHERE trade_id = ?", [trade_id]
    )
    assert exit_kind == "tp"
    assert result_r > 0

    snapshot_kinds = [k for (k,) in reader.query(
        "SELECT kind FROM context_snapshots WHERE setup_id = ? ORDER BY ts", [setup_id]
    )]
    assert snapshot_kinds == ["engagement", "armed", "entry", "exit"]

    armed_payload = json.loads(
        reader.query(
            "SELECT payload FROM context_snapshots WHERE setup_id = ? AND kind = 'armed'",
            [setup_id],
        )[0][0]
    )
    assert armed_payload["fvg"]["top"] == 128
    assert armed_payload["fvg"]["bottom"] == 116
    reader.close()
