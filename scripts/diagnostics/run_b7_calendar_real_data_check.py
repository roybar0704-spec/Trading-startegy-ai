#!/usr/bin/env python3
"""B-7 Commit 4 -- CalendarEngine real-data integration check (KI-010 Phase 1).

Read-only diagnostic -- NOT part of the production pipeline or the pytest suite. Proves
the real, unmodified CalendarEngine (src/session/calendar_engine.py) correctly consumes
real NewsEvent objects loaded (via src/data/news_loader.py, also unmodified here) from
the real, already-committed data/news/bls_calendar.csv (B-7 Commit 2) -- using the real,
FROZEN config/rules_v1.yaml::news_filter scope (not hardcoded duplicate values).

Does not modify CalendarEngine, NewsEvent, news_loader.py, rules_v1.yaml, db/schema.sql,
the CSV, or anything under data/holdout/ -- everything here is read-only.
"""

from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.config.models import load_rules_v1  # noqa: E402
from src.data.news_loader import load_bls_csv  # noqa: E402
from src.session.calendar_engine import CalendarEngine  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
CSV_PATH = REPO_ROOT / "data" / "news" / "bls_calendar.csv"


def main() -> int:
    print("Loading real, FROZEN config: config/rules_v1.yaml (unmodified)...")
    rules = load_rules_v1()
    nf = rules.news_filter
    print(f"  news_filter.currency = {nf.currency}")
    print(f"  news_filter.impact = {nf.impact}")
    print(
        f"  news_filter.blackout_min = before={nf.blackout_min.before}min "
        f"after={nf.blackout_min.after}min"
    )

    print(f"\nLoading real events via news_loader.load_bls_csv({CSV_PATH})...")
    events = load_bls_csv(CSV_PATH)
    print(f"Total NewsEvent loaded: {len(events)}")

    cpi_events = [e for e in events if e.title == "CPI"]
    nfp_events = [e for e in events if e.title == "Employment Situation"]
    print(f"CPI events: {len(cpi_events)}")
    print(f"Employment Situation events: {len(nfp_events)}")

    all_usd_red = all(e.currency == "USD" and e.impact == "red" for e in events)
    print(f"All events currency=USD, impact=red: {all_usd_red}")

    print("\n=== Sample real events (with UTC timestamp) ===")
    print(f"CPI sample: {cpi_events[0]}")
    print(f"NFP sample: {nfp_events[0]}")

    print("\nBuilding CalendarEngine.from_config(...) with the REAL rules_v1.yaml scope...")
    calendar = CalendarEngine.from_config(
        events=events,
        currencies=nf.currency,
        impacts=nf.impact,
        blackout_before_min=nf.blackout_min.before,
        blackout_after_min=nf.blackout_min.after,
    )
    print(
        f"CalendarEngine built with {len(calendar.events)} filtered events "
        f"(all {len(events)} real events already match currency=USD/impact=red)"
    )

    probe = cpi_events[0]
    print(f"\n=== Probing a real CPI event: {probe.title} at {probe.ts_utc.isoformat()} ===")

    inside_exact = calendar.in_blackout(probe.ts_utc)
    print(f"in_blackout(event time exactly): {inside_exact}")

    inside_before = calendar.in_blackout(probe.ts_utc - timedelta(minutes=15))
    print(f"in_blackout(15min before): {inside_before}")

    inside_after = calendar.in_blackout(probe.ts_utc + timedelta(minutes=15))
    print(f"in_blackout(15min after): {inside_after}")

    outside_before = calendar.in_blackout(probe.ts_utc - timedelta(minutes=45))
    print(f"in_blackout(45min before, outside the +/-30min window): {outside_before}")

    outside_after = calendar.in_blackout(probe.ts_utc + timedelta(minutes=45))
    print(f"in_blackout(45min after, outside the +/-30min window): {outside_after}")

    checks = {
        "66 events loaded": len(events) == 66,
        "33 CPI": len(cpi_events) == 33,
        "33 Employment Situation": len(nfp_events) == 33,
        "all USD/red": all_usd_red,
        "inside window (exact) is True": inside_exact is True,
        "inside window (-15min) is True": inside_before is True,
        "inside window (+15min) is True": inside_after is True,
        "outside window (-45min) is False": outside_before is False,
        "outside window (+45min) is False": outside_after is False,
    }
    print("\n=== Summary ===")
    for name, ok in checks.items():
        print(f"{name}: {'PASS' if ok else 'FAIL'}")

    print(
        "\nNote: this script never reads data/ticks/, data/holdout/, or any month "
        "outside the committed CSV -- Holdout is untouched by design."
    )
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
