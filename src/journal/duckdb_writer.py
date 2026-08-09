"""DuckDB Journal writer (docs/INTERFACES.md Journal, db/schema.sql).

Append-only: no UPDATE/DELETE on research tables (CLAUDE.md). ``record()`` is the sole
write path -- it INSERTs whatever dict-shaped row the Orchestrator already built,
matching the schema's columns by name. ``table``/``row`` keys are always hardcoded at
Orchestrator call sites (never external input), but ``table`` is still checked against
the schema's real table set -- catches a typo as a loud error, not a silent no-op.
"""

from __future__ import annotations

from pathlib import Path

import duckdb

_KNOWN_TABLES = {
    "experiments", "runs", "portfolios", "sessions", "bias_history", "fvg_registry",
    "setups", "orders", "setup_arm_outcomes", "trades", "equity_curve", "news_events",
    "scores", "ai_annotations", "baseline_runs", "feature_registry", "trade_features",
    "context_snapshots",
}


class DuckDBJournal:
    """One instance per run; owns the DuckDB connection and applies db/schema.sql once."""

    def __init__(self, db_path: str | Path, schema_path: str | Path) -> None:
        """Open (or create) the DuckDB file at ``db_path`` and apply the schema."""
        self._con = duckdb.connect(str(db_path))
        self._con.execute(Path(schema_path).read_text(encoding="utf-8"))

    def record(self, table: str, row: dict) -> None:
        """Append one row to ``table``. Transactional per call (autocommit)."""
        if table not in _KNOWN_TABLES:
            raise ValueError(f"unknown Journal table {table!r} -- not in db/schema.sql")
        columns = list(row.keys())
        placeholders = ", ".join("?" for _ in columns)
        col_list = ", ".join(columns)
        self._con.execute(
            f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})",  # noqa: S608
            list(row.values()),
        )

    def query(self, sql: str, params: list | None = None) -> list[tuple]:
        """Read-only fetch (tests/inspection) -- never used by write paths."""
        return self._con.execute(sql, params or []).fetchall()

    def close(self) -> None:
        """Close the underlying DuckDB connection."""
        self._con.close()
