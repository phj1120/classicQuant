"""전략 NAV 백테스트 모듈.

과거 가격 데이터를 이용하여 전략별 NAV 시계열을 시뮬레이션한다.
월말 리밸런싱 기준으로 매일 NAV를 계산한다.
"""

from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from app.assets import reload_assets
from app.constants import LOOKBACK_DAYS
from app.csv_logger import load_ohlc_prices, save_strategy_nav
from app.data_utils import parse_history
from app.momentum import compute_momentum
from app.strategy import BaseStrategy


def _get_month_end_dates(all_dates: List[str]) -> List[str]:
    """날짜 목록에서 각 달의 마지막 거래일을 반환한다."""
    month_last: Dict[str, str] = {}
    for d in sorted(all_dates):
        ym = d[:7]  # "YYYY-MM"
        month_last[ym] = d
    return sorted(month_last.values())


def _prices_up_to(
    price_dict: Dict[str, Dict[str, float]],
    ticker: str,
    cutoff: str,
) -> List[float]:
    """특정 날짜 이하의 가격 시계열(오름차순)을 반환한다."""
    data = price_dict.get(ticker, {})
    dates = sorted(d for d in data if d <= cutoff)
    return [data[d] for d in dates]


def _compute_scores_at_date(
    strategy: BaseStrategy,
    price_dict: Dict[str, Dict[str, float]],
    date: str,
) -> Dict[str, Optional[float]]:
    """특정 날짜 기준 전략 universe의 모멘텀 점수를 계산한다."""
    from app.assets import group_tickers
    reload_assets(strategy.assets_file)

    scores: Dict[str, Optional[float]] = {}
    for group in strategy.get_universe():
        score = None
        for ticker in group_tickers(group):
            prices = _prices_up_to(price_dict, ticker, date)
            if len(prices) > LOOKBACK_DAYS["12m"]:
                _, returns = compute_momentum(prices)
                score = strategy.score_from_returns(returns)
                if score is not None:
                    break
        scores[group] = score
    return scores


def _build_histories_at_date(
    strategy: BaseStrategy,
    price_dict: Dict[str, Dict[str, float]],
    date: str,
) -> Dict[str, List[float]]:
    """특정 날짜 기준 전략 universe의 파싱된 가격 시계열을 반환한다.

    SMA·변동성·상관관계 계산이 필요한 전략(GTAA, Ivy, FAA, EAA, LAA)에 사용됩니다.
    """
    from app.assets import group_tickers
    histories: Dict[str, List[float]] = {}
    for group in strategy.get_universe():
        for ticker in group_tickers(group):
            prices = _prices_up_to(price_dict, ticker, date)
            if prices:
                histories[ticker] = prices
    return histories


def run_backtest(
    strategy_name: str,
    strategy: BaseStrategy,
    price_dict: Dict[str, Dict[str, float]],
    lookback_months: int = 60,
) -> List[Tuple[str, float, float]]:
    """전략의 과거 NAV 시계열을 시뮬레이션한다.

    Args:
        strategy_name: 전략 이름
        strategy: BaseStrategy 인스턴스
        price_dict: {ticker: {date: close_price}}
        lookback_months: 최대 백테스트 기간 (월)

    Returns:
        [(date, daily_return, cumulative_nav), ...] 날짜 오름차순
    """
    # 모든 관련 티커의 날짜 수집
    all_dates: List[str] = []
    reload_assets(strategy.assets_file)
    from app.assets import group_tickers
    relevant_tickers = set()
    for group in strategy.get_universe():
        for ticker in group_tickers(group):
            if ticker in price_dict:
                relevant_tickers.add(ticker)
                all_dates.extend(price_dict[ticker].keys())

    if not all_dates:
        print(f"⚠️  {strategy_name}: 가격 데이터 없음")
        return []

    all_dates = sorted(set(all_dates))
    month_ends = _get_month_end_dates(all_dates)

    # 워밍업: 최소 12개월 데이터 필요
    min_warmup = LOOKBACK_DAYS["12m"]

    # 선택 가능한 날짜 범위 결정 (lookback_months 제한)
    if len(month_ends) > lookback_months + 2:
        month_ends = month_ends[-(lookback_months + 2):]

    nav = 1.0
    results: List[Tuple[str, float, float]] = []
    current_targets: Dict[str, float] = {}
    last_rebalance_date = ""

    for i, date in enumerate(all_dates):
        # 이 날짜가 월말이면 리밸런싱
        if date in set(month_ends):
            reload_assets(strategy.assets_file)
            scores = _compute_scores_at_date(strategy, price_dict, date)
            histories = _build_histories_at_date(strategy, price_dict, date)
            try:
                current_targets = strategy.select_targets(scores, histories=histories)
            except RuntimeError:
                pass  # 데이터 부족 시 이전 targets 유지
            last_rebalance_date = date

        if not current_targets or not last_rebalance_date:
            continue

        # 일별 수익률 계산
        if i == 0:
            continue

        prev_date = all_dates[i - 1]

        reload_assets(strategy.assets_file)
        daily_return = _calc_daily_return(
            current_targets, price_dict, prev_date, date
        )

        nav *= (1.0 + daily_return)
        results.append((date, daily_return, nav))

    return results


def _calc_daily_return(
    targets: Dict[str, float],
    price_dict: Dict[str, Dict[str, float]],
    prev_date: str,
    curr_date: str,
) -> float:
    """전날 → 오늘의 가중 수익률 계산."""
    from app.assets import group_tickers
    total_return = 0.0
    total_weight = 0.0

    for group, weight in targets.items():
        # 그룹의 우선순위 티커 순서로 시도
        for ticker in group_tickers(group):
            prev_price = price_dict.get(ticker, {}).get(prev_date)
            curr_price = price_dict.get(ticker, {}).get(curr_date)
            if prev_price and curr_price and prev_price > 0:
                ret = (curr_price / prev_price) - 1.0
                total_return += weight * ret
                total_weight += weight
                break

    # 데이터 없는 자산은 0% 수익률로 처리
    return total_return


def run_all_backtests(
    strategy_entries: List[Dict],
    lookback_months: int = 60,
) -> None:
    """모든 전략의 백테스트를 실행하고 strategy_nav.csv에 저장한다."""
    from app.strategies import get_strategy
    from app.csv_logger import load_strategy_nav

    # 기존 NAV 데이터 확인
    existing_nav = load_strategy_nav()

    # 전체 price_dict 구축 (ohlc_history.csv 활용)
    print("📂 가격 히스토리 로드 중...")
    price_dict = load_ohlc_prices()

    if not price_dict:
        print("⚠️  ohlc_history.csv에 데이터 없음. run_backfill.py를 먼저 실행하세요.")
        return

    for entry in strategy_entries:
        name = entry["name"]

        # 이미 충분한 데이터가 있으면 스킵
        existing = existing_nav.get(name, [])
        if len(existing) > LOOKBACK_DAYS["12m"]:
            print(f"⏭️  {name}: 이미 NAV 데이터 있음 ({len(existing)}일치), 스킵")
            continue

        print(f"\n🔄 {name} 백테스트 실행 중...")
        try:
            strategy = get_strategy(name)
            nav_series = run_backtest(name, strategy, price_dict, lookback_months)

            saved = 0
            for date, daily_ret, nav_val in nav_series:
                save_strategy_nav(date, name, daily_ret, nav_val)
                saved += 1

            print(f"  ✅ {name}: {saved}일치 NAV 저장 완료")
        except Exception as e:
            print(f"  ❌ {name} 백테스트 실패: {e}")
