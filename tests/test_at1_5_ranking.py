"""AT-1.5 Ranking: Fixture with Displacement+BOS -> L3; §4 priority correctly picked among 3 FVGs.
"""

from datetime import UTC, datetime, timedelta

from src.core.types import FVG, TF
from src.displacement.d1_body import D1_DEFAULT_PARAMS, D1BodyRatio
from src.fvg.engine import FVGEngine
from src.fvg.ranking import sort_by_priority
from src.store.state_store import StateStore
from src.structure.engine import StructureEngine
from tests.fixtures.bars import make_bars

START = datetime(2024, 1, 1, tzinfo=UTC)
INTERVAL = timedelta(hours=4)


def test_at_1_5_displacement_and_bos_yields_level_3():
    quiet = [
        (100 + 0.1 * i, 100 + 0.1 * i + 0.3, 100 + 0.1 * i - 0.1, 100 + 0.1 * i + 0.2)
        for i in range(8)
    ]
    ohlc = [
        (100, 105, 99, 102),  # 0
        (102, 110, 101, 108),  # 1 candidate H=110
        (108, 106, 100, 103),  # 2 confirms H=110
        *quiet,  # 3..10 -- D1's trailing-average baseline (small bodies)
        (100.9, 101.2, 100.6, 101.0),  # 11 c1
        (101.0, 116, 100.5, 115),  # 12 c2: big body -> Displacement, closes 115>110 -> BOS
        (115, 120, 105, 118),  # 13 c3: low=105 > c1.high(101.2) -> bullish FVG
    ]
    bars = make_bars(TF.H4, START, INTERVAL, ohlc)

    store = StateStore()
    structure = StructureEngine(TF.H4, is_bias_source=True)
    fvg_engine = FVGEngine(
        TF.H4, displacement_model=D1BodyRatio(), displacement_params=D1_DEFAULT_PARAMS
    )

    formed = []
    for bar in bars:
        structure.step(bar, store)
        fvg = fvg_engine.step_bar_close(bar, store)
        if fvg is not None:
            formed.append(fvg)

    bull_fvgs = [f for f in formed if f.direction == "bull"]
    assert len(bull_fvgs) == 1
    fvg = bull_fvgs[0]
    assert fvg.displacement is True
    assert fvg.bos_link is not None
    assert fvg.level == 3


def _fvg(
    fvg_id: str, top: float, bottom: float, *, displacement: bool, bos_link: str | None
) -> FVG:
    ts = datetime(2024, 1, 1, tzinfo=UTC)
    return FVG(
        id=fvg_id,
        tf=TF.H4,
        direction="bull",
        top=top,
        bottom=bottom,
        level=1,
        created_at=ts,
        confirmed_at=ts,
        mitigation_pct=0.0,
        invalidated_at=None,
        bos_link=bos_link,
        displacement=displacement,
    )


def test_at_1_5_priority_bos_then_displacement_then_plain_then_proximity():
    plain_near = _fvg("plain-near", top=101, bottom=99, displacement=False, bos_link=None)
    disp_only = _fvg("disp-only", top=201, bottom=199, displacement=True, bos_link=None)
    bos_far = _fvg("bos-far", top=501, bottom=499, displacement=False, bos_link="SW-1")

    ranked = sort_by_priority([plain_near, disp_only, bos_far], current_price=100)

    assert [f.id for f in ranked] == ["bos-far", "disp-only", "plain-near"]


def test_at_1_5_priority_proximity_tiebreak_within_same_tier():
    near = _fvg("near", top=101, bottom=99, displacement=False, bos_link=None)
    far = _fvg("far", top=301, bottom=299, displacement=False, bos_link=None)

    ranked = sort_by_priority([far, near], current_price=100)

    assert [f.id for f in ranked] == ["near", "far"]
