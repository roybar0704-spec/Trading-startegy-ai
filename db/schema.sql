-- XAUUSD Research Platform — DuckDB Schema v1
-- כל הזמנים UTC (TIMESTAMPTZ). Append-Only: אין UPDATE/DELETE על טבלאות מחקר.

CREATE TABLE IF NOT EXISTS experiments (
    experiment_id   TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    hypothesis      TEXT NOT NULL,
    objective_fn    TEXT NOT NULL,          -- נעול לפני ריצה ראשונה
    declared_grid   JSON NOT NULL,          -- הזרועות/פרמטרים המוצהרים מראש
    holdout_range   JSON NOT NULL,          -- {start,end} — נגיעה אחת
    created_at      TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    run_id          TEXT PRIMARY KEY,
    experiment_id   TEXT NOT NULL REFERENCES experiments(experiment_id),
    config_hash     TEXT NOT NULL,          -- SHA256(config+data_ver+code_ver)
    code_version    TEXT NOT NULL,          -- git sha
    data_version    TEXT NOT NULL,
    period_start    DATE NOT NULL,
    period_end      DATE NOT NULL,
    split_type      TEXT NOT NULL,          -- in_sample | wf_train | wf_test | holdout
    seed            BIGINT,                 -- NULL = engine run (RNG-free, D-067); NOT NULL = baseline run (Phase 5)
    created_at      TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS portfolios (                   -- זרוע = תיק מבודד
    portfolio_id    TEXT PRIMARY KEY,
    run_id          TEXT NOT NULL REFERENCES runs(run_id),
    entry_model     TEXT NOT NULL CHECK (entry_model IN ('M1','M2','M4')),
    sl_anchor       TEXT NOT NULL CHECK (sl_anchor IN ('R_body','S_body','S_wick')),
    initial_equity  DOUBLE NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (                     -- שורה ליום מסחר
    run_id          TEXT NOT NULL,
    ny_date         DATE NOT NULL,
    effective_window_minutes  INTEGER NOT NULL,
    thin_liquidity  BOOLEAN NOT NULL DEFAULT FALSE,
    news_blackouts  JSON,                   -- [{start,end,title}]
    PRIMARY KEY (run_id, ny_date)
);

CREATE TABLE IF NOT EXISTS bias_history (
    run_id      TEXT NOT NULL,
    ts          TIMESTAMPTZ NOT NULL,
    state       TEXT NOT NULL CHECK (state IN ('bullish','bearish','neutral')),
    trigger_bos JSON,
    PRIMARY KEY (run_id, ts)
);

CREATE TABLE IF NOT EXISTS fvg_registry (
    fvg_id        TEXT PRIMARY KEY,
    run_id        TEXT NOT NULL,
    tf            TEXT NOT NULL,
    direction     TEXT NOT NULL CHECK (direction IN ('bull','bear')),
    top           DOUBLE NOT NULL,
    bottom        DOUBLE NOT NULL,
    level         INTEGER NOT NULL CHECK (level IN (1,2,3)),
    displacement  BOOLEAN NOT NULL,
    bos_link      TEXT,
    created_at    TIMESTAMPTZ NOT NULL,
    confirmed_at  TIMESTAMPTZ NOT NULL,
    max_mitigation_pct DOUBLE NOT NULL DEFAULT 0,
    invalidated_at TIMESTAMPTZ
);

-- Setup = ישות מחקרית model-agnostic בלבד (D-052). outcome מכיל אך ורק את ארבעת
-- הערכים שאינם תלויי-תיק (הזהים ל-9 התיקים) -- ר' SPEC_V1_FROZEN.md §14.
-- תוצאה תלויית-תיק (closed/blocked_news/blocked_quota/invalid_geometry) חייבת
-- להישמר ב-setup_arm_outcomes בלבד; לעולם לא כאן.
CREATE TABLE IF NOT EXISTS setups (
    setup_id      TEXT PRIMARY KEY,
    run_id        TEXT NOT NULL,
    direction     TEXT NOT NULL CHECK (direction IN ('long','short')),
    fvg_id        TEXT NOT NULL,
    engagement_ts TIMESTAMPTZ NOT NULL,
    r_bar         JSON,                     -- {open_ts,o,h,l,c}
    s_bar         JSON,
    ifvg          JSON,                     -- {top,bottom,inversion_ts}
    ts_flag       BOOLEAN NOT NULL DEFAULT FALSE,
    same_zone_reentry BOOLEAN NOT NULL DEFAULT FALSE,
    score         DOUBLE,
    outcome       TEXT NOT NULL CHECK (outcome IN
                    ('armed','expired','invalidated','no_ifvg')),
    outcome_reason TEXT,
    state_log     JSON NOT NULL             -- [{state,ts,reason}] — מעברי ה-FSM המשותפים בלבד
);

CREATE TABLE IF NOT EXISTS orders (
    order_id      TEXT PRIMARY KEY,
    setup_id      TEXT NOT NULL REFERENCES setups(setup_id),
    portfolio_id  TEXT NOT NULL REFERENCES portfolios(portfolio_id),
    otype         TEXT NOT NULL CHECK (otype IN ('limit','market')),
    side          TEXT NOT NULL CHECK (side IN ('buy','sell')),
    price         DOUBLE,
    sl            DOUBLE NOT NULL,
    tp            DOUBLE NOT NULL,
    units         DOUBLE NOT NULL,
    placed_at     TIMESTAMPTZ NOT NULL,
    valid_until   TIMESTAMPTZ NOT NULL,
    status        TEXT NOT NULL CHECK (status IN ('pending','filled','cancelled')),
    filled_at     TIMESTAMPTZ,
    fill_price    DOUBLE,
    cancel_reason TEXT
);

-- תוצאה פר-(Setup, תיק) -- D-052. שורה נוצרת עבור כל אחד מ-9 התיקים ברגע שהתיק
-- הזה מגיע לתוצאה סופית משלו (ARMED כשלעצמו אינו כותב שורה כאן -- ר' D-060).
-- תיק אחד יכול לקבל blocked_quota בעוד תיק אחר על אותו Setup בדיוק ממשיך רגיל --
-- זו בדיוק הנקודה: 9 התיקים עצמאיים לחלוטין, גם כשה-Setup הבסיסי זהה.
-- D-060 (Append-Only, ללא UPDATE): "pending" מוצהר ב-CHECK אך **לא נכתב בפועל**
-- כשורת-ביניים -- שורה אחת בלבד נכתבת פר-(setup_id,portfolio_id), ברגע שהתוצאה
-- כבר סופית (closed/expired/invalidated/blocked_news/blocked_quota/
-- invalid_geometry). פוזיציה שעדיין פתוחה בתום הריצה (Overnight מותר) לא
-- מקבלת שורה כלל -- ר' KI-019. הכרעה עתידית ל-Event Log אמיתי (PK מגורסן)
-- תישאר v2+ אם תידרש (ר' DECISIONS_LOG D-060).
CREATE TABLE IF NOT EXISTS setup_arm_outcomes (
    setup_id      TEXT NOT NULL REFERENCES setups(setup_id),
    portfolio_id  TEXT NOT NULL REFERENCES portfolios(portfolio_id),
    outcome       TEXT NOT NULL CHECK (outcome IN
                    ('pending','closed','expired','invalidated',
                     'blocked_news','blocked_quota','invalid_geometry')),
    outcome_reason TEXT,
    order_id      TEXT REFERENCES orders(order_id),   -- NULL אם נדחה לפני שנוצרה פקודה בכלל (RiskEngine Rejection)
    state_log     JSON NOT NULL,            -- [{state,ts,reason}] -- מעברי התיק הזה בלבד, מ-ARMED ואילך
    PRIMARY KEY (setup_id, portfolio_id)
);

CREATE TABLE IF NOT EXISTS trades (
    trade_id      TEXT PRIMARY KEY,
    order_id      TEXT NOT NULL REFERENCES orders(order_id),
    portfolio_id  TEXT NOT NULL,
    entry_ts      TIMESTAMPTZ NOT NULL,
    exit_ts       TIMESTAMPTZ,
    entry_px      DOUBLE NOT NULL,
    exit_px       DOUBLE,
    sl_px         DOUBLE NOT NULL,
    tp_px         DOUBLE NOT NULL,
    exit_kind     TEXT CHECK (exit_kind IN ('tp','sl','gap_through_sl')),
    result_r      DOUBLE,
    mae_r         DOUBLE,
    mfe_r         DOUBLE,
    duration_min  INTEGER,
    cost_spread   DOUBLE NOT NULL,
    cost_slippage DOUBLE NOT NULL,
    cost_commission DOUBLE NOT NULL,
    tag_overnight BOOLEAN NOT NULL DEFAULT FALSE,
    tag_weekend   BOOLEAN NOT NULL DEFAULT FALSE,
    tag_news_cross BOOLEAN NOT NULL DEFAULT FALSE,
    tag_concurrent BOOLEAN NOT NULL DEFAULT FALSE,
    tag_bias_flip  BOOLEAN NOT NULL DEFAULT FALSE,
    hour_bucket_et INTEGER
);

CREATE TABLE IF NOT EXISTS equity_curve (
    portfolio_id  TEXT NOT NULL,
    ts            TIMESTAMPTZ NOT NULL,
    balance_r     DOUBLE NOT NULL,          -- ממומש, ב-R מצטבר
    open_risk_r   DOUBLE NOT NULL,
    PRIMARY KEY (portfolio_id, ts)
);

CREATE TABLE IF NOT EXISTS news_events (
    ts_utc      TIMESTAMPTZ NOT NULL,
    currency    TEXT NOT NULL,
    impact      TEXT NOT NULL,
    title       TEXT NOT NULL,
    source      TEXT NOT NULL,
    PRIMARY KEY (ts_utc, title)
);

CREATE TABLE IF NOT EXISTS scores (
    setup_id    TEXT PRIMARY KEY REFERENCES setups(setup_id),
    components  JSON NOT NULL,              -- {fvg_level, ts, sweep_quality, bias_recency}
    total       DOUBLE NOT NULL
);

CREATE TABLE IF NOT EXISTS ai_annotations (
    annotation_id TEXT PRIMARY KEY,
    ref_kind      TEXT NOT NULL CHECK (ref_kind IN ('setup','trade','session')),
    ref_id        TEXT NOT NULL,
    kind          TEXT NOT NULL,            -- pre_session | feature_tag | insight
    content       JSON NOT NULL,
    model_version TEXT NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS baseline_runs (
    baseline_id   TEXT PRIMARY KEY,
    run_id        TEXT NOT NULL,
    portfolio_arm JSON NOT NULL,            -- {entry_model, sl_anchor}
    n_sims        INTEGER NOT NULL,
    seed          BIGINT NOT NULL,
    expectancy_dist JSON NOT NULL,          -- percentiles
    strategy_p_value DOUBLE
);

-- ============ Feature Store (D-028) ============

CREATE TABLE IF NOT EXISTS feature_registry (
    feature       TEXT PRIMARY KEY,
    dtype         TEXT NOT NULL CHECK (dtype IN ('num','text')),
    definition    TEXT NOT NULL,
    source        TEXT NOT NULL,            -- extractor module
    version       INTEGER NOT NULL DEFAULT 1,
    status        TEXT NOT NULL CHECK (status IN ('approved','proposed')),
    added_at      TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS trade_features (               -- EAV: הרחבה ללא מיגרציות
    trade_id      TEXT NOT NULL REFERENCES trades(trade_id),
    feature       TEXT NOT NULL REFERENCES feature_registry(feature),
    value_num     DOUBLE,
    value_text    TEXT,
    extractor_version INTEGER NOT NULL,
    computed_at   TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (trade_id, feature)
);

CREATE TABLE IF NOT EXISTS context_snapshots (            -- נקודתי-בזמן: confirmed_at <= ts בלבד
    snapshot_id   TEXT PRIMARY KEY,
    setup_id      TEXT NOT NULL REFERENCES setups(setup_id),
    -- D-058: engagement/armed הם model-agnostic (order_id=NULL, שורה אחת לכל Setup,
    -- זהה ל-9 התיקים). entry/exit הם פר-תיק (order_id חובה, שורה אחת לכל Order) --
    -- אותו עיקרון בדיוק כמו setup_arm_outcomes (D-052).
    order_id      TEXT REFERENCES orders(order_id),
    kind          TEXT NOT NULL CHECK (kind IN ('engagement','armed','entry','exit')),
    ts            TIMESTAMPTZ NOT NULL,
    payload       JSON NOT NULL
);

-- תצוגה רחבה לאנליטיקה נבנית ב-Runtime:
-- CREATE VIEW v_trades_wide AS PIVOT trade_features ON feature USING first(coalesce(value_text, CAST(value_num AS TEXT)));
