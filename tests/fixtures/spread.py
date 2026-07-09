from src.data.spread_report import HourSpreadStats, SpreadReport


def make_spread_report(median_by_hour: dict[int, float], symbol: str = "XAUUSD") -> SpreadReport:
    """A SpreadReport with directly-controlled median spread per ET hour, for RiskEngine tests."""
    by_hour = {
        hour: HourSpreadStats(
            hour_et=hour,
            tick_count=100,
            mean_spread=median,
            p25_spread=median,
            median_spread=median,
            p75_spread=median,
            p95_spread=median,
        )
        for hour, median in median_by_hour.items()
    }
    return SpreadReport(symbol=symbol, by_hour=by_hour)
