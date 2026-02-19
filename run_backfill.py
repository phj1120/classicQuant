"""과거 NAV 일괄 생성 스크립트 (1회 실행).

실행: python run_backfill.py

동작:
1. 전체 전략의 자산에 대해 과거 가격 데이터 수집 (KIS API, 최대 ~5년)
2. ohlc_history.csv에 저장
3. 각 전략의 NAV 시뮬레이션 (월말 리밸런싱 기준)
4. strategy_nav.csv에 저장 (이미 데이터 있으면 스킵)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.assets import reload_assets
from app.backtest import run_all_backtests
from app.config import build_kis_config, load_config, load_key, load_strategy_entries
from app.csv_logger import save_ohlc_history
from app.exchange import set_exchange_for_ticker
from app.groups import group_tickers
from app.kis_api import KoreaInvestmentAPI
from app.strategies import get_strategy


def collect_price_history(api: KoreaInvestmentAPI, strategy_entries: list) -> None:
    """전체 전략 자산의 과거 가격 데이터를 수집하여 ohlc_history.csv에 저장한다."""
    all_tickers: set = set()

    for entry in strategy_entries:
        name = entry["name"]
        try:
            strategy = get_strategy(name)
            reload_assets(strategy.assets_file)
            for group in strategy.get_universe():
                for ticker in group_tickers(group):
                    all_tickers.add(ticker)
        except Exception as e:
            print(f"⚠️  {name} universe 로드 실패: {e}")

    print(f"\n📋 수집할 티커: {len(all_tickers)}개")
    print(", ".join(sorted(all_tickers)))

    for i, ticker in enumerate(sorted(all_tickers), 1):
        print(f"\n[{i}/{len(all_tickers)}] {ticker} 가격 히스토리 수집 중...")
        try:
            set_exchange_for_ticker(api, ticker)
            # 최대 5년치 (약 1260 거래일) 수집
            history = api.get_historical_data(ticker, period="D", min_records=1260)
            if history:
                save_ohlc_history(ticker, history)
                print(f"  ✅ {len(history)}개 데이터 저장")
            else:
                print(f"  ⚠️  데이터 없음")
        except Exception as e:
            print(f"  ❌ 실패: {e}")


def main() -> None:
    base_dir = Path(__file__).resolve().parent
    config_path = base_dir / "config.json"
    key_path = base_dir / "key.json"

    raw = load_config(config_path)
    key = load_key(key_path if key_path.exists() else None)
    kis_config = build_kis_config(key)
    strategy_entries = load_strategy_entries(raw)

    api = KoreaInvestmentAPI(kis_config, config_file=str(key_path) if key_path.exists() else None)

    print("=" * 60)
    print("📊 classicQuant 백필 시작")
    print("=" * 60)

    # Step 1: 과거 가격 데이터 수집
    print("\n[Step 1] 과거 가격 데이터 수집")
    collect_price_history(api, strategy_entries)

    # Step 2: 전략 NAV 시뮬레이션
    print("\n[Step 2] 전략 NAV 시뮬레이션")
    run_all_backtests(strategy_entries, lookback_months=60)

    print("\n✅ 백필 완료!")
    print("이제 run_collect.py (매일) 또는 run_rebalance.py를 실행할 수 있습니다.")


if __name__ == "__main__":
    main()
