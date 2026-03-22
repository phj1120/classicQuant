"""일별 신호 수집 스크립트 (매일 실행).

실행: python run_collect.py

동작:
1. 전체 9개 전략의 오늘 신호 계산 (잔고 조회 없음)
2. data/strategy_signals.csv 에 오늘치 신호 기록
3. data/momentum.csv 에 오늘치 모멘텀 점수 기록
4. data/ohlc_history.csv 에 오늘 가격 추가
5. data/strategy_nav.csv 에 오늘치 NAV 추가 (어제 포트폴리오 기준 수익률)

매매 없음, 보고서 없음.
GitHub Actions / cron으로 매일 실행.
"""

import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.assets.assets import reload_assets
from app.config import build_kis_config, load_config, load_key, load_strategy_entries
from app.analytics.csv_logger import (
    load_ohlc_prices,
    load_strategy_nav,
    load_strategy_signals,
    save_momentum,
    save_ohlc_history,
    save_strategy_nav,
    save_strategy_signal,
)
from app.execution.exchange import set_exchange_for_ticker
from app.assets.groups import group_tickers
from app.data.kis_api import KoreaInvestmentAPI
from app.data.data_utils import parse_history
from app.indicators.momentum import get_momentum_scores
from app.strategies import get_strategy


def _get_latest_price_for_ticker(ticker: str, price_dict: dict) -> float | None:
    """ohlc_history.csv에서 특정 티커의 가장 최근 가격을 반환한다."""
    dates = price_dict.get(ticker, {})
    if not dates:
        return None
    latest_date = max(dates.keys())
    return dates[latest_date]


def _calc_strategy_daily_return(
    strategy_name: str,
    today: str,
    price_dict: dict,
) -> float:
    """어제 포지션 기준으로 오늘의 일별 수익률을 계산한다."""
    signals = load_strategy_signals(strategy_name)
    if len(signals) < 2:
        return 0.0

    # 어제 신호 (오늘 이전 마지막 신호)
    prev_signals = [s for s in signals if s.get("date", "") < today]
    if not prev_signals:
        return 0.0

    prev_signal = prev_signals[-1]
    prev_date = prev_signal.get("date", "")

    # 선택 자산 파싱: "SPY:0.5|AGG:0.5" 형식
    assets_str = prev_signal.get("selected_assets", "")
    if not assets_str:
        return 0.0

    targets: dict = {}
    for part in assets_str.split("|"):
        if ":" in part:
            group, w_str = part.split(":", 1)
            try:
                targets[group.strip()] = float(w_str)
            except ValueError:
                pass

    if not targets:
        return 0.0

    total_return = 0.0
    for group, weight in targets.items():
        for ticker in group_tickers(group):
            prev_price = price_dict.get(ticker, {}).get(prev_date)
            curr_price = price_dict.get(ticker, {}).get(today)
            if prev_price and curr_price and prev_price > 0:
                ret = (curr_price / prev_price) - 1.0
                total_return += weight * ret
                break

    return total_return


def _get_prev_nav(strategy_name: str) -> float:
    """이전 NAV 값을 가져온다. 없으면 1.0."""
    nav_data = load_strategy_nav(strategy_name)
    series = nav_data.get(strategy_name, [])
    if not series:
        return 1.0
    try:
        return float(series[-1]["nav"])
    except (KeyError, ValueError, TypeError):
        return 1.0


def main() -> None:
    base_dir = Path(__file__).resolve().parent
    config_path = base_dir / "config.json"
    key_path = base_dir / "key.json"

    raw = load_config(config_path)
    key = load_key(key_path if key_path.exists() else None)
    kis_config = build_kis_config(key)
    strategy_entries = load_strategy_entries(raw)

    api = KoreaInvestmentAPI(kis_config, config_file=str(key_path) if key_path.exists() else None)

    today = datetime.now().strftime("%Y-%m-%d")

    print("=" * 60)
    print(f"📊 classicQuant 일별 수집 | {today}")
    print("=" * 60)

    for entry in strategy_entries:
        name = entry["name"]

        print(f"\n{'─'*50}")
        print(f"📈 전략: {name}")
        print(f"{'─'*50}")

        try:
            strategy = get_strategy(name)
            reload_assets(strategy.assets_file)

            universe = strategy.get_universe()
            _, all_returns, all_histories = get_momentum_scores(api, universe)
            scores = {group: strategy.score_from_returns(rets) for group, rets in all_returns.items()}
            parsed_histories = {t: parse_history(h) for t, h in all_histories.items()}
            targets = strategy.select_targets(scores, histories=parsed_histories)

            # 모멘텀 기록
            save_momentum(today, name, scores, all_returns)

            # OHLC 기록
            for ticker, history in all_histories.items():
                save_ohlc_history(ticker, history)

            # 신호 기록
            mode = "offensive" if strategy.is_offensive(scores) else "defensive"
            top_score = max(
                (s for s in scores.values() if s is not None),
                default=None
            )
            save_strategy_signal(today, name, mode, targets, top_score)

            print(f"  모드: {mode}")
            print(f"  선택 자산: {', '.join(f'{g}({w:.0%})' for g, w in targets.items())}")

            # NAV 업데이트
            price_dict = load_ohlc_prices()
            daily_return = _calc_strategy_daily_return(name, today, price_dict)
            prev_nav = _get_prev_nav(name)
            new_nav = prev_nav * (1.0 + daily_return)
            save_strategy_nav(today, name, daily_return, new_nav)

            print(f"  일별수익: {daily_return:.4%} | NAV: {new_nav:.4f}")

        except Exception as e:
            print(f"  ❌ {name} 처리 실패: {e}")

    print(f"\n✅ 수집 완료: {today}")


if __name__ == "__main__":
    main()
