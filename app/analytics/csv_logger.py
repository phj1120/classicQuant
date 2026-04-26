import csv
import os
from pathlib import Path
from typing import Dict, List, Optional


def _normalize_date(date_str: str) -> str:
    """날짜 문자열을 YYYY-MM-DD로 정규화한다.

    KIS API는 YYYYMMDD, yfinance/collect은 YYYY-MM-DD를 반환하는데,
    두 형식이 섞이면 중복 감지가 실패하고 sort 순서가 어긋난다.
    모든 I/O 경계에서 이 함수로 통일한다.
    """
    s = str(date_str).strip().replace("-", "")
    if len(s) == 8 and s.isdigit():
        return f"{s[:4]}-{s[4:6]}-{s[6:]}"
    return date_str

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"

HOLDINGS_CSV = DATA_DIR / "holdings.csv"
MOMENTUM_CSV = DATA_DIR / "momentum.csv"
PORTFOLIO_CSV = DATA_DIR / "portfolio.csv"
PORTFOLIO_STATE_CSV = DATA_DIR / "portfolio_state.csv"
PORTFOLIO_NAV_MODEL_CSV = DATA_DIR / "portfolio_nav_model.csv"
PORTFOLIO_NAV_ACTUAL_CSV = DATA_DIR / "portfolio_nav_actual.csv"
OHLC_CSV = DATA_DIR / "ohlc_history.csv"
STRATEGY_SIGNALS_CSV = DATA_DIR / "strategy_signals.csv"
STRATEGY_NAV_CSV = DATA_DIR / "strategy_nav.csv"
PORTFOLIO_NAV_LEGACY_CSV = DATA_DIR / "portfolio_nav.csv"

HOLDINGS_HEADER = ["date", "ticker", "group", "qty", "price", "value", "exchange"]
MOMENTUM_HEADER = ["date", "strategy", "group", "score", "r1m", "r3m", "r6m", "r12m"]
PORTFOLIO_HEADER = ["date", "total_equity", "cash", "strategy", "group", "target_weight", "selected_ticker"]
PORTFOLIO_STATE_HEADER = ["date", "total_equity", "cash"]
OHLC_HEADER = ["ticker", "date", "close"]
STRATEGY_SIGNALS_HEADER = ["date", "strategy", "mode", "selected_assets", "top_score"]
STRATEGY_NAV_HEADER = ["date", "strategy", "daily_return", "nav"]
PORTFOLIO_NAV_MODEL_HEADER = ["date", "nav", "daily_return"]
PORTFOLIO_NAV_ACTUAL_HEADER = ["date", "nav", "daily_return", "total_equity", "fx_rate", "krw_nav"]


