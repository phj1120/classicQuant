"""과거 NAV 일괄 생성 스크립트 (1회 실행).

실행: python run_backfill.py

동작:
1. 전체 전략의 자산에 대해 과거 가격 데이터 수집 (KIS API, 최대 ~5년)
2. ohlc_history.csv에 저장
3. 각 전략의 NAV 시뮬레이션 (월말 리밸런싱 기준)
4. strategy_nav.csv에 저장 (이미 데이터 있으면 스킵)
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.assets.assets import merge_assets, reload_assets
from app.analytics.backtest import run_all_backtests
from app.config import build_kis_config, load_config, load_key, load_strategy_entries
from app.analytics.csv_logger import save_ohlc_history
from app.execution.exchange import set_exchange_for_ticker
from app.assets.groups import group_tickers
from app.data.kis_api import KoreaInvestmentAPI
from app.strategies import get_strategy


def _collect_all_tickers(strategy_entries: list):
    """전략 목록에서 전체 티커 집합과 assets 파일 목록을 반환한다."""
    

    all_tickers: set = set()
    assets_files = []

    for entry in strategy_entries:
        name = entry["name"]
        try:
            strategy = get_strategy(name)
            reload_assets(strategy.assets)
            assets_files.append(strategy.assets)
            for group in strategy.get_universe():
                for ticker in group_tickers(group):
                    all_tickers.add(ticker)
        except Exception as e:
            print(f"⚠️  {name} universe 로드 실패: {e}")

    merge_assets(assets_files)
    return sorted(all_tickers)


def collect_price_history_yfinance(strategy_entries: list) -> None:
    """Yahoo Finance로 전체 전략 자산의 장기 가격 데이터를 수집한다 (최대 20년+)."""
    from app.data.yfinance_loader import fetch_all_tickers

    sorted_tickers = _collect_all_tickers(strategy_entries)

    print(f"\n📋 수집할 티커: {len(sorted_tickers)}개")
    print(", ".join(sorted_tickers))
    print()

    ticker_data = fetch_all_tickers(sorted_tickers, period="max")

    for ticker, rows in ticker_data.items():
        save_ohlc_history(ticker, rows)


def collect_price_history_kis(api: KoreaInvestmentAPI, strategy_entries: list) -> None:
    """KIS API로 전략 자산 가격 데이터를 수집한다.

    KIS API는 페이지당 ~100건, max_pages 설정에 따라 최대 수년치 수집 가능.
    초기 백필보다는 일별 갱신에 적합하다.
    """
    sorted_tickers = _collect_all_tickers(strategy_entries)

    print(f"\n📋 수집할 티커: {len(sorted_tickers)}개")
    print(", ".join(sorted_tickers))

    for i, ticker in enumerate(sorted_tickers, 1):
        print(f"\n[{i}/{len(sorted_tickers)}] {ticker} 가격 히스토리 수집 중...")
        try:
            set_exchange_for_ticker(api, ticker)
            history = api.get_historical_data(ticker, period="D", min_records=5040, max_pages=52)
            if history:
                save_ohlc_history(ticker, history)
                print(f"  ✅ {len(history)}개 데이터 저장")
            else:
                print(f"  ⚠️  데이터 없음")
        except Exception as e:
            print(f"  ❌ 실패: {e}")


def main() -> None:
    parser = argparse.ArgumentParser(description="classicQuant 백필")
    parser.add_argument(
        "--source",
        choices=["yfinance", "kis"],
        default="yfinance",
        help="가격 데이터 수집 소스 (기본: yfinance = 20년+, kis = KIS API)",
    )
    parser.add_argument(
        "--nav-only",
        action="store_true",
        help="가격 수집 없이 NAV 시뮬레이션만 실행",
    )
    args = parser.parse_args()

    base_dir = Path(__file__).resolve().parent
    config_path = base_dir / "config.json"
    key_path = base_dir / "key.json"

    raw = load_config(config_path)
    key = load_key(key_path if key_path.exists() else None)
    strategy_entries = load_strategy_entries(raw)

    print("=" * 60)
    print("📊 classicQuant 백필 시작")
    print("=" * 60)

    if not args.nav_only:
        print(f"\n[Step 1] 과거 가격 데이터 수집 (소스: {args.source})")
        if args.source == "yfinance":
            collect_price_history_yfinance(strategy_entries)
        else:
            kis_config = build_kis_config(key)
            api = KoreaInvestmentAPI(kis_config, config_file=str(key_path) if key_path.exists() else None)
            collect_price_history_kis(api, strategy_entries)

    # Step 2: 전략 NAV 시뮬레이션
    print("\n[Step 2] 전략 NAV 시뮬레이션 (20년 기준)")
    run_all_backtests(strategy_entries, lookback_months=240)

    print("\n✅ 백필 완료!")
    print("이제 run_selection_backtest.py --full 로 최적 설정을 찾을 수 있습니다.")


if __name__ == "__main__":
    main()
