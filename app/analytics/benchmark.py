"""벤치마크 NAV 계산 모듈.

ohlc_history.csv의 SPY, AGG 가격으로 두 가지 벤치마크 NAV를 생성한다.
- spy_nav: SPY 100% (매수 후 보유)
- balanced_nav: SPY 60% + AGG 40% (연 1회 리밸런싱)

daily_return 기준으로 NAV를 누적한다.
"""
from pathlib import Path
from typing import Dict, List, Optional

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
BENCHMARK_NAV_CSV = DATA_DIR / "benchmark_nav.csv"


def build_benchmark_nav(ohlc_rows: List[Dict]) -> List[Dict]:
    """ohlc_rows에서 벤치마크 NAV 시계열을 생성한다.

    ohlc_rows: csv_logger.load_ohlc_history() 반환값 (list of dicts)
    각 row: {"date": "YYYY-MM-DD", "ticker": "...", "close": "..."}

    Returns: [{"date": ..., "spy_nav": ..., "spy_return": ...,
                "balanced_nav": ..., "balanced_return": ...}, ...]
    날짜 오름차순.
    """
    # SPY와 AGG 가격 추출
    spy_prices: Dict[str, float] = {}
    agg_prices: Dict[str, float] = {}
    for row in ohlc_rows:
        ticker = row.get("ticker", "")
        date = row.get("date", "")
        try:
            close = float(row.get("close", 0) or 0)
        except (ValueError, TypeError):
            continue
        if ticker == "SPY" and close > 0:
            spy_prices[date] = close
        elif ticker == "AGG" and close > 0:
            agg_prices[date] = close

    # 공통 날짜
    common_dates = sorted(set(spy_prices) & set(agg_prices))
    if len(common_dates) < 2:
        return []

    results = []
    spy_nav = 1.0
    bal_nav = 1.0
    # 60/40 포트폴리오: 매년 1월 첫 거래일에 리밸런싱
    spy_weight = 0.6
    agg_weight = 0.4
    prev_spy = spy_prices[common_dates[0]]
    prev_agg = agg_prices[common_dates[0]]
    prev_year = common_dates[0][:4]

    for i, date in enumerate(common_dates):
        if i == 0:
            results.append({
                "date": date,
                "spy_nav": f"{spy_nav:.6f}",
                "spy_return": "0.000000",
                "balanced_nav": f"{bal_nav:.6f}",
                "balanced_return": "0.000000",
            })
            continue

        spy_r = spy_prices[date] / prev_spy - 1
        agg_r = agg_prices[date] / prev_agg - 1

        # 연간 리밸런싱 (새해 첫 거래일)
        cur_year = date[:4]
        if cur_year != prev_year:
            # 리밸런싱: spy/agg 비중 초기화
            spy_weight = 0.6
            agg_weight = 0.4
            prev_year = cur_year

        spy_nav *= (1 + spy_r)
        bal_return = spy_weight * spy_r + agg_weight * agg_r
        bal_nav *= (1 + bal_return)

        # 비중 드리프트 반영
        total = spy_weight * (1 + spy_r) + agg_weight * (1 + agg_r)
        if total > 0:
            spy_weight = spy_weight * (1 + spy_r) / total
            agg_weight = agg_weight * (1 + agg_r) / total

        results.append({
            "date": date,
            "spy_nav": f"{spy_nav:.6f}",
            "spy_return": f"{spy_r:.6f}",
            "balanced_nav": f"{bal_nav:.6f}",
            "balanced_return": f"{bal_return:.6f}",
        })
        prev_spy = spy_prices[date]
        prev_agg = agg_prices[date]

    return results


def save_benchmark_nav(rows: List[Dict]) -> None:
    """benchmark_nav.csv에 저장. 이미 있는 날짜는 스킵."""
    import csv
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    header = ["date", "spy_nav", "spy_return", "balanced_nav", "balanced_return"]

    existing_dates: set = set()
    if BENCHMARK_NAV_CSV.exists():
        with open(BENCHMARK_NAV_CSV, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                existing_dates.add(row.get("date", ""))

    new_rows = [r for r in rows if r["date"] not in existing_dates]
    if not new_rows:
        return

    write_header = not BENCHMARK_NAV_CSV.exists() or BENCHMARK_NAV_CSV.stat().st_size == 0
    with open(BENCHMARK_NAV_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(header)
        for row in new_rows:
            writer.writerow([row[k] for k in header])


def load_benchmark_nav() -> List[Dict]:
    """benchmark_nav.csv 로드. 날짜 오름차순."""
    import csv
    if not BENCHMARK_NAV_CSV.exists():
        return []
    rows = []
    with open(BENCHMARK_NAV_CSV, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return sorted(rows, key=lambda r: r.get("date", ""))