def _ensure_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _existing_dates_in_csv(
    path: Path,
    date_col: str,
    filter_col: Optional[str] = None,
    filter_val: Optional[str] = None,
) -> set:
    """CSV 파일에서 기존 날짜 집합을 반환한다.

    filter_col/filter_val 지정 시 해당 컬럼 값이 일치하는 행만 검사한다.
    파일이 없거나 비어 있으면 빈 set을 반환한다.
    """
    if not path.exists() or path.stat().st_size == 0:
        return set()
    with open(path, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return {
            _normalize_date(row.get(date_col, ""))
            for row in reader
            if filter_col is None or row.get(filter_col) == filter_val
        }


def _append_rows(path: Path, header: List[str], rows: List[List]) -> None:
    _ensure_dir()
    write_header = not path.exists() or path.stat().st_size == 0
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(header)
        writer.writerows(rows)


def _migrate_legacy_portfolio_nav_to_actual_if_needed() -> None:
    """레거시 portfolio_nav.csv를 actual NAV 파일로 승격/이관한다."""
    if not PORTFOLIO_NAV_LEGACY_CSV.exists() or PORTFOLIO_NAV_LEGACY_CSV.stat().st_size == 0:
        return

    if PORTFOLIO_NAV_ACTUAL_CSV.exists() and PORTFOLIO_NAV_ACTUAL_CSV.stat().st_size > 0:
        return

    with open(PORTFOLIO_NAV_LEGACY_CSV, "r", newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        rows = list(reader)

    if not rows:
        return

    header = rows[0]
    if header == PORTFOLIO_NAV_ACTUAL_HEADER:
        migrated_rows = rows
    elif header == ["date", "nav", "daily_return"]:
        migrated_rows = [PORTFOLIO_NAV_ACTUAL_HEADER]
        for row in rows[1:]:
            if len(row) >= 3:
                migrated_rows.append([row[0], row[1], row[2], "", "", ""])
    elif header == ["date", "nav", "daily_return", "total_equity"]:
        migrated_rows = [PORTFOLIO_NAV_ACTUAL_HEADER]
        for row in rows[1:]:
            if len(row) >= 4:
                migrated_rows.append([row[0], row[1], row[2], row[3], "", ""])
    else:
        raise RuntimeError(
            f"알 수 없는 portfolio_nav.csv 헤더 형식: {header}"
        )

    with open(PORTFOLIO_NAV_ACTUAL_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerows(migrated_rows)


def _load_portfolio_nav_actual_rows_from_legacy() -> List[Dict]:
    """레거시 portfolio_nav.csv를 actual 형식으로 메모리에서 읽는다."""
    if not PORTFOLIO_NAV_LEGACY_CSV.exists() or PORTFOLIO_NAV_LEGACY_CSV.stat().st_size == 0:
        return []

    rows = []
    with open(PORTFOLIO_NAV_LEGACY_CSV, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            normalized = {
                "date": _normalize_date(row.get("date", "")),
                "nav": row.get("nav", ""),
                "daily_return": row.get("daily_return", ""),
                "total_equity": row.get("total_equity", ""),
            }
            if normalized["date"]:
                rows.append(normalized)
    return sorted(rows, key=lambda r: r.get("date", ""))


def _append_unique_rows(
    path: Path,
    header: List[str],
    rows: List[List],
    existing_key_fn,
    row_key_fn,
) -> None:
    """기존 키와 중복되지 않는 행만 append 한다.

    기존 파일의 마지막 기록을 유지한 채, 같은 키의 중복 재실행만 방지한다.
    """
    _ensure_dir()

    existing_keys = set()
    if path.exists() and path.stat().st_size > 0:
        with open(path, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                existing_keys.add(existing_key_fn(row))

    unique_rows: List[List] = []
    for row in rows:
        key = row_key_fn(row)
        if key in existing_keys:
            continue
        existing_keys.add(key)
        unique_rows.append(row)

    if unique_rows:
        _append_rows(path, header, unique_rows)


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
        _append_unique_rows(
            HOLDINGS_CSV,
            HOLDINGS_HEADER,
            rows,
            existing_key_fn=lambda row: (
                _normalize_date(row.get("date", "")),
                row.get("ticker", ""),
            ),
            row_key_fn=lambda row: (
                _normalize_date(row[0]),
                row[1],
            ),
        )


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
        _append_unique_rows(
            MOMENTUM_CSV,
            MOMENTUM_HEADER,
            rows,
            existing_key_fn=lambda row: (
                _normalize_date(row.get("date", "")),
                row.get("strategy", ""),
                row.get("group", ""),
            ),
            row_key_fn=lambda row: (
                _normalize_date(row[0]),
                row[1],
                row[2],
            ),
        )


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
        _append_unique_rows(
            PORTFOLIO_CSV,
            PORTFOLIO_HEADER,
            rows,
            existing_key_fn=lambda row: (
                _normalize_date(row.get("date", "")),
                row.get("strategy", ""),
                row.get("group", ""),
            ),
            row_key_fn=lambda row: (
                _normalize_date(row[0]),
                row[3],
                row[4],
            ),
        )


def save_portfolio_state(date: str, total_equity: float, cash: float) -> None:
    _append_unique_rows(
        PORTFOLIO_STATE_CSV,
        PORTFOLIO_STATE_HEADER,
        [[date, f"{total_equity:.2f}", f"{cash:.2f}"]],
        existing_key_fn=lambda row: _normalize_date(row.get("date", "")),
        row_key_fn=lambda row: _normalize_date(row[0]),
    )


def load_portfolio_state() -> List[Dict]:
    if not PORTFOLIO_STATE_CSV.exists():
        return []
    rows = []
    with open(PORTFOLIO_STATE_CSV, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            row["date"] = _normalize_date(row.get("date", ""))
            rows.append(row)

    deduped: Dict[str, Dict] = {}
    for row in rows:
        deduped[row["date"]] = row
    return sorted(deduped.values(), key=lambda r: r.get("date", ""))


def save_strategy_signal(
    date: str,
    strategy_name: str,
    mode: str,
    selected_assets: Dict[str, float],
    top_score: Optional[float],
) -> None:
    """전략 신호를 strategy_signals.csv에 기록한다."""
    assets_str = "|".join(f"{g}:{w:.4f}" for g, w in sorted(selected_assets.items()))
    row = [
        date,
        strategy_name,
        mode,
        assets_str,
        f"{top_score:.4f}" if top_score is not None else "",
    ]
    _append_unique_rows(
        STRATEGY_SIGNALS_CSV,
        STRATEGY_SIGNALS_HEADER,
        [row],
        existing_key_fn=lambda existing_row: (
            _normalize_date(existing_row.get("date", "")),
            existing_row.get("strategy", ""),
        ),
        row_key_fn=lambda new_row: (
            _normalize_date(new_row[0]),
            new_row[1],
        ),
    )


def load_strategy_signals(strategy_name: str) -> List[Dict]:
    """특정 전략의 모든 신호를 날짜 순으로 로드한다."""
    if not STRATEGY_SIGNALS_CSV.exists():
        return []
    rows = []
    with open(STRATEGY_SIGNALS_CSV, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("strategy") == strategy_name:
                row["date"] = _normalize_date(row.get("date", ""))
                rows.append(row)

    deduped: Dict[str, Dict] = {}
    for row in rows:
        deduped[row["date"]] = row
    return sorted(deduped.values(), key=lambda r: r.get("date", ""))


def save_strategy_nav(
    date: str,
    strategy_name: str,
    daily_return: float,
    nav: float,
) -> None:
    """전략 NAV를 strategy_nav.csv에 기록한다 (중복 날짜 스킵)."""
    _ensure_dir()
    date = _normalize_date(date)

    if date in _existing_dates_in_csv(STRATEGY_NAV_CSV, "date", "strategy", strategy_name):
        return

    row = [date, strategy_name, f"{daily_return:.6f}", f"{nav:.6f}"]
    _append_rows(STRATEGY_NAV_CSV, STRATEGY_NAV_HEADER, [row])


def load_strategy_nav(strategy_name: Optional[str] = None) -> Dict[str, List[Dict]]:
    """strategy_nav.csv를 로드한다.

    strategy_name 지정 시 해당 전략만 반환, None이면 전체 반환.
    날짜를 YYYY-MM-DD로 정규화하고, (전략, 날짜) 중복은 파일 하단(최신 기록) 우선으로 제거한다.
    반환: {strategy_name: [{date, daily_return, nav}, ...]} (날짜 오름차순)
    """
    if not STRATEGY_NAV_CSV.exists():
        return {}
    raw: Dict[str, List[Dict]] = {}
    with open(STRATEGY_NAV_CSV, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row.get("strategy", "")
            if strategy_name and name != strategy_name:
                continue
            row["date"] = _normalize_date(row.get("date", ""))
            raw.setdefault(name, []).append(row)

    result: Dict[str, List[Dict]] = {}
    for name, rows in raw.items():
        # 중복 날짜 제거: 파일 하단 기록 우선 (실제 매매 데이터 > 시뮬레이션 데이터)
        deduped: Dict[str, Dict] = {}
        for row in rows:
            deduped[row["date"]] = row
        result[name] = sorted(deduped.values(), key=lambda r: r["date"])
    return result


def load_portfolio_snapshots() -> List[Dict]:
    """portfolio.csv에서 날짜별 포트폴리오 스냅샷을 로드한다."""
    if not PORTFOLIO_CSV.exists():
        return []

    raw: Dict[str, Dict] = {}
    with open(PORTFOLIO_CSV, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            date = _normalize_date(row.get("date", ""))
            if not date:
                continue
            row["date"] = date
            raw[date] = row

    return sorted(raw.values(), key=lambda r: r.get("date", ""))


def load_ohlc_prices(tickers: Optional[List[str]] = None) -> Dict[str, Dict[str, float]]:
    """ohlc_history.csv에서 가격 데이터를 로드한다.

    반환: {ticker: {date: close_price}}
    """
    if not OHLC_CSV.exists():
        return {}
    result: Dict[str, Dict[str, float]] = {}
    ticker_set = set(tickers) if tickers else None
    with open(OHLC_CSV, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ticker = row.get("ticker", "")
            if ticker_set and ticker not in ticker_set:
                continue
            date = row.get("date", "")
            try:
                price = float(row.get("close", 0))
            except (ValueError, TypeError):
                continue
            result.setdefault(ticker, {})[date] = price
    return result


def save_ohlc_history(ticker: str, history_data: List[Dict]) -> None:
    from app.data.data_utils import extract_date, extract_price

    new_rows = []
    for row in history_data:
        date = _normalize_date(extract_date(row) or "")
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


def save_portfolio_nav_model(
    date: str,
    nav: float,
    daily_return: float,
) -> None:
    """모델 포트폴리오 NAV를 portfolio_nav_model.csv에 기록한다."""
    _ensure_dir()
    date = _normalize_date(date)
    if date in _existing_dates_in_csv(PORTFOLIO_NAV_MODEL_CSV, "date"):
        return
    _append_rows(
        PORTFOLIO_NAV_MODEL_CSV,
        PORTFOLIO_NAV_MODEL_HEADER,
        [[date, f"{nav:.6f}", f"{daily_return:.6f}"]],
    )


def load_portfolio_nav_model() -> List[Dict]:
    """portfolio_nav_model.csv 로드. 날짜 오름차순."""
    if not PORTFOLIO_NAV_MODEL_CSV.exists():
        return []
    rows = []
    with open(PORTFOLIO_NAV_MODEL_CSV, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            row["date"] = _normalize_date(row.get("date", ""))
            rows.append(row)
    return sorted(rows, key=lambda r: r.get("date", ""))


def save_portfolio_nav_actual(
    date: str,
    nav: float,
    daily_return: float,
    total_equity: Optional[float] = None,
    fx_rate: Optional[float] = None,
    krw_nav: Optional[float] = None,
) -> None:
    """실제 포트폴리오 NAV를 portfolio_nav_actual.csv에 기록한다."""
    _ensure_dir()
    _migrate_legacy_portfolio_nav_to_actual_if_needed()
    date = _normalize_date(date)
    if date in _existing_dates_in_csv(PORTFOLIO_NAV_ACTUAL_CSV, "date"):
        return
    equity_str = f"{total_equity:.2f}" if total_equity is not None else ""
    fx_str = f"{fx_rate:.2f}" if fx_rate is not None else ""
    krw_str = f"{krw_nav:.2f}" if krw_nav is not None else ""
    _append_rows(
        PORTFOLIO_NAV_ACTUAL_CSV,
        PORTFOLIO_NAV_ACTUAL_HEADER,
        [[date, f"{nav:.6f}", f"{daily_return:.6f}", equity_str, fx_str, krw_str]],
    )


def load_portfolio_nav_actual() -> List[Dict]:
    """portfolio_nav_actual.csv 로드. 날짜 오름차순."""
    if not PORTFOLIO_NAV_ACTUAL_CSV.exists():
        return _load_portfolio_nav_actual_rows_from_legacy()
    rows = []
    with open(PORTFOLIO_NAV_ACTUAL_CSV, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            row["date"] = _normalize_date(row.get("date", ""))
            rows.append(row)
    return sorted(rows, key=lambda r: r.get("date", ""))
