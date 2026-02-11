import csv
import os
from pathlib import Path
from typing import Dict, List, Optional

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

HOLDINGS_CSV = DATA_DIR / "holdings.csv"
MOMENTUM_CSV = DATA_DIR / "momentum.csv"
PORTFOLIO_CSV = DATA_DIR / "portfolio.csv"
OHLC_CSV = DATA_DIR / "ohlc_history.csv"

HOLDINGS_HEADER = ["date", "ticker", "group", "qty", "price", "value", "exchange"]
MOMENTUM_HEADER = ["date", "strategy", "group", "score", "r1m", "r3m", "r6m", "r12m"]
PORTFOLIO_HEADER = ["date", "total_equity", "cash", "strategy", "group", "target_weight", "selected_ticker"]
OHLC_HEADER = ["ticker", "date", "close"]


def _ensure_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _append_rows(path: Path, header: List[str], rows: List[List]) -> None:
    _ensure_dir()
    write_header = not path.exists() or path.stat().st_size == 0
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(header)
        writer.writerows(rows)


def save_holdings(
    date: str,
    holdings_detail: Dict[str, Dict],
    prices: Dict[str, float],
    group_for_ticker_fn,
) -> None:
    rows = []
    for ticker, info in sorted(holdings_detail.items()):
        qty = info.get("qty", 0)
        price = prices.get(ticker) or info.get("price") or 0.0
        value = round(price * qty, 2)
        group = group_for_ticker_fn(ticker)
        exchange = info.get("excg", "")
        rows.append([date, ticker, group, qty, f"{price:.2f}", f"{value:.2f}", exchange])
    if rows:
        _append_rows(HOLDINGS_CSV, HOLDINGS_HEADER, rows)


def save_momentum(
    date: str,
    strategy_name: str,
    scores: Dict[str, Optional[float]],
    returns: Dict[str, Dict[str, Optional[float]]],
) -> None:
    rows = []
    for group in sorted(scores.keys()):
        score = scores[group]
        ret = returns.get(group, {})
        rows.append([
            date,
            strategy_name,
            group,
            f"{score:.4f}" if score is not None else "",
            f"{ret.get('r1m', 0.0):.4f}" if ret.get("r1m") is not None else "",
            f"{ret.get('r3m', 0.0):.4f}" if ret.get("r3m") is not None else "",
            f"{ret.get('r6m', 0.0):.4f}" if ret.get("r6m") is not None else "",
            f"{ret.get('r12m', 0.0):.4f}" if ret.get("r12m") is not None else "",
        ])
    if rows:
        _append_rows(MOMENTUM_CSV, MOMENTUM_HEADER, rows)


def save_portfolio(
    date: str,
    total_equity: float,
    cash: float,
    strategy_results: List[Dict],
    merged_targets: Dict[str, float],
    selected_tickers: Dict[str, str],
) -> None:
    rows = []
    for data in strategy_results:
        strategy_name = data["name"]
        for group, weight in sorted(data["targets"].items()):
            actual_weight = merged_targets.get(group, 0.0)
            sel_ticker = selected_tickers.get(group, "")
            rows.append([
                date,
                f"{total_equity:.2f}",
                f"{cash:.2f}",
                strategy_name,
                group,
                f"{actual_weight:.4f}",
                sel_ticker,
            ])
    if rows:
        _append_rows(PORTFOLIO_CSV, PORTFOLIO_HEADER, rows)


def save_ohlc_history(ticker: str, history_data: List[Dict]) -> None:
    from app.data_utils import extract_date, extract_price

    new_rows = []
    for row in history_data:
        date = extract_date(row)
        price = extract_price(row)
        if date and price is not None:
            new_rows.append((date, price))

    if not new_rows:
        return

    _ensure_dir()

    existing_dates = set()
    if OHLC_CSV.exists() and OHLC_CSV.stat().st_size > 0:
        with open(OHLC_CSV, "r", newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            header = next(reader, None)
            for row in reader:
                if len(row) >= 3 and row[0] == ticker:
                    existing_dates.add(row[1])

    rows_to_add = []
    for date, price in new_rows:
        if date not in existing_dates:
            rows_to_add.append([ticker, date, f"{price:.2f}"])

    if rows_to_add:
        _append_rows(OHLC_CSV, OHLC_HEADER, rows_to_add)
