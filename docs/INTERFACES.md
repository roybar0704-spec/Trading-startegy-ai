# INTERFACES — חוזי המודולים
חתימות מחייבות. שינוי חתימה = אישור משתמש. `dt` = datetime ב-UTC תמיד.

## טיפוסי ליבה
```python
class TF(Enum): M1="1M"; M5="5M"; H4="4H"

@dataclass(frozen=True)
class Tick:  ts: dt; bid: float; ask: float
    # mid = (bid+ask)/2  — מחיר המבנים

@dataclass(frozen=True)
class Bar:   tf: TF; open_ts: dt; close_ts: dt
             o: float; h: float; l: float; c: float   # Mid
             tick_volume: int

@dataclass(frozen=True)
class Swing: id: str; tf: TF; kind: Literal["H","L"]; price: float
             created_at: dt; confirmed_at: dt; taken_at: dt | None

@dataclass(frozen=True)
class FVG:   id: str; tf: TF; direction: Literal["bull","bear"]
             top: float; bottom: float; level: int          # 1..3
             created_at: dt; confirmed_at: dt
             mitigation_pct: float; invalidated_at: dt | None
             bos_link: str | None; displacement: bool

@dataclass
class Setup: id: str; direction: Literal["long","short"]; fvg_id: str
             state: SetupState; r_bar: Bar | None; s_bar: Bar | None
             ifvg: FVG | None; ts_flag: bool; score: float | None
             outcome: Outcome | None      # closed/expired/invalidated/
                                          # blocked_news/blocked_quota/
                                          # no_ifvg/invalid_geometry

@dataclass(frozen=True)
class OrderIntent: setup_id: str; arm: ArmId; side: Side
                   otype: Literal["limit","market"]; price: float | None
                   sl: float; tp: float; valid_until: dt

@dataclass(frozen=True)
class ArmId: entry: Literal["M1","M2","M4"]
             sl_anchor: Literal["R_body","S_body","S_wick"]
```

## Data Layer
```python
class DataProvider(Protocol):
    def get_ticks(self, symbol: str, start: dt, end: dt) -> pl.DataFrame
    def data_version(self) -> str

class BarBuilder(Protocol):
    def build(self, ticks: pl.DataFrame, tf: TF) -> list[Bar]   # anchor מוזרק בקונפיג
```

## Store
```python
class StateStore:                     # כתיבה: מנועי מבנה בלבד
    def put(self, obj) -> None
    def invalidate(self, obj_id: str, ts: dt) -> None
    def as_of(self, ts: dt) -> "MarketContext"

class MarketContext:                  # קריאה בלבד; confirmed_at <= now מובטח
    now: dt
    def bias(self) -> Literal["bullish","bearish","neutral"]
    def active_fvgs(self, tf: TF, direction: str) -> list[FVG]
    def confirmed_swings(self, tf: TF, since: dt) -> list[Swing]
    def in_window(self) -> bool
    def in_blackout(self) -> bool
    def median_spread(self, hour_et: int) -> float
```

## Structure / FVG / Displacement
```python
class StructureEngine(Protocol):      # מופע לכל TF
    def on_bar_close(self, bar: Bar, store: StateStore) -> None

class FVGEngine(Protocol):
    def on_bar_close(self, bar: Bar, store: StateStore) -> None
    def on_price(self, ts: dt, mid: float, store: StateStore) -> None  # mitigation

class DisplacementModel(Protocol):
    id: str                            # "D1".."D5"
    def evaluate(self, bars: Sequence[Bar], params: dict) -> bool
```

## Setup Stream (State Machine — model-agnostic)
```python
class SetupStream:
    def step(self, ctx: MarketContext) -> list[SetupEvent]
    # SetupEvent ∈ {Engaged, ReactionSeen, SweepConfirmed, Armed(ifvg),
    #               Invalidated(reason), Expired, NoIFVG}
```

## Entry / Risk / Execution
```python
class EntryModel(Protocol):
    id: Literal["M1","M2","M4"]
    def on_event(self, ev: SetupEvent, ctx: MarketContext) -> OrderIntent | None
    def on_bar_close_1m(self, bar: Bar, ctx: MarketContext) -> OrderIntent | None  # M4

class RiskEngine(Protocol):           # מופע לכל תיק/זרוע
    def approve(self, intent: OrderIntent, ctx: MarketContext) -> Order | Rejection

class CostModel(Protocol):
    def stop_slippage(self, ts: dt, in_news: bool) -> float
    def market_slippage(self, ts: dt) -> float
    def commission(self, units: float) -> float

class FillSimulator(Protocol):
    def place(self, order: Order, portfolio: PortfolioId) -> None
    def cancel(self, order_id: str, reason: str) -> None
    def on_tick(self, tick: Tick) -> list[Fill]
    def on_bar_1m(self, bar: Bar) -> list[Fill]        # fallback: SL-First
```

## Orchestrator / Journal / Validation / Tracker
```python
class Orchestrator:
    def run(self, cfg: RunConfig) -> RunResult
    # לולאה דו-שלבית; מחזיקה 9 תיקים; כותבת ליומן בלבד

class Journal(Protocol):
    def record(self, table: str, row: dict) -> None    # טרנזקציוני, append-only

class Validation(Protocol):
    def walk_forward(self, cfg) -> list[Split]
    def random_baseline(self, arm: ArmId, n: int, seed: int) -> BaselineDist
    def sensitivity(self, cfg, pct: float) -> SensReport

class ExperimentTracker(Protocol):
    def register_run(self, cfg_hash: str, data_ver: str, code_ver: str,
                     objective: str) -> RunId          # objective שונה מהמוצהר → חריגה
```

## AI Analyst (Read-Only)
```python
class Analyst(Protocol):
    def pre_session(self, snapshot: ContextSnapshot) -> AnalystReport   # JSON מובנה
    def tag_trade(self, trade: Trade, snapshot: ContextSnapshot) -> list[FeatureTag]
```
