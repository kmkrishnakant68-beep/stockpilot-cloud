#!/usr/bin/env python3
"""StockPilot moving-average tracker.

Fetch Yahoo Finance daily prices, use an indicative intraday quote during
regular US market hours when available, and flag stocks falling below their
50-day or 200-day simple moving averages (SMA).

Output: latest_signals.csv, latest_signals.json, alerts.csv, state.json.
Requires: pip install -r requirements.txt
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import time
from datetime import datetime, time as dtime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf

EASTERN = ZoneInfo("America/New_York")
ROOT = Path(__file__).resolve().parent
DEFAULT_TICKERS = ["MSFT", "GOOGL", "NVDA", "AMD", "META", "AVGO", "VOO", "SMH"]


def load_symbols(raw: list[str] | None, watchlist: Path) -> list[str]:
    if raw:
        values = raw
    elif watchlist.exists():
        values = watchlist.read_text(encoding="utf-8").splitlines()
    else:
        values = DEFAULT_TICKERS
    result = []
    for item in values:
        for part in item.split(","):
            sym = part.strip().upper()
            if sym and not sym.startswith("#") and sym not in result:
                result.append(sym)
    if not result:
        raise ValueError("No symbols found. Supply --tickers or a watchlist file.")
    return result


def safe_float(value: object) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) and number > 0 else None
    except (TypeError, ValueError):
        return None


def get_quote(ticker: yf.Ticker) -> float | None:
    try:
        return safe_float(ticker.fast_info["last_price"])
    except Exception:
        return None


def is_us_regular_session(now: datetime) -> bool:
    et = now.astimezone(EASTERN)
    return et.weekday() < 5 and dtime(9, 30) <= et.time() < dtime(16, 0)


def moving_average_result(
    symbol: str,
    history: pd.DataFrame,
    indicative_quote: float | None,
    now: datetime,
    prior: dict | None = None,
) -> dict:
    """Compute SMAs; detect a crossing since last sample or last completed bar."""
    if history.empty or "Close" not in history:
        raise ValueError("No daily price history returned")

    closes = pd.to_numeric(history["Close"], errors="coerce").dropna()
    closes = closes[closes > 0]
    if len(closes) < 51:
        raise ValueError(f"Only {len(closes)} daily closes; need at least 51")

    history_day = pd.Timestamp(closes.index[-1]).date()
    current_day = now.astimezone(EASTERN).date()
    mode = "completed daily close"

    # The current trading day's bar, when present, may still be incomplete.
    # During the session, append exactly ONE provisional value rather than
    # counting today's in-progress daily bar twice.
    if is_us_regular_session(now) and indicative_quote is not None:
        completed = closes.iloc[:-1] if history_day == current_day else closes
        closes = pd.concat([
            completed.reset_index(drop=True),
            pd.Series([indicative_quote], dtype=float),
        ], ignore_index=True)
        bar_day = str(current_day)
        mode = "indicative session quote (may be delayed)"
    else:
        closes = closes.reset_index(drop=True)
        bar_day = str(history_day)

    latest_price = float(closes.iloc[-1])
    result = {
        "ticker": symbol,
        "as_of_date": bar_day,
        "checked_at_utc": now.astimezone(timezone.utc).isoformat(timespec="seconds"),
        "price_mode": mode,
        "price": round(latest_price, 4),
        "status": "ok",
        "trend30": [round(float(v), 4) for v in closes.tail(30).tolist()],
    }
    for window in (50, 200):
        average = closes.rolling(window=window, min_periods=window).mean()
        level = safe_float(average.iloc[-1])
        previous_level = safe_float(average.iloc[-2]) if len(average) > 1 else None
        prior_status = (prior or {}).get(f"below{window}")

        is_below = latest_price < level if level is not None else None
        previously_below = (
            prior_status if isinstance(prior_status, bool) else
            (float(closes.iloc[-2]) < previous_level if previous_level is not None else None)
        )
        crossed = is_below is True and previously_below is False

        result[f"ma{window}"] = round(level, 4) if level is not None else None
        result[f"distance{window}_pct"] = (
            round((latest_price / level - 1) * 100, 2)
            if level is not None else None
        )
        result[f"below{window}"] = is_below
        result[f"crossed_below{window}"] = crossed
        result[f"signal{window}"] = (
            "INSUFFICIENT HISTORY" if is_below is None else
            "CROSSED BELOW" if crossed else
            "BELOW" if is_below else "AT / ABOVE"
        )
    return result


def fetch_and_analyze(symbol: str, now: datetime, prior: dict | None) -> dict:
    stock = yf.Ticker(symbol)
    history = stock.history(period="2y", interval="1d", auto_adjust=False,
                            actions=False, timeout=15)
    # Using unadjusted Close (split-adjusted by Yahoo) makes the SMA comparable
    # with an unadjusted last_price quote, especially around dividends.
    quote = get_quote(stock) if is_us_regular_session(now) else None
    return moving_average_result(symbol, history, quote, now, prior)


def load_state(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, indent=2, allow_nan=False), encoding="utf-8")
    temp.replace(path)


def run_once(symbols: list[str], output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    state_path = output / "state.json"
    state = load_state(state_path)
    now = datetime.now(timezone.utc)
    results = []
    alerts = []

    for symbol in symbols:
        try:
            record = fetch_and_analyze(symbol, now, state.get(symbol))
            state[symbol] = {"below50": record["below50"],
                             "below200": record["below200"]}
            for window in (50, 200):
                if record[f"crossed_below{window}"]:
                    alerts.append({
                        "checked_at_utc": record["checked_at_utc"],
                        "ticker": symbol,
                        "event": f"CROSSED BELOW {window}D SMA",
                        "price": record["price"],
                        "moving_average": record[f"ma{window}"],
                        "price_mode": record["price_mode"],
                    })
        except Exception as exc:
            record = {"ticker": symbol, "status": f"ERROR: {exc}"}
        results.append(record)

    if not any(r.get("status") == "ok" for r in results):
        raise RuntimeError("No price histories could be fetched. Preserving previously published data; check Yahoo Finance availability and rate limits.")

    columns = ["ticker", "as_of_date", "price", "ma50", "ma200",
               "distance50_pct", "distance200_pct", "signal50", "signal200",
               "below50", "below200", "crossed_below50", "crossed_below200",
               "price_mode", "checked_at_utc", "status"]
    pd.DataFrame(results).reindex(columns=columns).to_csv(
        output / "latest_signals.csv", index=False)
    save_json(output / "latest_signals.json", {
        "generated_at_utc": now.isoformat(timespec="seconds"),
        "provider": "Yahoo Finance via yfinance (quotes may be delayed)",
        "stocks": results,
    })
    save_json(state_path, state)

    save_json(output / "new_alerts.json", {"generated_at_utc": now.isoformat(timespec="seconds"), "alerts": alerts})

    alert_file = output / "alerts.csv"
    if alerts:
        with alert_file.open("a", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=list(alerts[0]))
            if file.tell() == 0:
                writer.writeheader()
            writer.writerows(alerts)

    alert_history = []
    if alert_file.exists():
        with alert_file.open(newline="", encoding="utf-8") as f:
            alert_history = list(csv.DictReader(f))[-100:]
    save_json(output / "alert_history.json", {"alerts": alert_history[::-1]})

    view = pd.DataFrame(results).reindex(columns=[
        "ticker", "price", "ma50", "ma200", "signal50", "signal200", "status"])
    print(f"\nStockPilot scan | {now.isoformat(timespec='seconds')} | {len(symbols)} ticker(s)")
    print(view.to_string(index=False, na_rep="—"))
    for alert in alerts:
        print(f"ALERT: {alert['ticker']} {alert['event']} "
              f"at ${alert['price']:.2f} (SMA ${alert['moving_average']:.2f})")
    if not alerts:
        print("No new downward crosses detected this scan.")
    print(f"Saved results in: {output.resolve()}")


def main() -> None:
    parser = argparse.ArgumentParser(description="StockPilot 50/200-day moving average tracker")
    parser.add_argument("--tickers", nargs="+", help="Tickers separated by spaces or commas")
    parser.add_argument("--watchlist", type=Path, default=ROOT / "watchlist.txt")
    parser.add_argument("--output", type=Path, default=ROOT / "stockpilot_data")
    parser.add_argument("--poll-minutes", type=int, default=0,
                        help="Repeat every N minutes (0 = single scan; N >= 5)")
    args = parser.parse_args()
    if args.poll_minutes != 0 and args.poll_minutes < 5:
        parser.error("--poll-minutes must be 0 or >= 5 to avoid excessive requests")
    symbols = load_symbols(args.tickers, args.watchlist)
    try:
        while True:
            run_once(symbols, args.output)
            if args.poll_minutes == 0:
                break
            time.sleep(args.poll_minutes * 60)
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
